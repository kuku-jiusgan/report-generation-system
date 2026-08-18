from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from .auth import AuthManager
from .config import Settings
from .database import Database
from .report_utils import resolved_report_title
from .schemas import ReplaceSourceRequest, ReportTask
from .services.report_source_replacement import replace_report_source


def create_report_source_router(
    database: Database, settings: Settings, auth: AuthManager,
    required_owned_report: Callable[[str, dict[str, Any]], dict[str, Any]],
    report_response: Callable[[dict[str, Any]], ReportTask],
    render_report_word: Callable[..., str],
) -> APIRouter:
    router = APIRouter()

    @router.post(f"{settings.api_prefix}/reports/{{report_id}}/replace-source", response_model=ReportTask)
    def replace_source(
        report_id: str, request: ReplaceSourceRequest,
        user: dict = Depends(auth.require("REPORT_EDIT")),
    ) -> ReportTask:
        item = required_owned_report(report_id, user)
        source = database.get_source(request.source_document_id)
        if not source:
            raise HTTPException(404, "新数据源不存在")
        if source.get("source_type") != request.source_type:
            raise HTTPException(422, "新数据源类型与替换类型不一致")
        if request.source_type == "EXCEL" and not source.get("payload"):
            raise HTTPException(422, "Excel 尚未完成解析")
        if request.source_type == "PDF" and not source.get("extracted_fields"):
            raise HTTPException(422, "PDF 尚未完成解析")
        data = replace_report_source(dict(item["resolved_data"]), source, request.source_type, settings.api_prefix)
        try:
            output_name = render_report_word(item, data)
        except Exception as error:
            raise HTTPException(500, f"更换数据源后重新生成报告失败：{error}") from error
        updated = database.update_report(
            report_id, title=resolved_report_title(item.get("title"), data), resolved_data=data,
            status="EDITING", output_name=output_name, updated_by=user["id"],
            word_edit_locked=0, word_edited_at=None,
            **({"source_document_id": source["id"]} if request.source_type == "PDF" else {}),
        )
        database.create_version(report_id, data, f"更换 {request.source_type} 数据源：{source['file_name']}")
        return report_response(updated)

    return router
