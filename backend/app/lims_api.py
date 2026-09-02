import uuid

from fastapi import APIRouter, Depends, HTTPException

from .config import Settings
from .auth import AuthManager
from .database import Database, now_iso
from .schemas import QueryLimsRequest, RecognizeLimsRequest
from .services.lims_normalizer import COLLECTION_ORDER, merge_instances, normalize_instance
from .services.lims_oracle import query_lims_project


def create_lims_router(database: Database, settings: Settings, auth: AuthManager) -> APIRouter:
    router = APIRouter(
        prefix=f"{settings.api_prefix}/lims", tags=["lims"],
        dependencies=[Depends(auth.require_any("REPORT_EDIT", "LIMS_FIELDS_MANAGE"))],
    )

    def import_response(item: dict) -> dict:
        return {"id": item["id"], "fileName": item["file_name"], "size": item["size"],
                "summary": item["summary"], "createdAt": item["created_at"]}

    def required_import(import_id: str) -> dict:
        item = database.get_lims_import(import_id)
        if not item:
            raise HTTPException(404, "LIMS 导入记录不存在")
        return item

    def stored_instance(item: dict, instance_id: str) -> dict:
        payload = database.get_lims_instance_payload(item["id"], instance_id)
        if not payload:
            raise KeyError(instance_id)
        return payload

    def normalized_instance(item: dict, instance_id: str) -> dict:
        payload = database.get_lims_normalized_payload(item["id"], instance_id)
        if not payload:
            raise KeyError(instance_id)
        return payload

    @router.get("/capabilities")
    def capabilities() -> dict:
        return {
            "sqlEnabled": settings.lims_sql_enabled,
            "sqlConfigured": bool(settings.lims_sql_dsn.strip() and settings.lims_sql_user.strip()
                                  and settings.lims_sql_password),
        }

    @router.post("/query")
    def query_project(request: QueryLimsRequest) -> dict:
        try:
            summary, instances = query_lims_project(settings, request.project_id)
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error
        except Exception as error:
            raise HTTPException(502, f"LIMS Oracle 查询失败：{error}") from error
        if not instances:
            raise HTTPException(404, f"项目编号 {request.project_id} 未查询到 LIMS 数据")
        fields = database.list_lims_fields()
        rules = database.list_lims_parser_rules()
        # 先完成全部归一化：任一实例解析失败时不留下 0 实例的孤儿导入记录
        try:
            normalized = [(raw, normalize_instance(raw, fields, rules)) for raw in instances]
        except (ValueError, IndexError, KeyError, TypeError) as error:
            raise HTTPException(502, f"LIMS 数据解析失败：{error}") from error
        import_id = uuid.uuid4().hex
        item = database.create_lims_import({
            "id": import_id,
            "file_name": f"Oracle 查询：{request.project_id}",
            "stored_name": "",
            "size": 0,
            "summary": summary,
            "created_at": now_iso(),
        })
        for raw, payload in normalized:
            database.replace_lims_instance(import_id, raw, payload, COLLECTION_ORDER)
        return import_response(item)

    @router.get("/queries")
    def list_queries() -> list[dict]:
        return [import_response(item) for item in database.list_lims_imports()]

    @router.get("/imports/{import_id}/instances")
    def list_instances(import_id: str) -> list[dict]:
        return required_import(import_id)["summary"].get("instances", [])

    @router.get("/imports/{import_id}/instances/{instance_id}")
    def get_instance(import_id: str, instance_id: str) -> dict:
        item = required_import(import_id)
        try:
            return stored_instance(item, instance_id)
        except KeyError as error:
            raise HTTPException(404, "LIMS 实验实例不存在") from error

    @router.post("/imports/{import_id}/recognize")
    def recognize_instances(import_id: str, request: RecognizeLimsRequest) -> dict:
        item = required_import(import_id)
        try:
            instances = [normalized_instance(item, instance_id) for instance_id in request.instance_ids]
            return merge_instances(instances, normalized=True)
        except KeyError as error:
            raise HTTPException(404, f"LIMS 实验记录不存在：{error.args[0]}") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            raise HTTPException(422, f"LIMS 数据识别失败：{error}") from error

    @router.get("/imports/{import_id}/instances/{instance_id}/standard-records")
    def standard_records(import_id: str, instance_id: str) -> list[dict]:
        item = required_import(import_id)
        try:
            stored_instance(item, instance_id)
        except KeyError as error:
            raise HTTPException(404, "LIMS 实验记录不存在") from error
        return database.list_lims_standard_records(import_id, instance_id)

    return router
