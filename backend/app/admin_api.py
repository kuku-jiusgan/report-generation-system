import hashlib
import re
import shutil
import time
import uuid
import urllib.request
from pathlib import Path
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .config import Settings
from .auth import AuthManager
from .services.rule_admin import RuleAdminRepository
from .services.lims_excel import parse_lims_workbook
from .services.lims_normalizer import merge_instances
from .services.template_compiler import compile_template


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
        chapter_rows = repository.list_template_chapters()
        tables = {item["tableNo"]: item for item in repository.list_table_rules()}
        mappings_by_id = {item["id"]: item for item in mappings}
        blocks_by_chapter: dict[int, list[dict[str, Any]]] = {}
        for block in repository.list_content_blocks():
            chapter_id = int(block["chapterId"])
            items = [mappings_by_id[item_id] for item_id in block["mappingIds"] if item_id in mappings_by_id]
            table = tables.get(block.get("tableNo", ""))
            enabled = [item for item in items if item.get("enabled")]
            pending = [item for item in enabled if item.get("sourcePending")]
            blocks_by_chapter.setdefault(chapter_id, []).append({
                "id": block["id"], "chapterId": chapter_id, "title": block["title"],
                "kind": block["kind"], "tableNo": block.get("tableNo", ""), "orderNo": block["orderNo"],
                "sourcePath": block.get("sourcePath", ""), "repeatKey": block.get("repeatKey", ""),
                "prototypeLocation": block.get("prototypeLocation", ""), "dedupKey": block.get("dedupKey", ""),
                "sortRule": block.get("sortRule", ""), "emptyBehavior": block.get("emptyBehavior", "KEEP"),
                "mergeRule": block.get("mergeRule", "NONE"),
                "enabled": block["enabled"], "mappingIds": [item["id"] for item in items],
                "controlTags": [item.get("controlTag") for item in items if item.get("controlTag")],
                "sources": sorted({item.get("sourceType") for item in items if item.get("sourceType")}),
                "status": "DISABLED" if not block["enabled"] else ("PENDING" if pending or not items else "READY"),
                "mappings": items, "tableRule": table,
            })
        nodes = {row["id"]: {**row, "blocks": blocks_by_chapter.get(row["id"], []), "children": []} for row in chapter_rows}
        roots: list[dict[str, Any]] = []
        for node in nodes.values():
            if node.get("parentId") and node["parentId"] in nodes:
                nodes[node["parentId"]]["children"].append(node)
            else:
                roots.append(node)
        for node in nodes.values():
            node["children"].sort(key=lambda item: (item.get("orderNo", 0), item["id"]))
            node["blocks"].sort(key=lambda item: (item.get("orderNo", 0), item["id"]))
        active = repository.active_workspace()
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

    @router.post("/templates/{template_id}/versions/{version_id}/activate")
    def activate_template_version(template_id: str, version_id: str) -> dict[str, Any]:
        try:
            workspace = repository.activate_template_version(template_id, version_id)
            ensure_draft_template()
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

    @router.post("/content-blocks")
    def create_content_block(item: dict[str, Any]) -> dict[str, Any]:
        if not item.get("chapterId") or not str(item.get("title") or "").strip():
            raise HTTPException(422, "章节和内容块名称不能为空")
        try:
            result = repository.create_content_block(item)
            if item.get("kind") in {"REPEATING_TABLE", "MATRIX"} and item.get("tableNo"):
                if not any(rule["tableNo"] == item["tableNo"] for rule in repository.list_table_rules()):
                    repository.upsert_table_rule({
                        "tableNo": item["tableNo"], "sectionCode": "", "mode": "MATRIX" if item["kind"] == "MATRIX" else "ROW_REPEAT",
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
        if item.get("kind") in {"REPEATING_TABLE", "MATRIX"} and item.get("tableNo"):
            existing = next((rule for rule in repository.list_table_rules() if rule["tableNo"] == item["tableNo"]), None)
            repository.upsert_table_rule({
                **(existing or {}), "tableNo": item["tableNo"], "sectionCode": (existing or {}).get("sectionCode", ""),
                "mode": "MATRIX" if item["kind"] == "MATRIX" else "ROW_REPEAT",
                "headerRows": (existing or {}).get("headerRows", 1), "dataRowStart": (existing or {}).get("dataRowStart", 2),
                "dataRowEnd": (existing or {}).get("dataRowEnd", 2), "footerRows": (existing or {}).get("footerRows", 0),
                "recordKey": item.get("repeatKey", ""), "mergeFields": (existing or {}).get("mergeFields", []),
                "enabled": True, "notes": (existing or {}).get("notes", ""),
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
                    "autostart": ["asc.{9C4D6F33-55AE-4AAE-8D86-4B81D7229F10}"],
                    "pluginsData": [f"{settings.public_base_url}{settings.api_prefix}/admin/onlyoffice/plugin/config.json"],
                },
            },
            "height": "100%", "width": "100%", "type": "desktop",
        }
        config["token"] = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
        return {"documentServerUrl": settings.onlyoffice_url, "config": config}

    @router.get("/onlyoffice/plugin/config.json")
    def template_link_plugin_config() -> dict[str, Any]:
        return {
            "name": "Report Template Link",
            "guid": "asc.{9C4D6F33-55AE-4AAE-8D86-4B81D7229F10}",
            "version": "1.0.0",
            "variations": [{
                "description": "Links Word content controls with report template mapping rules.",
                "url": "index.html",
                "isViewer": True, "EditorsSupport": ["word"], "isVisual": False, "isModal": False,
                "isInsideMode": False, "initDataType": "none", "initOnSelectionChanged": True,
            }],
        }

    @router.get("/onlyoffice/plugin/index.html", response_class=HTMLResponse)
    def template_link_plugin_index() -> str:
        script_url = f"{settings.onlyoffice_url}/sdkjs-plugins/v1/plugins.js"
        bridge_url = f"{settings.public_base_url}/onlyoffice-template-link/link.js?v=4"
        return ("<!doctype html><html><head><meta charset='utf-8'>"
                f"<script src='{script_url}'></script></head>"
                f"<body><script src='{bridge_url}'></script></body></html>")

    word_command: dict[str, Any] = {"nonce": 0}

    @router.post("/onlyoffice/command")
    def submit_word_command(item: dict[str, Any]) -> dict[str, Any]:
        if item.get("type") not in {"bind", "unbind"}:
            raise HTTPException(422, "不支持的 Word 操作")
        nonce = int(item.get("nonce") or 0)
        if nonce <= int(word_command.get("nonce") or 0):
            nonce = int(word_command.get("nonce") or 0) + 1
        word_command.clear()
        word_command.update(item, nonce=nonce)
        return {"accepted": True, "nonce": nonce}

    @router.get("/onlyoffice/command")
    def poll_word_command(after: int = 0) -> dict[str, Any] | None:
        return dict(word_command) if int(word_command.get("nonce") or 0) > after else None

    @router.post("/onlyoffice/callback/{version_id}")
    async def template_onlyoffice_callback(version_id: str, request: Request) -> dict[str, int]:
        payload = await request.json()
        token = payload.get("token")
        authorization = request.headers.get("authorization", "")
        if not token and authorization.lower().startswith("bearer "):
            token = authorization[7:]
        if settings.onlyoffice_jwt_secret:
            if not token:
                raise HTTPException(401, "ONLYOFFICE 回调缺少签名")
            try:
                jwt.decode(token, settings.onlyoffice_jwt_secret, algorithms=["HS256"])
            except jwt.PyJWTError as error:
                raise HTTPException(401, "ONLYOFFICE 回调签名无效") from error
        if int(payload.get("status", 0)) in (2, 6) and payload.get("url"):
            try:
                output = ensure_version_draft_template(version_id)
            except ValueError as error:
                raise HTTPException(404, str(error)) from error
            temporary = output.with_suffix(".saving.docx")
            try:
                with urllib.request.urlopen(payload["url"], timeout=60) as response, temporary.open("wb") as target:
                    target.write(response.read())
                temporary.replace(output)
                repository.set_template_version_file(version_id, str(output))
            except Exception as error:
                temporary.unlink(missing_ok=True)
                raise HTTPException(502, f"保存模板失败：{error}") from error
        return {"error": 0}

    @router.get("/mappings")
    def list_mappings(search: str = "", table_no: str = "", source_type: str = "") -> list[dict[str, Any]]:
        return repository.list_mappings(search, table_no, source_type)

    @router.get("/standard-fields")
    def list_standard_fields(include_disabled: bool = False) -> list[dict[str, Any]]:
        return repository.database.list_lims_fields(include_disabled)

    @router.get("/standard-field-catalog")
    def standard_field_catalog(include_disabled: bool = True) -> dict[str, Any]:
        return repository.standard_field_catalog(include_disabled)

    def validate_standard_field(item: dict[str, Any], original_code: str = "") -> dict[str, Any]:
        field_code = str(item.get("fieldCode") or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", field_code):
            raise HTTPException(422, "标准字段编码只能使用英文字母、数字、点和下划线，且必须以字母开头")
        if not str(item.get("label") or "").strip():
            raise HTTPException(422, "标准字段名称不能为空")
        if item.get("validationRegex"):
            try:
                re.compile(str(item["validationRegex"]))
            except re.error as error:
                raise HTTPException(422, f"校验正则无效：{error}") from error
        existing = repository.database.get_lims_field(field_code)
        if existing and field_code != original_code:
            raise HTTPException(409, "标准字段编码已存在")
        return {**item, "fieldCode": field_code, "label": str(item["label"]).strip()}

    @router.post("/standard-fields")
    def create_standard_field(item: dict[str, Any]) -> dict[str, Any]:
        return repository.database.upsert_lims_field(validate_standard_field(item))

    @router.put("/standard-fields/{field_code:path}")
    def update_standard_field(field_code: str, item: dict[str, Any]) -> dict[str, Any]:
        existing = repository.database.get_lims_field(field_code)
        if not existing:
            raise HTTPException(404, "标准字段不存在")
        updated = validate_standard_field({**existing, **item}, field_code)
        if updated["fieldCode"] != field_code:
            raise HTTPException(422, "字段编码创建后不能修改；请新建字段并迁移模板引用")
        return repository.database.upsert_lims_field(updated)

    @router.delete("/standard-fields/{field_code:path}")
    def delete_standard_field(field_code: str) -> dict[str, bool]:
        with repository.database.connect() as connection:
            used = connection.execute(
                "SELECT COUNT(*) FROM admin_mapping_rules WHERE standard_field_code=?", (field_code,)
            ).fetchone()[0]
        if used:
            raise HTTPException(409, f"该标准字段正被 {used} 个模板字段引用，请先停用或迁移引用")
        if not repository.database.delete_lims_field(field_code):
            raise HTTPException(404, "标准字段不存在")
        return {"deleted": True}

    @router.get("/standard-fields/{field_code:path}/preview")
    def preview_standard_field(field_code: str, limit: int = 12, instance_ids: str = "") -> dict[str, Any]:
        field = repository.database.get_lims_field(field_code)
        if not field:
            raise HTTPException(404, "标准字段不存在")
        selected = [value.strip() for value in instance_ids.split(",") if value.strip()]
        return repository.database.preview_lims_field(field, limit, selected)

    @router.get("/standard-field-source")
    def standard_field_source(field_code: str, import_id: str, instance_id: str,
                              record_key: str = "") -> dict[str, Any]:
        field = repository.database.get_lims_field(field_code)
        if not field:
            raise HTTPException(404, "标准字段不存在")
        result = repository.database.get_lims_field_instance_source(
            field, import_id, instance_id,
        )
        if not result:
            raise HTTPException(404, "LIMS 实验实例不存在")
        return result

    def validate_extraction_rule(item: dict[str, Any]) -> dict[str, Any]:
        if not repository.database.get_lims_field(str(item.get("fieldCode") or "")):
            raise HTTPException(422, "提取规则关联的标准字段不存在")
        if not str(item.get("name") or "").strip():
            raise HTTPException(422, "提取规则名称不能为空")
        for key, label in (("sectionPattern", "章节"), ("headerPattern", "表头"),
                           ("valuePattern", "取值")):
            if item.get(key):
                try:
                    re.compile(str(item[key]))
                except re.error as error:
                    raise HTTPException(422, f"{label}正则无效：{error}") from error
        config = item.get("config") or {}
        parser = str(config.get("parser") or "") if isinstance(config, dict) else ""
        allowed_parsers = {"", "NORMALIZED_JSON", "INSTANCE_FIELD", "STRUCTURED_UNIT", "HTML_TABLE_GRID"}
        if parser not in allowed_parsers:
            raise HTTPException(422, f"不支持的解析器：{parser}")
        if parser == "HTML_TABLE_GRID" and not str(config.get("parserProfile") or "").strip():
            raise HTTPException(422, "HTML 表格解析规则必须指定解析配置")
        return item

    @router.get("/standard-fields/{field_code:path}/extraction-rules")
    def list_extraction_rules(field_code: str) -> list[dict[str, Any]]:
        return repository.database.list_lims_extraction_rules(field_code)

    @router.post("/standard-fields/{field_code:path}/extraction-rules")
    def create_extraction_rule(field_code: str, item: dict[str, Any]) -> dict[str, Any]:
        return repository.database.save_lims_extraction_rule(
            validate_extraction_rule({**item, "fieldCode": field_code})
        )

    @router.put("/extraction-rules/{rule_id}")
    def update_extraction_rule(rule_id: int, item: dict[str, Any]) -> dict[str, Any]:
        try:
            return repository.database.save_lims_extraction_rule(
                validate_extraction_rule(item), rule_id
            )
        except KeyError as error:
            raise HTTPException(404, "提取规则不存在") from error

    @router.delete("/extraction-rules/{rule_id}")
    def delete_extraction_rule(rule_id: int) -> dict[str, bool]:
        if not repository.database.delete_lims_extraction_rule(rule_id):
            raise HTTPException(404, "提取规则不存在")
        return {"deleted": True}

    def resolve_standard_field(item: dict[str, Any]) -> None:
        code = str(item.get("standardFieldCode") or "")
        if not code:
            return
        field = next((value for value in repository.database.list_lims_fields()
                      if value["fieldCode"] == code), None)
        if not field:
            raise HTTPException(422, "标准字段不存在或已停用")
        item["sourcePath"] = field["legacyJsonPath"]

    @router.post("/mappings")
    def create_mapping(item: dict[str, Any]) -> dict[str, Any]:
        try:
            resolve_standard_field(item)
            result = repository.create_mapping(item)
            repository.save_active_workspace()
            return result
        except Exception as error:
            raise HTTPException(400, f"创建映射失败：{error}") from error

    @router.put("/mappings/{rule_id}")
    def update_mapping(rule_id: int, item: dict[str, Any]) -> dict[str, Any]:
        resolve_standard_field(item)
        result = repository.update_mapping(rule_id, item)
        if not result:
            raise HTTPException(404, "映射规则不存在")
        repository.save_active_workspace()
        return result

    @router.delete("/mappings/{rule_id}")
    def delete_mapping(rule_id: int) -> dict[str, bool]:
        if not repository.delete_mapping(rule_id):
            raise HTTPException(404, "映射规则不存在")
        repository.save_active_workspace()
        return {"deleted": True}

    @router.get("/table-rules")
    def list_table_rules() -> list[dict[str, Any]]:
        return repository.list_table_rules()

    @router.put("/table-rules/{table_no}")
    def update_table_rule(table_no: str, item: dict[str, Any]) -> dict[str, Any]:
        item["tableNo"] = table_no.upper()
        result = repository.upsert_table_rule(item)
        repository.save_active_workspace()
        return result

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
            instances = [parse_lims_workbook(settings.lims_dir / imported["stored_name"], value)
                         for value in instance_ids]
            return merge_instances(instances)
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
        options = item or {}
        output, report = run_compile()
        if not report["valid"]:
            raise HTTPException(422, {"message": "规则校验失败，不能发布", "validation": report})
        snapshot = repository.snapshot()
        return repository.publish_active_template_version(snapshot, report, str(output))

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
