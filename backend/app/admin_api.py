import hashlib
import logging
import time
import uuid
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from lxml import etree

from .config import Settings
from .database import now_iso
from .auth import AuthManager
from .onlyoffice_callback import (
    assert_document_server_url, callback_status, is_current_document_key, verified_callback_payload,
)
from .services.rule_admin import RuleAdminRepository
from .services.docx_control_index import control_locations, describe_binding
from .services.designer_blocks import designer_blocks
from .services.onlyoffice_force_save import (
    OnlyOfficeForceSaveError, request_onlyoffice_force_save, wait_for_file_update,
)
from .services.template_file_store import TemplateFileStore
from .services.template_mapping_reconciliation import mappings_for_removed_controls
from .admin_routes.protocol_rules import register_protocol_rule_routes
from .admin_routes.lims_rules import register_lims_rule_routes
from .admin_routes.rule_catalog import register_rule_catalog_routes
from .admin_routes.data_sources import register_data_source_routes
from .admin_routes.publishing import register_publishing_routes
from .admin_api_metadata import CHAPTER_TITLES, SECTION_TITLES, chapter_key


logger = logging.getLogger(__name__)


def create_admin_router(repository: RuleAdminRepository, settings: Settings, auth: AuthManager) -> APIRouter:
    router = APIRouter(
        prefix=f"{settings.api_prefix}/admin", tags=["后台管理系统"],
        dependencies=[Depends(auth.admin_route_guard)],
    )
    compiled_dir = settings.template_path.parent / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    file_store = TemplateFileStore(repository, settings.template_path)
    migrated_versions = file_store.migrate_legacy_published_versions()
    if migrated_versions:
        logger.info("已迁移历史发布模板到独立存储 migrated_versions=%s", migrated_versions)
    chapter_titles, section_titles = CHAPTER_TITLES, SECTION_TITLES

    def require_editable_workspace() -> dict[str, Any]:
        workspace = repository.active_workspace()
        if not workspace:
            raise ValueError("没有活动模板版本")
        if workspace["versionStatus"] != "DRAFT":
            raise ValueError("已发布或历史模板版本不可进入设计器，请先基于该版本新建草稿")
        return workspace

    def designer_payload() -> dict[str, Any]:
        mappings = repository.list_mappings()
        # 绑定状态以草稿文档为准：控件在 ONLYOFFICE 里被删掉后映射行还在，
        # 只看映射会把早已失效的绑定显示成正常的。
        workspace = repository.active_workspace()
        locations = control_locations(workspace.get("templateFile") if workspace else None)
        mappings = [{**item, **describe_binding(locations, str(item.get("controlTag") or ""))}
                    for item in mappings]
        standard_catalog = repository.standard_field_catalog()
        standard_groups = standard_catalog["groups"]
        chapter_rows = repository.list_template_chapters()
        table_rules = repository.list_table_rules()
        active = repository.active_workspace()
        configured_blocks = {
            row["standardGroupCode"]: row for row in repository.list_template_blocks(active["versionId"])
        } if active else {}
        # 历史 admin_content_blocks 不属于当前设计器结构。系统字段目录中的直属字段与
        # 标准编组统一装配为虚拟块，字段归属只取后端目录元数据。
        blocks_by_chapter, groups_by_chapter = designer_blocks(
            standard_catalog["chapters"], chapter_rows, standard_groups,
            mappings, configured_blocks, table_rules,
        )
        nodes = {row["id"]: {**row, "blocks": blocks_by_chapter.get(row["id"], []),
                              "standardGroups": groups_by_chapter.get(row["id"], []), "children": []} for row in chapter_rows}
        roots: list[dict[str, Any]] = []
        for node in nodes.values():
            if node.get("parentId") and node["parentId"] in nodes:
                nodes[node["parentId"]]["children"].append(node)
            else:
                roots.append(node)
        for node in nodes.values():
            node["children"].sort(key=lambda item: (item.get("orderNo", 0), item["id"]))
            node["blocks"].sort(key=lambda item: (item.get("orderNo", 0), item["id"]))
        return {
            "template": {"id": "primary-report-template",
                         "name": active.get("templateName") if active else settings.template_path.name,
                         "draftFile": file_store.active_draft_path().name,
                         "templateId": active.get("templateId") if active else None,
                         "templateName": active.get("templateName") if active else settings.template_path.name,
                         "versionId": active.get("versionId") if active else None,
                         "versionNo": active.get("versionNo") if active else 1,
                         "status": active.get("versionStatus", "DRAFT") if active else "DRAFT"},
            "chapters": roots,
            "summary": {"chapters": len(chapter_rows), "blocks": sum(len(value) for value in blocks_by_chapter.values()),
                        "mappings": len(mappings), "pending": sum(1 for item in mappings if item.get("sourcePending"))},
        }

    @router.get("/overview")
    def overview() -> dict[str, Any]:
        summary = repository.summary()
        summary["template"] = {
            "name": settings.template_path.name,
            "size": settings.template_path.stat().st_size if settings.template_path.exists() else 0,
            "exists": settings.template_path.exists(),
        }
        return summary

    @router.get("/templates")
    def list_templates() -> list[dict[str, Any]]:
        return repository.list_templates()

    @router.post("/templates")
    def create_template(item: dict[str, Any]) -> dict[str, Any]:
        if not str(item.get("name") or "").strip() or not str(item.get("code") or "").strip():
            raise HTTPException(422, "模板名称和编码不能为空")
        try:
            result = repository.create_template(item)
            version = repository.list_template_versions(result["id"])[0]
            file_store.initialize_version(str(version["id"]), settings.template_path)
            return result
        except Exception as error:
            raise HTTPException(400, f"创建模板失败：{error}") from error

    @router.post("/templates/with-file")
    async def create_template_with_file(
        code: str = Form(...), name: str = Form(...), description: str = Form(""),
        note: str = Form("初始草稿版本"), template_file: UploadFile = File(...),
    ) -> dict[str, Any]:
        if not code.strip() or not name.strip():
            raise HTTPException(422, "模板名称和编码不能为空")
        suffix = Path(template_file.filename or "").suffix.lower()
        if suffix not in {".docx", ".docm"}:
            raise HTTPException(422, "模板基座必须是 .docx 或 .docm 文件")
        upload_path = file_store.draft_dir / f"uploaded-{uuid.uuid4().hex}{suffix}"
        try:
            upload_path.write_bytes(await template_file.read())
            if upload_path.stat().st_size == 0:
                raise ValueError("上传的 Word 文件为空")
            result = repository.create_template(
                {"code": code.strip(), "name": name.strip(), "description": description.strip(), "note": note},
                template_file=str(upload_path),
            )
            version = repository.list_template_versions(result["id"])[0]
            file_store.initialize_version(str(version["id"]), upload_path)
            return result
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("创建带 Word 基座的模板失败")
            raise HTTPException(400, f"创建模板失败：{error}") from error

    @router.put("/templates/{template_id}")
    def update_template(template_id: str, item: dict[str, Any]) -> dict[str, Any]:
        result = repository.update_template(template_id, item)
        if not result:
            raise HTTPException(404, "模板不存在")
        return result

    @router.delete("/templates/{template_id}")
    def delete_template(template_id: str) -> dict[str, Any]:
        try:
            result = repository.delete_template(template_id)
            for version_id in result["versionIds"]:
                file_store.version_draft_path(str(version_id)).unlink(missing_ok=True)
            return {"deleted": True, **result}
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/templates/{template_id}/versions")
    def list_template_versions(template_id: str) -> list[dict[str, Any]]:
        return repository.list_template_versions(template_id)

    @router.post("/templates/{template_id}/versions")
    def create_template_version(template_id: str, item: dict[str, Any] | None = None) -> dict[str, Any]:
        options = item or {}
        try:
            result = repository.create_template_version(
                template_id, options.get("baseVersionId"), options.get("note", "新建草稿版本")
            )
            source = Path(result["templateFile"]) if result.get("templateFile") else settings.template_path
            file_store.initialize_version(str(result["id"]), source)
            return repository.get_template_version(str(result["id"])) or result
        except ValueError as error:
            raise HTTPException(404, str(error)) from error

    @router.delete("/templates/{template_id}/versions/{version_id}")
    def delete_template_version(template_id: str, version_id: str) -> dict[str, Any]:
        try:
            result = repository.delete_template_version(template_id, version_id)
            file_store.version_draft_path(version_id).unlink(missing_ok=True)
            return {"deleted": True, **result}
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/templates/{template_id}/versions/{version_id}/activate")
    def activate_template_version(template_id: str, version_id: str) -> dict[str, Any]:
        try:
            version = repository.get_template_version(version_id)
            if not version or version["templateId"] != template_id:
                raise ValueError("模板版本不存在")
            if version["status"] != "DRAFT":
                raise HTTPException(
                    409, "已发布或历史模板版本不可进入设计器，请先基于该版本新建草稿",
                )
            workspace = repository.activate_template_version(template_id, version_id)
            file_store.ensure_active_draft()
            # 切换活动版本后，该版本此前签发的文档 key 不再代表当前草稿
            repository.set_version_document_key(version_id, None)
            return workspace
        except ValueError as error:
            raise HTTPException(404, str(error)) from error

    @router.get("/designer")
    def template_designer() -> dict[str, Any]:
        try:
            require_editable_workspace()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        file_store.ensure_active_draft()
        return designer_payload()

    @router.get("/chapters")
    def list_chapters() -> list[dict[str, Any]]:
        return repository.list_template_chapters()

    @router.post("/chapters")
    def create_chapter(item: dict[str, Any]) -> dict[str, Any]:
        try:
            result = repository.create_template_chapter(item)
            repository.save_active_workspace()
            return result
        except Exception as error:
            raise HTTPException(400, f"创建章节失败：{error}") from error

    @router.put("/chapters/{chapter_id}")
    def update_chapter(chapter_id: int, item: dict[str, Any]) -> dict[str, Any]:
        result = repository.update_template_chapter(chapter_id, item)
        if not result:
            raise HTTPException(404, "章节不存在")
        repository.save_active_workspace()
        return result

    @router.delete("/chapters/{chapter_id}")
    def delete_chapter(chapter_id: int) -> dict[str, bool]:
        if not repository.delete_template_chapter(chapter_id):
            raise HTTPException(404, "章节不存在")
        repository.save_active_workspace()
        return {"deleted": True}

    @router.get("/content-blocks")
    def list_content_blocks() -> list[dict[str, Any]]:
        return repository.list_content_blocks()

    @router.put("/template-blocks/{group_code}")
    def save_template_block(group_code: str, item: dict[str, Any]) -> dict[str, Any]:
        active = repository.active_workspace()
        if not active:
            raise HTTPException(409, "没有活动模板版本")
        table = dict(item.get("tableRule") or {})
        # 标准编组的布局必须从嵌套 tableRule 统一落库；拒绝仅保存内容块而丢失表格规则。
        if table.get("mode") in {"MATRIX", "TABLE_REPEAT", "ROW_REPEAT"}:
            table["mode"] = str(table["mode"])
            uses_matrix = table["mode"] == "MATRIX" or (
                table["mode"] == "TABLE_REPEAT" and table.get("innerMode") == "MATRIX"
            )
            if uses_matrix and not str(table.get("matrixLayout") or "").strip():
                raise HTTPException(422, "矩阵填充必须配置矩阵布局")
            if table["mode"] == "TABLE_REPEAT" and not str(table.get("groupKey") or "").strip():
                raise HTTPException(422, "按分组复制整表必须配置整表分组字段")
            if table["mode"] == "TABLE_REPEAT":
                group = next((value for value in repository.standard_field_catalog().get("groups", [])
                              if value.get("groupCode") == group_code), None)
                allowed = {str(field.get("fieldPath") or field.get("jsonKey") or "")
                           for field in (group or {}).get("fields", [])
                           if field.get("enabled", True) and "[*]" not in str(field.get("fieldPath") or "")}
                if str(table.get("groupKey") or "") not in allowed:
                    raise HTTPException(422, "整表分组字段必须是当前编组记录自身的字段")
        table_no = str(table.get("tableNo") or next((str(row.get("tableNo") or "") for row in repository.list_mappings()
                                                     if str(row.get("standardFieldCode") or "").startswith(f"{group_code}.")
                                                     and str(row.get("tableNo") or "").startswith("T")), f"GROUP:{group_code}"))
        table = {**table, "tableNo": table_no}
        if not int(table.get("physicalTableIndex") or 0):
            tags = [str(row.get("controlTag") or "") for row in repository.list_mappings()
                    if str(row.get("standardFieldCode") or "").startswith(f"{group_code}.") and row.get("controlTag")]
            if tags:
                try:
                    with zipfile.ZipFile(file_store.ensure_active_draft()) as archive:
                        root = etree.fromstring(archive.read("word/document.xml"))
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    tables = root.xpath("./w:body/w:tbl", namespaces=ns)
                    for index, target in enumerate(tables, start=1):
                        if any(target.xpath(".//w:sdt[w:sdtPr/w:tag/@w:val=$tag]", namespaces=ns, tag=tag) for tag in tags):
                            table["physicalTableIndex"] = index
                            break
                except (OSError, KeyError, etree.XMLSyntaxError) as error:
                    logger.warning("模板表格自动识别失败 group=%s error=%s", group_code, error)
        # 标准编组的目录属性只读，模板版本仅保存布局配置。
        item = {"chapterId": item.get("chapterId"), "standardGroupCode": group_code,
                "tableNo": table_no, "title": item.get("title", ""),
                "kind": item.get("kind", "MAPPED_FIELD"), "orderNo": item.get("orderNo", 0),
                "enabled": item.get("enabled", True), "tableRule": table}
        try:
            if table.get("mode") in {"MATRIX", "TABLE_REPEAT"}:
                with repository.database.connect() as connection:
                    connection.execute(
                        "UPDATE admin_mapping_rules SET table_no=%s,repeat_type='ROW',repeat_key=%s,updated_at=%s "
                        "WHERE standard_field_code LIKE %s",
                        (table_no, table.get("recordKey", ""), now_iso(), f"{group_code}.%"),
                    )
            result = repository.save_template_block(active["versionId"], item)
            if table:
                saved_rule = repository.upsert_table_rule({**table, "tableNo": table_no})
                result["tableRule"] = saved_rule
            repository.save_active_workspace()
            return result
        except (KeyError, ValueError) as error:
            raise HTTPException(422, str(error)) from error

    @router.post("/content-blocks")
    def create_content_block(item: dict[str, Any]) -> dict[str, Any]:
        if not item.get("chapterId") or not str(item.get("title") or "").strip():
            raise HTTPException(422, "章节和内容块名称不能为空")
        try:
            result = repository.create_content_block(item)
            if item.get("kind") in {"REPEATING_TABLE", "MATRIX", "TABLE_REPEAT"} and item.get("tableNo"):
                if not any(rule["tableNo"] == item["tableNo"] for rule in repository.list_table_rules()):
                    repository.upsert_table_rule({
                        "tableNo": item["tableNo"], "sectionCode": "", "mode": item["kind"] if item["kind"] in {"MATRIX", "TABLE_REPEAT"} else "ROW_REPEAT",
                        "headerRows": 1, "dataRowStart": 2, "dataRowEnd": 2, "footerRows": 0,
                        "recordKey": item.get("repeatKey", ""), "mergeFields": [], "enabled": True, "notes": "",
                    })
            repository.save_active_workspace()
            return result
        except Exception as error:
            raise HTTPException(400, f"创建内容块失败：{error}") from error

    @router.put("/content-blocks/{block_id}")
    def update_content_block(block_id: int, item: dict[str, Any]) -> dict[str, Any]:
        result = repository.update_content_block(block_id, item)
        if not result:
            raise HTTPException(404, "内容块不存在")
        if item.get("kind") in {"REPEATING_TABLE", "MATRIX", "TABLE_REPEAT"} and item.get("tableNo"):
            existing = next((rule for rule in repository.list_table_rules() if rule["tableNo"] == item["tableNo"]), None)
            repository.upsert_table_rule({
                **(existing or {}), "tableNo": item["tableNo"], "sectionCode": (existing or {}).get("sectionCode", ""),
                "mode": item["kind"] if item["kind"] in {"MATRIX", "TABLE_REPEAT"} else "ROW_REPEAT",
                "headerRows": (existing or {}).get("headerRows", 1), "dataRowStart": (existing or {}).get("dataRowStart", 2),
                "dataRowEnd": (existing or {}).get("dataRowEnd", 2), "footerRows": (existing or {}).get("footerRows", 0),
                "recordKey": item.get("repeatKey", ""), "mergeFields": (existing or {}).get("mergeFields", []),
                "physicalTableIndex": (existing or {}).get("physicalTableIndex", 0),
                "preservedRowLabels": (existing or {}).get("preservedRowLabels", []),
                "clearEmbeddedObjects": (existing or {}).get("clearEmbeddedObjects", False),
                "matrixLayout": (existing or {}).get("matrixLayout", ""),
                "groupKey": (existing or {}).get("groupKey", ""),
                "innerMode": (existing or {}).get("innerMode", "ROW_REPEAT"),
                "enabled": (existing or {}).get("enabled", True), "notes": (existing or {}).get("notes", ""),
            })
        repository.save_active_workspace()
        return result

    @router.post("/chapters/{chapter_id}/content-blocks/reorder")
    def reorder_content_blocks(chapter_id: int, item: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            block_ids = [int(value) for value in item.get("blockIds", [])]
            result = repository.reorder_content_blocks(chapter_id, block_ids)
            repository.save_active_workspace()
            return result
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/content-blocks/{block_id}/mappings/reorder")
    def reorder_block_mappings(block_id: int, item: dict[str, Any]) -> dict[str, list[int]]:
        try:
            mapping_ids = [int(value) for value in item.get("mappingIds", [])]
            result = repository.reorder_block_mappings(block_id, mapping_ids)
            repository.save_active_workspace()
            return {"mappingIds": result}
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.delete("/content-blocks/{block_id}")
    def delete_content_block(block_id: int, delete_mappings: bool = True) -> dict[str, bool]:
        if not repository.delete_content_block(block_id, delete_mappings):
            raise HTTPException(404, "内容块不存在")
        repository.save_active_workspace()
        return {"deleted": True}

    @router.get("/template/file/{version_id}")
    def version_template_file(version_id: str, document_token: str = "") -> FileResponse:
        if not settings.onlyoffice_jwt_secret or not document_token:
            raise HTTPException(401, "ONLYOFFICE 模板访问缺少签名")
        try:
            claims = jwt.decode(document_token, settings.onlyoffice_jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError as error:
            raise HTTPException(401, "ONLYOFFICE 模板访问签名无效") from error
        if claims.get("purpose") != "template-file" or claims.get("versionId") != version_id:
            raise HTTPException(403, "ONLYOFFICE 模板访问签名不匹配")
        version = repository.get_template_version(version_id)
        if not version or version["status"] != "DRAFT":
            raise HTTPException(409, "已发布模板不可进入编辑器，请创建新的草稿版本")
        try:
            path = file_store.ensure_version_draft(version_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            filename=settings.template_path.name)

    @router.get("/template/file")
    def template_file() -> FileResponse:
        path = file_store.ensure_active_draft()
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            filename=settings.template_path.name)

    @router.get("/onlyoffice/config")
    def template_onlyoffice_config() -> dict[str, Any]:
        if not settings.onlyoffice_jwt_secret:
            raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请通过 start.ps1 启动服务")
        try:
            workspace = require_editable_workspace()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        if not workspace:
            raise HTTPException(409, "没有活动模板版本")
        version_id = str(workspace["versionId"])
        path = file_store.ensure_active_draft()
        file_token = jwt.encode(
            {"purpose": "template-file", "versionId": version_id, "exp": int(time.time()) + 600},
            settings.onlyoffice_jwt_secret, algorithm="HS256",
        )
        # 同一编辑会话内文件每次自动保存都会更新 mtime；key 不能随文件变化，
        # 否则旧会话的后续回调会被误判为陈旧。模板被替换时由初始化流程主动清空 key。
        key = str(workspace.get("documentKey") or "")
        if not key:
            signature = f"admin-template:{version_id}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
            key = hashlib.sha256(signature.encode()).hexdigest()[:20]
            repository.set_version_document_key(version_id, key)
        config: dict[str, Any] = {
            "document": {"fileType": "docx", "key": key, "title": settings.template_path.name,
                         "url": (f"{settings.public_base_url}{settings.api_prefix}/admin/template/file/{version_id}"
                                 f"?document_token={file_token}"),
                         "permissions": {"edit": True, "download": True, "print": True, "review": True}},
            "documentType": "word",
            "editorConfig": {
                "callbackUrl": f"{settings.public_base_url}{settings.api_prefix}/admin/onlyoffice/callback/{version_id}",
                "lang": "zh-CN", "mode": "edit", "user": {"id": "template-admin", "name": "模板管理员"},
                "customization": {"autosave": True, "forcesave": True, "compactHeader": True},
                "plugins": {
                    "autostart": ["asc.{B75A5F24-8D2C-4E91-A763-6C98B8B80A15}"],
                    "pluginsData": [
                        f"{settings.onlyoffice_url}/sdkjs-plugins/"
                        "%7BB75A5F24-8D2C-4E91-A763-6C98B8B80A15%7D/config.json?v=22"
                    ],
                },
            },
            "height": "100%", "width": "100%", "type": "desktop",
        }
        config["token"] = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
        return {"documentServerUrl": settings.onlyoffice_url, "config": config}

    @router.post("/onlyoffice/force-save")
    def template_onlyoffice_force_save() -> dict[str, Any]:
        workspace = repository.active_workspace()
        if not workspace:
            raise HTTPException(409, "没有活动模板版本")
        if workspace["versionStatus"] != "DRAFT":
            raise HTTPException(409, "已发布模板不可保存，请创建新的草稿版本")
        version_id = str(workspace["versionId"])
        path = file_store.ensure_version_draft(version_id)
        signature = f"admin-template:{version_id}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
        document_key = str(workspace.get("documentKey") or "")
        if not document_key:
            document_key = hashlib.sha256(signature.encode()).hexdigest()[:20]
        before = path.stat().st_mtime_ns
        try:
            save_requested = request_onlyoffice_force_save(
                settings.onlyoffice_url, settings.onlyoffice_jwt_secret, document_key, version_id,
            )
        except OnlyOfficeForceSaveError as error:
            raise HTTPException(502, f"请求 ONLYOFFICE 保存模板失败：{error}") from error
        if not save_requested:
            return {"saved": False, "versionId": version_id}
        try:
            wait_for_file_update(path, before)
        except TimeoutError as error:
            raise HTTPException(504, "Word 绑定已完成，但模板保存回调超时，请稍后重试") from error
        return {"saved": True, "versionId": version_id}

    @router.post("/onlyoffice/callback/{version_id}")
    async def template_onlyoffice_callback(version_id: str, request: Request) -> dict[str, int]:
        payload = await verified_callback_payload(request, settings)
        if callback_status(payload) not in (2, 6):
            return {"error": 0}
        assert_document_server_url(payload.get("url"), settings)
        version = repository.get_template_version(version_id)
        if not version or version["status"] != "DRAFT":
            logger.warning("ONLYOFFICE 模板回调目标不是草稿版本，拒绝保存 version_id=%s", version_id)
            return {"error": 1}
        callback_key = str(payload.get("key") or "")
        if not callback_key:
            raise HTTPException(400, "ONLYOFFICE 回调缺少文档 key")
        workspace = repository.active_workspace()
        issued_key = str(workspace.get("documentKey") or "") if workspace else ""
        # key 必须等于最近一次签发值，且版本仍是活动版本：挡住陈旧会话与跨版本重放
        if not workspace or workspace["versionId"] != version_id:
            logger.warning("ONLYOFFICE 模板回调版本已失效，拒绝保存 version_id=%s", version_id)
            return {"error": 1}
        if not is_current_document_key(issued_key, callback_key):
            # 一个版本可能被多个设计器会话同时打开。旧会话的自动保存不能覆盖
            # 当前会话刚写入的草稿，否则已创建的内容控件会在页面刷新后消失。
            logger.warning("ONLYOFFICE 模板回调 key 已过期，拒绝保存 version_id=%s", version_id)
            return {"error": 1}
        if not payload.get("url"):
            raise HTTPException(400, "ONLYOFFICE 回调缺少文件地址")
        try:
            output = file_store.ensure_version_draft(version_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        # 唯一临时名：并发的保存不能互相截断对方的半截文件
        temporary = output.with_name(f"{output.name}.{uuid.uuid4().hex[:8]}.saving.docx")
        try:
            with urllib.request.urlopen(payload["url"], timeout=60) as response, temporary.open("wb") as target:
                target.write(response.read())
            previous_tags = set(control_locations(output))
            current_tags = set(control_locations(temporary))
            removed_mappings = mappings_for_removed_controls(
                repository.list_mappings(), previous_tags, current_tags,
            )
            temporary.replace(output)
            repository.set_version_document_key(version_id, callback_key)
            repository.set_template_version_file(version_id, str(output))
            for mapping in removed_mappings:
                repository.delete_mapping(int(mapping["id"]))
            if removed_mappings:
                repository.save_active_workspace()
                logger.info(
                    "ONLYOFFICE 草稿控件删除后已同步清理映射 version_id=%s mapping_ids=%s control_tags=%s",
                    version_id,
                    [mapping["id"] for mapping in removed_mappings],
                    [mapping["controlTag"] for mapping in removed_mappings],
                )
        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise HTTPException(502, f"保存模板失败：{error}") from error
        return {"error": 0}

    register_rule_catalog_routes(router, repository)
    register_lims_rule_routes(router)
    register_protocol_rule_routes(router, repository, settings)
    register_data_source_routes(router, repository)
    register_publishing_routes(
        router, repository, file_store.ensure_active_draft, file_store.publish_version, compiled_dir,
    )

    return router
