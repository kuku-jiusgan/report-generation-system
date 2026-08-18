import hashlib
import json
import shutil
import time
import urllib.request
import logging
from pathlib import Path
from typing import Any, Callable

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .auth import AuthManager
from .config import Settings
from .database import Database, now_iso
from .report_utils import has_custom_report_title, resolved_report_title
from .services.rule_admin import RuleAdminRepository
from .services.word_sync import read_bound_values

logger = logging.getLogger(__name__)


def create_report_word_router(
    database: Database, settings: Settings, auth: AuthManager, rule_admin: RuleAdminRepository,
    required_report: Callable[[str], dict[str, Any]],
    required_owned_report: Callable[[str, dict[str, Any]], dict[str, Any]],
    runtime_template_and_mappings: Callable[[], tuple[Path, list[dict], dict[str, str]]],
    render_report_word: Callable[..., str],
    require_automatic_edit_allowed: Callable[[dict[str, Any]], None],
    apply_content_block_rules: Callable[[dict], list[dict]],
) -> APIRouter:
    router = APIRouter()

    def document_key(report_id: str, path: Path) -> str:
        document_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        return f"{report_id}-{document_hash}"

    _apply_content_block_rules = apply_content_block_rules
    @router.get(f"{settings.api_prefix}/reports/{{report_id}}/file")
    def download_report(report_id: str, document_token: str = "",
                        user: dict | None = Depends(auth.optional_user)) -> FileResponse:
        item = required_report(report_id)
        signed_access = False
        if document_token and settings.onlyoffice_jwt_secret:
            try:
                claims = jwt.decode(document_token, settings.onlyoffice_jwt_secret, algorithms=["HS256"])
                signed_access = claims.get("purpose") == "report-file" and claims.get("reportId") == report_id
            except jwt.PyJWTError:
                signed_access = False
        if not signed_access:
            if not user:
                raise HTTPException(401, "请先登录")
            if "REPORT_DOWNLOAD" not in user["permissions"] or item.get("created_by") != user["id"]:
                raise HTTPException(404, "报告不存在")
        if not item.get("output_name"):
            raise HTTPException(409, "请先生成报告")
        path = settings.reports_dir / f"report-{report_id}-working.docx"
        if not path.exists():
            raise HTTPException(404, "报告文件不存在")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{item['title']}.docx",
        )


    def ensure_report_file(item: dict) -> tuple[dict, Path]:
        working_name = f"report-{item['id']}-working.docx"
        path = settings.reports_dir / working_name
        previous_name = item.get("output_name")
        previous_path = settings.reports_dir / previous_name if previous_name else None
        _, _, template_meta = runtime_template_and_mappings()
        template_changed = item["resolved_data"].get("template_revision") != template_meta["template_revision"]
        metadata_changed = any(item["resolved_data"].get(key) != value for key, value in template_meta.items())
        if template_changed and not item.get("word_edit_locked"):
            output_name = render_report_word(item, item["resolved_data"])
            item = database.update_report(
                item["id"], status="EDITING", output_name=output_name,
                resolved_data=item["resolved_data"],
            )
            return item, settings.reports_dir / output_name
        if metadata_changed and not item.get("word_edit_locked"):
            item["resolved_data"].update(template_meta)
            item = database.update_report(item["id"], resolved_data=item["resolved_data"])
        if not path.exists() and previous_path and previous_path.exists() and previous_path != path:
            shutil.copy2(previous_path, path)
        if not path.exists():
            require_automatic_edit_allowed(item)
            output_name = render_report_word(item, item["resolved_data"])
            path = settings.reports_dir / output_name
        if item.get("output_name") != working_name:
            item = database.update_report(item["id"], status="EDITING", output_name=working_name)
        return item, path


    def ensure_editable_report_file(item: dict) -> tuple[dict, Path]:
        return ensure_report_file(item)


    def sync_word_fields(item: dict, path: Path) -> dict:
        snapshot, _ = rule_admin.active_runtime_rules()
        mappings = _apply_content_block_rules(snapshot)
        bound_values, canonical_values = read_bound_values(path, mappings)
        data = dict(item["resolved_data"])
        old_word = data.get("source_payloads", {}).get("WORD", {}).get("boundValues", {})
        sources = dict(data.get("field_sources", {}))
        originals = dict(data.get("original_values", {}))
        for code, value in canonical_values.items():
            old_value = str(data.get(code) or "")
            if old_value != value:
                database.add_change(item["id"], code, old_value, value, "ONLYOFFICE", "Word 人工编辑")
            data[code] = value
            sources[code] = {"type": "MANUAL_WORD", "record_id": "ONLYOFFICE"}
            originals[code] = value
        for code, value in bound_values.items():
            sources[code] = {"type": "MANUAL_WORD", "record_id": "ONLYOFFICE"}
            if code in canonical_values:
                continue
            before = old_word.get(code, "") if isinstance(old_word, dict) else ""
            if before != value:
                database.add_change(
                    item["id"], code,
                    json.dumps(before, ensure_ascii=False) if isinstance(before, list) else str(before),
                    json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value),
                    "ONLYOFFICE", "Word 人工编辑",
                )
        data["field_sources"] = sources
        data["original_values"] = originals
        source_payloads = dict(data.get("source_payloads", {}))
        source_payloads["WORD"] = {"boundValues": bound_values}
        data["source_payloads"] = source_payloads
        title = item["title"] if has_custom_report_title(item) else resolved_report_title(None, data)
        return database.update_report(
            item["id"], title=title, resolved_data=data, status="EDITING",
            word_edit_locked=1, word_edited_at=now_iso(),
        )


    @router.get(f"{settings.api_prefix}/onlyoffice/reports/{{report_id}}/config")
    def onlyoffice_config(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict:
        if not settings.onlyoffice_jwt_secret:
            raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请设置 REPORT_ONLYOFFICE_JWT_SECRET")
        item = required_owned_report(report_id, user)
        try:
            item, path = ensure_editable_report_file(item)
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("ONLYOFFICE 工作文档准备失败 report_id=%s", report_id)
            raise HTTPException(422, f"报告文档准备失败：{error}") from error
        file_token = jwt.encode(
            {"purpose": "report-file", "reportId": report_id, "exp": int(time.time()) + 600},
            settings.onlyoffice_jwt_secret, algorithm="HS256",
        )
        config = {
            "document": {
                "fileType": "docx",
                "key": document_key(report_id, path),
                "title": f"{item['resolved_data'].get('report_no') or item['title']}.docx",
                "url": f"{settings.public_base_url}{settings.api_prefix}/reports/{report_id}/file?document_token={file_token}",
                "permissions": {"edit": True, "download": True, "print": True, "review": True},
            },
            "documentType": "word",
            "editorConfig": {
                "callbackUrl": f"{settings.public_base_url}{settings.api_prefix}/onlyoffice/callback/{report_id}",
                "lang": "zh-CN",
                "mode": "edit",
                "user": {"id": user["id"], "name": user["display_name"]},
                "customization": {"autosave": True, "forcesave": True, "compactHeader": False},
                "plugins": {
                    "autostart": ["asc.{B75A5F24-8D2C-4E91-A763-6C98B8B80A15}"],
                    "pluginsData": [
                        f"{settings.onlyoffice_url}/sdkjs-plugins/"
                        "%7BB75A5F24-8D2C-4E91-A763-6C98B8B80A15%7D/config.json?v=18"
                    ],
                },
            },
            "height": "100%",
            "width": "100%",
            "type": "desktop",
        }
        config["token"] = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
        return {"documentServerUrl": settings.onlyoffice_url, "config": config}


    @router.post(f"{settings.api_prefix}/onlyoffice/callback/{{report_id}}")
    async def onlyoffice_callback(report_id: str, request: Request) -> dict:
        item = required_report(report_id)
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

        status = int(payload.get("status", 0))
        if status in (2, 6) and payload.get("url"):
            _, output = ensure_report_file(item)
            callback_key = str(payload.get("key") or "")
            if callback_key and callback_key != document_key(report_id, output):
                return {"error": 0}
            temp_path = output.with_suffix(".saving.docx")
            try:
                with urllib.request.urlopen(payload["url"], timeout=60) as response, temp_path.open("wb") as target:
                    target.write(response.read())
                # Validate and extract controls before replacing the known-good working file.
                snapshot, _ = rule_admin.active_runtime_rules()
                read_bound_values(temp_path, _apply_content_block_rules(snapshot))
                temp_path.replace(output)
                updated = sync_word_fields(item, output)
                database.create_version(report_id, updated["resolved_data"], "ONLYOFFICE 自动保存")
            except Exception as error:
                temp_path.unlink(missing_ok=True)
                raise HTTPException(502, f"保存 ONLYOFFICE 文件失败：{error}") from error
        return {"error": 0}

    return router
