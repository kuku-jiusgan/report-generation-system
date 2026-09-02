import hashlib
import json
import logging
import shutil
import time
import uuid
import urllib.request
from pathlib import Path
from typing import Any

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from .config import Settings
from .auth import AuthManager
from .onlyoffice_callback import assert_document_server_url, callback_status, verified_callback_payload
from .services.rule_admin import RuleAdminRepository
from .services.system_field_groups import list_system_field_groups
from .services.lims_normalizer import merge_instances
from .services.template_compiler import compile_template
from .services.docx_language import ensure_simplified_chinese
from .admin_routes.rule_catalog import register_rule_catalog_routes


logger = logging.getLogger(__name__)


def create_admin_router(repository: RuleAdminRepository, settings: Settings, auth: AuthManager) -> APIRouter:
    router = APIRouter(
        prefix=f"{settings.api_prefix}/admin", tags=["后台管理系统"],
        dependencies=[Depends(auth.admin_route_guard)],
    )
    compiled_dir = settings.template_path.parent / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    draft_dir = settings.template_path.parent / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)

    chapter_titles = {
        "cover": "封面、审批与目录", "3": "3 实验设计", "4": "4 实验材料",
        "5": "5 验证项目与接受标准", "6": "6 仪器方法", "7": "7 实验过程与结果",
        "8": "8 样品检测结果", "version": "版本记录", "other": "其他内容",
    }
    section_titles = {
        "header": "页眉与文件信息", "approval": "审批信息", "toc": "目录",
        "3.2.limit": "3.2 杂质限度", "3.3.impurity": "3.3 杂质信息",
        "4.1.samples": "4.1 供试品", "4.2.referenceStandards": "4.2 对照品",
        "4.3.instruments": "4.3 仪器", "4.3.columns": "4.4 色谱柱",
        "4.5.reagents": "4.5 试剂", "5.validationSummary": "5 验证项目与接受标准",
        "6.methodParameters": "6 仪器方法参数", "7.1.solutions": "7.1 系统适用性溶液",
        "7.1.systemSuitability": "7.1 系统适用性结果", "7.2.solutions": "7.2 专属性溶液",
        "7.2.specificity": "7.2 专属性结果", "7.3.lodSolutions": "7.3 检出限与定量限溶液",
        "7.3.lod": "7.3 检出限结果", "7.3.loq": "7.3 定量限结果",
        "7.4.linearityPreparation": "7.4 线性溶液", "7.4.linearity": "7.4 线性结果",
        "7.5.solutions": "7.5 重复性溶液", "7.5.repeatability": "7.5 重复性结果",
        "7.6.solutions": "7.6 中间精密度溶液", "7.6.linearityPreparation": "7.6 中间精密度线性溶液",
        "7.6.linearity": "7.6 中间精密度线性结果", "7.6.intermediatePrecision": "7.6 中间精密度结果",
        "7.7.solutions": "7.7 准确度溶液", "7.7.blankAmount": "7.7 空白本底",
        "7.7.accuracy": "7.7 准确度结果", "7.8.solutions": "7.8 稳定性溶液",
        "7.8.solutionStability": "7.8 溶液稳定性结果", "7.9.solutions": "7.9 耐用性溶液",
        "7.9.robustnessSpecificity": "7.9 耐用性专属性", "7.9.robustnessSolutions": "7.9 耐用性溶液配置",
        "7.9.robustnessSequence": "7.9 耐用性序列", "7.9.robustnessResult": "7.9 耐用性结果",
        "8.sampleResults": "8 样品检测结果", "versionHistory": "版本记录",
        "cover": "封面", "narrative": "目的、概述与总结", "attachment": "附件",
    }

    def version_draft_template(version_id: str) -> Path:
        return draft_dir / f"report-template-{version_id}.docx"

    def active_draft_template() -> Path:
        workspace = repository.active_workspace()
        version_id = workspace["versionId"] if workspace else "default"
        return version_draft_template(version_id)

    def ensure_version_draft_template(version_id: str) -> Path:
        draft_template = version_draft_template(version_id)
        if draft_template.exists():
            ensure_simplified_chinese(draft_template)
            return draft_template
        version = repository.get_template_version(version_id)
        if not version:
            raise ValueError("模板版本不存在")
        stored_file = Path(version["templateFile"]) if version.get("templateFile") else None
        if stored_file and stored_file.exists() and stored_file.resolve() != draft_template.resolve():
            shutil.copy2(stored_file, draft_template)
        else:
            shutil.copy2(settings.template_path, draft_template)
        repository.set_template_version_file(version_id, str(draft_template))
        ensure_simplified_chinese(draft_template)
        return draft_template

    def ensure_draft_template() -> Path:
        workspace = repository.active_workspace()
        if not workspace:
            return settings.template_path
        return ensure_version_draft_template(workspace["versionId"])

    def initialize_version_document(version_id: str, source: Path) -> Path:
        if not source.exists():
            source = settings.template_path
        target = version_draft_template(version_id)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        repository.set_template_version_file(version_id, str(target))
        # 文档已被替换为非编辑器内容，此前签发的文档 key 全部失效
        repository.set_version_document_key(version_id, None)
        return target

    def chapter_key(section_code: str) -> str:
        if section_code in {"header", "approval", "toc", "cover", "narrative"}:
            return "cover"
        if section_code == "versionHistory":
            return "version"
        prefix = section_code.split(".", 1)[0]
        return prefix if prefix in {"3", "4", "5", "6", "7", "8"} else "other"

    def block_kind(items: list[dict[str, Any]], table: dict[str, Any] | None) -> str:
        sources = {item.get("sourceType") for item in items}
        if sources == {"FIXED"}:
            return "FIXED"
        if table and table.get("mode") == "TABLE_REPEAT":
            return "TABLE_REPEAT"
        if table and table.get("mode") == "MATRIX":
            return "MATRIX"
        if table or any(item.get("repeatType") not in {"", "NONE"} for item in items):
            return "REPEATING_TABLE"
        if "AI" in sources:
            return "AI_NARRATIVE"
        if "CALCULATED" in sources:
            return "CALCULATED"
        return "MAPPED_FIELD"

    def designer_payload() -> dict[str, Any]:
        mappings = repository.list_mappings()
        standard_groups = list_system_field_groups(repository.database)
        chapter_rows = repository.list_template_chapters()
        table_rules = repository.list_table_rules()
        active = repository.active_workspace()
        configured_blocks = {
            row["standardGroupCode"]: row for row in repository.list_template_blocks(active["versionId"])
        } if active else {}
        # 内容块由系统标准编组装配。历史 admin_content_blocks 不属于模板设计器的
        # 当前结构，不能在绑定字段后抢占标准编组展示位置。
        blocks_by_chapter: dict[int, list[dict[str, Any]]] = {}
        groups_by_chapter: dict[int, list[dict[str, Any]]] = {}
        for group in standard_groups:
            for chapter_id in group.get("chapterIds", []):
                groups_by_chapter.setdefault(int(chapter_id), []).append(group)
        # 系统标准编组是设计器的内容块来源；不依赖已删除的历史内容块记录。
        for chapter_id, groups in groups_by_chapter.items():
            for index, group in enumerate(groups):
                codes = {field["fieldCode"] for field in group.get("fields", [])}
                # 标准编组是系统目录定义的虚拟块；字段绑定应以标准字段编码为唯一归属，
                # 不因版本恢复时章节关系表缺失而显示为“未绑定”。
                items = [item for item in mappings if item.get("standardFieldCode") in codes
                         and (item.get("chapterId") == chapter_id or not item.get("chapterId"))]
                configured = configured_blocks.get(group["groupCode"], {})
                table = next((rule for rule in table_rules
                              if rule.get("tableNo") == configured.get("tableNo")
                              and rule.get("groupKey") == group["groupCode"]), None)
                block_kind = configured.get("kind") or "MAPPED_FIELD"
                blocks_by_chapter.setdefault(chapter_id, []).append({
                    "id": -(chapter_id * 1000 + index + 1), "chapterId": chapter_id,
                    "title": configured.get("title") or group["label"], "kind": block_kind,
                    "tableNo": configured.get("tableNo", ""),
                    "standardGroupCode": group["groupCode"], "standardFields": group.get("fields", []),
                    "orderNo": configured.get("orderNo", index), "sourcePath": configured.get("sourcePath") or group.get("itemPath", ""),
                    "repeatKey": configured.get("repeatKey") or group.get("itemKey", ""),
                    "prototypeLocation": configured.get("prototypeLocation", ""),
                    "dedupKey": configured.get("dedupKey", ""), "sortRule": configured.get("sortRule", ""),
                    "emptyBehavior": configured.get("emptyBehavior", "KEEP"), "mergeRule": configured.get("mergeRule", "NONE"),
                    "enabled": configured.get("enabled", group.get("enabled", True)), "mappingIds": [item["id"] for item in items],
                    "controlTags": [item.get("controlTag") for item in items if item.get("controlTag")],
                    "sources": sorted({item.get("sourceType") for item in items if item.get("sourceType")} ),
                    "status": "READY" if configured else "UNCONFIGURED", "mappings": items, "tableRule": table,
                })
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
                         "draftFile": active_draft_template().name,
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
            initialize_version_document(str(version["id"]), settings.template_path)
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
        upload_path = draft_dir / f"uploaded-{uuid.uuid4().hex}{suffix}"
        try:
            upload_path.write_bytes(await template_file.read())
            if upload_path.stat().st_size == 0:
                raise ValueError("上传的 Word 文件为空")
            result = repository.create_template(
                {"code": code.strip(), "name": name.strip(), "description": description.strip(), "note": note},
                template_file=str(upload_path),
            )
            version = repository.list_template_versions(result["id"])[0]
            initialize_version_document(str(version["id"]), upload_path)
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
                version_draft_template(str(version_id)).unlink(missing_ok=True)
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
            initialize_version_document(str(result["id"]), source)
            return repository.get_template_version(str(result["id"])) or result
        except ValueError as error:
            raise HTTPException(404, str(error)) from error

    @router.delete("/templates/{template_id}/versions/{version_id}")
    def delete_template_version(template_id: str, version_id: str) -> dict[str, Any]:
        try:
            result = repository.delete_template_version(template_id, version_id)
            version_draft_template(version_id).unlink(missing_ok=True)
            return {"deleted": True, **result}
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/templates/{template_id}/versions/{version_id}/activate")
    def activate_template_version(template_id: str, version_id: str) -> dict[str, Any]:
        try:
            workspace = repository.activate_template_version(template_id, version_id)
            ensure_draft_template()
            # 切换活动版本后，该版本此前签发的文档 key 不再代表当前草稿
            repository.set_version_document_key(version_id, None)
            return workspace
        except ValueError as error:
            raise HTTPException(404, str(error)) from error

    @router.get("/designer")
    def template_designer() -> dict[str, Any]:
        ensure_draft_template()
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
        table = item.get("tableRule") or {}
        table_no = str(table.get("tableNo") or "")
        # 标准编组的目录属性只读，模板版本仅保存布局配置。
        item = {"chapterId": item.get("chapterId"), "standardGroupCode": group_code,
                "tableNo": table_no, "title": item.get("title", ""),
                "kind": item.get("kind", "MAPPED_FIELD"), "orderNo": item.get("orderNo", 0),
                "enabled": item.get("enabled", True), "tableRule": table}
        try:
            result = repository.save_template_block(active["versionId"], item)
            if table and table_no:
                repository.upsert_table_rule({**table, "tableNo": table_no, "groupKey": group_code})
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
        try:
            path = ensure_version_draft_template(version_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            filename=settings.template_path.name)

    @router.get("/template/file")
    def template_file() -> FileResponse:
        path = ensure_draft_template()
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            filename=settings.template_path.name)

    @router.get("/onlyoffice/config")
    def template_onlyoffice_config() -> dict[str, Any]:
        if not settings.onlyoffice_jwt_secret:
            raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请通过 start.ps1 启动服务")
        workspace = repository.active_workspace()
        if not workspace:
            raise HTTPException(409, "没有活动模板版本")
        version_id = str(workspace["versionId"])
        path = ensure_draft_template()
        file_token = jwt.encode(
            {"purpose": "template-file", "versionId": version_id, "exp": int(time.time()) + 600},
            settings.onlyoffice_jwt_secret, algorithm="HS256",
        )
        signature = f"admin-template:{version_id}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
        key = hashlib.sha256(signature.encode()).hexdigest()[:20]
        # 文档 key 基于文件 mtime/size，保存一次后即变化，必须落库供回调比对，
        # 否则第二次自动保存起都会被误判为陈旧会话而丢弃
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
                        "%7BB75A5F24-8D2C-4E91-A763-6C98B8B80A15%7D/config.json?v=18"
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
        version_id = str(workspace["versionId"])
        path = ensure_version_draft_template(version_id)
        signature = f"admin-template:{version_id}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
        document_key = str(workspace.get("documentKey") or "")
        if not document_key:
            document_key = hashlib.sha256(signature.encode()).hexdigest()[:20]
        before = path.stat().st_mtime_ns
        command: dict[str, Any] = {"c": "forcesave", "key": document_key, "userdata": version_id}
        command["token"] = jwt.encode(command, settings.onlyoffice_jwt_secret, algorithm="HS256")
        request = urllib.request.Request(
            f"{settings.onlyoffice_url.rstrip('/')}/coauthoring/CommandService.ashx",
            data=json.dumps(command).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as error:
            raise HTTPException(502, f"请求 ONLYOFFICE 保存模板失败：{error}") from error
        error_code = int(result.get("error", -1))
        if error_code not in (0, 4):
            raise HTTPException(502, f"ONLYOFFICE 保存模板失败，错误码：{result.get('error')}")
        if error_code == 4:
            return {"saved": False, "versionId": version_id}
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if path.exists() and path.stat().st_mtime_ns > before:
                return {"saved": True, "versionId": version_id}
            time.sleep(0.25)
        raise HTTPException(504, "Word 绑定已完成，但模板保存回调超时，请稍后重试")

    @router.post("/onlyoffice/callback/{version_id}")
    async def template_onlyoffice_callback(version_id: str, request: Request) -> dict[str, int]:
        payload = await verified_callback_payload(request, settings)
        if callback_status(payload) not in (2, 6):
            return {"error": 0}
        assert_document_server_url(payload.get("url"), settings)
        callback_key = str(payload.get("key") or "")
        if not callback_key:
            raise HTTPException(400, "ONLYOFFICE 回调缺少文档 key")
        workspace = repository.active_workspace()
        issued_key = str(workspace.get("documentKey") or "") if workspace else ""
        # key 必须等于最近一次签发值，且版本仍是活动版本：挡住陈旧会话与跨版本重放
        if not workspace or workspace["versionId"] != version_id:
            logger.warning("ONLYOFFICE 模板回调版本已失效，拒绝保存 version_id=%s", version_id)
            return {"error": 1}
        if issued_key and callback_key != issued_key:
            # 文档被编辑后，OnlyOffice 可能为回调生成新的 key；版本校验仍保证不会跨版本写入。
            logger.info("ONLYOFFICE 模板回调 key 已轮换 version_id=%s", version_id)
        if not payload.get("url"):
            raise HTTPException(400, "ONLYOFFICE 回调缺少文件地址")
        try:
            output = ensure_version_draft_template(version_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        # 唯一临时名：并发的保存不能互相截断对方的半截文件
        temporary = output.with_name(f"{output.name}.{uuid.uuid4().hex[:8]}.saving.docx")
        try:
            with urllib.request.urlopen(payload["url"], timeout=60) as response, temporary.open("wb") as target:
                target.write(response.read())
            temporary.replace(output)
            repository.set_version_document_key(version_id, callback_key)
            repository.set_template_version_file(version_id, str(output))
        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise HTTPException(502, f"保存模板失败：{error}") from error
        return {"error": 0}

    register_rule_catalog_routes(router, repository)

    @router.get("/data-sources")
    def list_data_sources() -> list[dict[str, Any]]:
        return repository.list_data_sources()

    @router.post("/lims-recognition-test")
    def test_lims_recognition(item: dict[str, Any]) -> dict[str, Any]:
        imported = repository.database.get_lims_import(str(item.get("importId") or ""))
        if not imported:
            raise HTTPException(404, "LIMS 导入记录不存在")
        instance_ids = [str(value) for value in item.get("instanceIds", []) if value]
        if not instance_ids:
            raise HTTPException(422, "至少选择一个实验记录")
        try:
            instances = []
            for value in instance_ids:
                payload = repository.database.get_lims_normalized_payload(imported["id"], value)
                if payload is None:
                    raise KeyError(value)
                instances.append(payload)
            return merge_instances(instances, normalized=True)
        except (KeyError, ValueError) as error:
            raise HTTPException(422, str(error)) from error

    @router.put("/data-sources/{code}")
    def update_data_source(code: str, item: dict[str, Any]) -> dict[str, Any]:
        item["code"] = code
        return repository.upsert_data_source(item)

    @router.get("/ai-rules")
    def list_ai_rules() -> list[dict[str, Any]]:
        return repository.list_ai_rules()

    @router.post("/ai-rules")
    def create_ai_rule(item: dict[str, Any]) -> dict[str, Any]:
        result = repository.upsert_ai_rule(item)
        repository.save_active_workspace()
        return result

    @router.put("/ai-rules/{field_code:path}")
    def update_ai_rule(field_code: str, item: dict[str, Any]) -> dict[str, Any]:
        item["fieldCode"] = field_code
        result = repository.upsert_ai_rule(item)
        repository.save_active_workspace()
        return result

    @router.delete("/ai-rules/{rule_id}")
    def delete_ai_rule(rule_id: int) -> dict[str, bool]:
        if not repository.delete_ai_rule(rule_id):
            raise HTTPException(404, "AI规则不存在")
        repository.save_active_workspace()
        return {"deleted": True}

    @router.post("/ai-rules/test")
    def test_ai_rule(item: dict[str, Any]) -> dict[str, Any]:
        inputs = item.get("sampleInputs", {})
        missing = [field for field in item.get("inputFields", []) if field not in inputs]
        if missing:
            return {"success": False, "missingInputs": missing, "output": "", "citations": []}
        facts = "；".join(f"{key}={value}" for key, value in inputs.items())
        return {
            "success": True,
            "mock": True,
            "output": f"[AI提供方尚未配置] 已接收结构化事实：{facts}",
            "citations": list(inputs),
            "message": "当前仅验证输入、提示词和输出约束；配置模型提供方后执行真实生成。",
        }

    def run_compile() -> tuple[Path, dict[str, Any]]:
        snapshot = repository.snapshot()
        output = compiled_dir / f"report-template-bound-{uuid.uuid4().hex[:8]}.docx"
        report = compile_template(ensure_draft_template(), output, snapshot["mappings"], snapshot["tableRules"])
        return output, report

    @router.post("/validate")
    def validate_rules() -> dict[str, Any]:
        output, report = run_compile()
        report["previewTemplate"] = output.name
        return report

    @router.post("/publish")
    def publish_rules(item: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            output, report = run_compile()
            if not report["valid"]:
                raise HTTPException(422, {"message": "规则校验失败，不能发布", "validation": report})
            snapshot = repository.snapshot()
            workspace = repository.active_workspace()
            version_file = active_draft_template()
            shutil.copy2(output, version_file)
            # 保留当前 OnlyOffice 会话的 document key。发布后继续在同一编辑器中绑定字段时，
            # 强制保存仍需使用该 key；回调保存成功后会按实际回调 key 更新它。
            return repository.publish_active_template_version(snapshot, report, str(version_file))
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(500, f"发布模板版本失败：{error}") from error

    @router.get("/versions")
    def list_versions() -> list[dict[str, Any]]:
        active = repository.active_workspace()
        return repository.list_template_versions(active["templateId"]) if active else []

    @router.get("/compiled/{file_name}")
    def download_compiled(file_name: str) -> FileResponse:
        safe_name = Path(file_name).name
        path = compiled_dir / safe_name
        if not path.exists() or path.parent.resolve() != compiled_dir.resolve():
            raise HTTPException(404, "编译模板不存在")
        return FileResponse(path, filename=safe_name)

    return router
