import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from .config import Settings
from .auth import AuthManager
from .database import Database, now_iso
from .schemas import RecognizeLimsRequest
from .services.lims_excel import parse_lims_workbook
from .services.lims_normalizer import COLLECTION_ORDER, merge_instances, normalize_instance


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

    def persist_import(item: dict) -> None:
        path = settings.lims_dir / item["stored_name"]
        for summary in item["summary"].get("instances", []):
            instance_id = str(summary["instanceId"])
            if database.get_lims_instance_payload(item["id"], instance_id):
                continue
            raw = parse_lims_workbook(path, instance_id)
            database.replace_lims_instance(
                item["id"], raw,
                normalize_instance(raw, database.list_lims_fields(), database.list_lims_extraction_rules()),
                COLLECTION_ORDER,
            )

    def stored_instance(item: dict, instance_id: str) -> dict:
        payload = database.get_lims_instance_payload(item["id"], instance_id)
        if payload:
            return payload
        persist_import(item)
        payload = database.get_lims_instance_payload(item["id"], instance_id)
        if not payload:
            raise KeyError(instance_id)
        return payload

    @router.get("/capabilities")
    def capabilities() -> dict:
        return {
            "sqlEnabled": settings.lims_sql_enabled,
            "sqlConfigured": bool(settings.lims_sql_dsn.strip()),
            "excelImportEnabled": settings.lims_excel_import_enabled,
        }

    @router.get("/imports")
    def list_imports() -> list[dict]:
        return [import_response(item) for item in database.list_lims_imports()]

    @router.post("/imports")
    async def upload_import(file: UploadFile = File(...)) -> dict:
        if not settings.lims_excel_import_enabled:
            raise HTTPException(403, "当前环境已关闭 Excel 导入")
        original_name = Path(file.filename or "").name
        if Path(original_name).suffix.lower() != ".xlsx":
            raise HTTPException(400, "仅支持 SQL 查询结果的 .xlsx 文件")
        import_id = uuid.uuid4().hex
        stored_name = f"{import_id}.xlsx"
        target = settings.lims_dir / stored_name
        size = 0
        max_bytes = settings.max_upload_mb * 1024 * 1024
        try:
            with target.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb} MB")
                    output.write(chunk)
            summary = parse_lims_workbook(target)
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        except Exception as error:
            target.unlink(missing_ok=True)
            raise HTTPException(422, f"LIMS Excel 解析失败：{error}") from error
        item = database.create_lims_import({"id": import_id, "file_name": original_name, "stored_name": stored_name,
                                            "size": size, "summary": summary, "created_at": now_iso()})
        persist_import(item)
        return import_response(item)

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
            instances = [stored_instance(item, instance_id) for instance_id in request.instance_ids]
            return merge_instances(
                instances, fields=database.list_lims_fields(),
                extraction_rules=database.list_lims_extraction_rules(),
            )
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
