import hashlib
import logging
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from .auth import AuthManager
from .config import Settings
from .database import Database, now_iso
from .onlyoffice_callback import assert_document_server_url, callback_status, verified_callback_payload
from .services.docx_export import export_docx_response
from .services.docx_validation import validate_docx_document
from .services.onlyoffice_force_save import (
    OnlyOfficeForceSaveError, request_onlyoffice_force_save, wait_for_file_update,
)

logger = logging.getLogger(__name__)


def create_report_word_router(
    database: Database, settings: Settings, auth: AuthManager,
    required_report: Callable[[str], dict[str, Any]],
    required_owned_report: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    def document_key(report_id: str, path: Path) -> str:
        document_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        return f"{report_id}-{document_hash}"

    @router.get(f"{settings.api_prefix}/reports/{{report_id}}/file")
    def download_report(report_id: str, document_token: str = "",
                        user: dict | None = Depends(auth.optional_user)) -> Response:
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
        if not signed_access:
            return export_docx_response(path, item["title"])
        return export_docx_response(path, item["title"])


    def ensure_report_file(item: dict) -> tuple[dict, Path]:
        path = settings.reports_dir / f"report-{item['id']}-working.docx"
        if not path.exists():
            raise HTTPException(409, "报告工作文件不存在，请先重新生成报告")
        return item, path


    @router.get(f"{settings.api_prefix}/onlyoffice/reports/{{report_id}}/config")
    def onlyoffice_config(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict:
        if not settings.onlyoffice_jwt_secret:
            raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请设置 REPORT_ONLYOFFICE_JWT_SECRET")
        item = required_owned_report(report_id, user)
        try:
            item, path = ensure_report_file(item)
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("ONLYOFFICE 工作文档准备失败 report_id=%s", report_id)
            raise HTTPException(422, f"报告文档准备失败：{error}") from error
        file_token = jwt.encode(
            {"purpose": "report-file", "reportId": report_id, "exp": int(time.time()) + 600},
            settings.onlyoffice_jwt_secret, algorithm="HS256",
        )
        # 文档 key 含文件内容哈希，每次签发后必须落库：回调用它识别当前编辑会话，
        # 而不是与保存后的文件内容重新比较（那样第二次自动保存起就会被误判为陈旧）
        doc_key = document_key(report_id, path)
        item = database.update_report(report_id, onlyoffice_document_key=doc_key)
        config = {
            "document": {
                "fileType": "docx",
                "key": doc_key,
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
                "customization": {
                    "autosave": True, "forcesave": True, "compactHeader": False,
                    "goback": {"requestClose": True, "text": "返回报告大厅"},
                },
            },
            "height": "100%",
            "width": "100%",
            "type": "desktop",
        }
        config["token"] = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
        return {"documentServerUrl": settings.onlyoffice_url, "config": config}


    @router.post(f"{settings.api_prefix}/onlyoffice/reports/{{report_id}}/force-save")
    def onlyoffice_force_save(
        report_id: str, user: dict = Depends(auth.require("REPORT_EDIT")),
    ) -> dict[str, Any]:
        if not settings.onlyoffice_jwt_secret:
            raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请设置 REPORT_ONLYOFFICE_JWT_SECRET")
        item = required_owned_report(report_id, user)
        _, path = ensure_report_file(item)
        document_key = str(item.get("onlyoffice_document_key") or "")
        if not document_key:
            raise HTTPException(409, "报告编辑器会话不存在，请重新打开报告后再编辑")
        before = path.stat().st_mtime_ns
        logger.info("请求 ONLYOFFICE 强制保存 report_id=%s", report_id)
        try:
            save_requested = request_onlyoffice_force_save(
                settings.onlyoffice_url, settings.onlyoffice_jwt_secret, document_key, report_id,
            )
        except OnlyOfficeForceSaveError as error:
            logger.exception("请求 ONLYOFFICE 强制保存失败 report_id=%s", report_id)
            raise HTTPException(502, f"报告保存失败：{error}") from error
        if not save_requested:
            logger.info("ONLYOFFICE 没有待保存改动 report_id=%s", report_id)
            return {"saved": False, "reportId": report_id}
        try:
            wait_for_file_update(path, before)
        except TimeoutError as error:
            logger.error("ONLYOFFICE 报告保存回调超时 report_id=%s", report_id)
            raise HTTPException(504, "报告保存回调超时，已保留当前编辑页面，请重试") from error
        logger.info("ONLYOFFICE 强制保存完成 report_id=%s", report_id)
        return {"saved": True, "reportId": report_id}


    @router.post(f"{settings.api_prefix}/onlyoffice/callback/{{report_id}}")
    async def onlyoffice_callback(report_id: str, request: Request) -> dict:
        payload = await verified_callback_payload(request, settings)
        status = callback_status(payload)
        if status not in (2, 6):
            return {"error": 0}
        assert_document_server_url(payload.get("url"), settings)
        item = required_report(report_id)
        callback_key = str(payload.get("key") or "")
        if not callback_key:
            raise HTTPException(400, "ONLYOFFICE 回调缺少文档 key")
        if not payload.get("url"):
            raise HTTPException(400, "ONLYOFFICE 回调缺少文件地址")
        _, output = ensure_report_file(item)
        # key 必须等于最近一次签发值：既挡住跨报告重放，也挡住陈旧编辑会话的延迟保存。
        # 必须在文件存在性检查后重新读取，避免并发重建已清空签发记录时仍接受旧回调。
        refreshed = database.get_report(report_id)
        issued_key = str((refreshed or {}).get("onlyoffice_document_key") or "")
        if not issued_key or callback_key != issued_key:
            logger.warning("ONLYOFFICE 回调文档 key 与签发记录不一致，拒绝保存 report_id=%s", report_id)
            return {"error": 1}
        # 唯一临时名：并发的自动保存不能互相截断对方的半截文件
        temp_path = output.with_name(f"{output.name}.{uuid.uuid4().hex[:8]}.saving.docx")
        started_at = time.monotonic()
        try:
            with urllib.request.urlopen(payload["url"], timeout=60) as response, temp_path.open("wb") as target:
                target.write(response.read())
            downloaded_at = time.monotonic()
            validate_docx_document(
                temp_path, settings.max_upload_mb * 1024 * 1024, "ONLYOFFICE 报告 DOCX 文件",
            )
            validated_at = time.monotonic()
            temp_path.replace(output)
            database.update_report(
                report_id, status="EDITING", word_edit_locked=1, word_edited_at=now_iso(),
            )
            completed_at = time.monotonic()
        except Exception as error:
            temp_path.unlink(missing_ok=True)
            logger.exception(
                "ONLYOFFICE 报告回调处理失败 report_id=%s elapsedMs=%d",
                report_id, int((time.monotonic() - started_at) * 1000),
            )
            raise HTTPException(502, f"保存 ONLYOFFICE 文件失败：{error}") from error
        elapsed_ms = int((completed_at - started_at) * 1000)
        callback_log = logger.warning if elapsed_ms >= 2000 else logger.info
        callback_log(
            "ONLYOFFICE 报告回调完成 report_id=%s downloadMs=%d validateMs=%d persistMs=%d totalMs=%d",
            report_id,
            int((downloaded_at - started_at) * 1000),
            int((validated_at - downloaded_at) * 1000),
            int((completed_at - validated_at) * 1000),
            elapsed_ms,
        )
        return {"error": 0}

    return router
