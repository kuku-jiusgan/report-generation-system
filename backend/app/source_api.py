import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .auth import AuthManager
from .config import Settings
from .database import Database, now_iso
from .schemas import SourceDocument
from .services.protocol_document import PROTOCOL_MEDIA_TYPE, validate_protocol_document
from .services.protocol_extractor import extract_protocol
from .services.pdf_extractor import extract_pdf
from .services.excel_field_extractor import extract_excel_fields
from .services.system_field_group_assembler import apply_group_contracts
from .services.system_field_groups import list_system_field_groups


logger = logging.getLogger(__name__)


def create_source_router(
    database: Database, settings: Settings, auth: AuthManager,
    source_response: Callable[[dict[str, Any]], SourceDocument],
) -> APIRouter:
    router = APIRouter()

    @router.post(f"{settings.api_prefix}/source-documents", response_model=SourceDocument)
    async def upload_source(
        file: UploadFile = File(...), user: dict = Depends(auth.require("REPORT_EDIT")),
    ) -> SourceDocument:
        del user
        original_name = Path(file.filename or "").name
        suffix = Path(original_name).suffix.lower()
        source_types = {".pdf": "PDF", ".xlsx": "EXCEL", ".xlsm": "EXCEL", ".docx": "PROTOCOL"}
        if suffix not in source_types:
            raise HTTPException(400, "仅支持 PDF、XLSX、XLSM 或 DOCX 文件；Word 方案请另存为 DOCX")
        source_type = source_types[suffix]
        source_id, stored_name = uuid.uuid4().hex, ""
        stored_name = f"{source_id}{suffix}"
        target, size = settings.uploads_dir / stored_name, 0
        max_bytes = settings.max_upload_mb * 1024 * 1024
        try:
            with target.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb} MB")
                    output.write(chunk)
            if not size:
                raise HTTPException(400, "上传文件不能为空")
            if source_type == "PROTOCOL":
                try:
                    validate_protocol_document(target, max_bytes)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from error
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        except Exception as error:
            target.unlink(missing_ok=True)
            logger.exception("保存来源文件失败 source_id=%s source_type=%s", source_id, source_type)
            raise HTTPException(500, "文件保存失败，请重试或联系管理员") from error
        logger.info("上传来源文件 source_id=%s source_type=%s size=%s", source_id, source_type, size)
        item = database.create_source({
            "id": source_id, "file_name": original_name, "stored_name": stored_name,
            "size": size, "source_type": source_type,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "created_at": now_iso(),
        })
        return source_response(item)

    @router.get(f"{settings.api_prefix}/source-documents/{{source_id}}/preview")
    def preview_source(
        source_id: str, user: dict = Depends(auth.require("REPORT_EDIT")),
    ) -> FileResponse:
        del user
        item = database.get_source(source_id)
        if not item:
            raise HTTPException(404, "源文件不存在")
        media_type = (PROTOCOL_MEDIA_TYPE if item.get("source_type") == "PROTOCOL" else
                      "application/pdf" if item.get("source_type") == "PDF" else
                      "application/vnd.ms-excel.sheet.macroEnabled.12")
        return FileResponse(settings.uploads_dir / item["stored_name"], media_type=media_type,
                            filename=item["file_name"])

    @router.post(f"{settings.api_prefix}/source-documents/{{source_id}}/extract", response_model=SourceDocument)
    def extract_source(
        source_id: str, user: dict = Depends(auth.require("REPORT_EDIT")),
    ) -> SourceDocument:
        del user
        item = database.get_source(source_id)
        if not item:
            raise HTTPException(404, "源文件不存在")
        try:
            if item.get("source_type") == "PROTOCOL":
                payload = extract_protocol(settings.uploads_dir / item["stored_name"], source_id,
                    database.list_lims_fields(True), database.list_system_field_rules(),
                    list_system_field_groups(database), settings.max_upload_mb * 1024 * 1024)
                updated = database.update_source_payload(source_id, payload, payload['_meta']['warnings'], item['sha256'])
                return source_response(updated)
            if item.get("source_type") == "EXCEL":
                groups = list_system_field_groups(database)
                payload = extract_excel_fields(
                    settings.uploads_dir / item["stored_name"], database.list_lims_fields(True),
                    database.list_system_field_rules(), groups,
                )
                # Excel 解析结果在落库前即固定为标准字段目录结构，报告创建阶段只复制该结果。
                apply_group_contracts(payload, groups)
                meta = payload.get("_meta", {})
                updated = database.update_source_payload(
                    source_id, payload, list(meta.get("warnings", [])), str(meta.get("sha256", "")),
                )
                return source_response(updated)
            fields = extract_pdf(settings.uploads_dir / item["stored_name"], source_id,
                                 database.list_lims_fields(True), database.list_system_field_rules())
        except Exception as error:
            kind = {"EXCEL": "Excel", "PROTOCOL": "方案", "PDF": "PDF"}.get(item.get("source_type"), "来源文件")
            raise HTTPException(422, f"{kind} 解析失败：{error}") from error
        return source_response(database.update_extracted_fields(source_id, fields))

    return router
