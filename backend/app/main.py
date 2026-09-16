import io
import logging
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Database, now_iso
from .admin_api import create_admin_router
from .auth import AuthManager, create_auth_router
from .management_api import create_management_router
from .lims_api import create_lims_router
from .schemas import (
    ChangeEvent,
    CreateReportRequest,
    FieldBinding,
    ReportTask,
    ReportVersion,
    SourceDocument,
    UpdateReportRequest,
)
logger = logging.getLogger(__name__)
from .services.mapped_docx_generator import build_mapped_docx
from .services.docx_export import export_docx_bytes, export_docx_response, write_export_docx
from .services.system_field_resolver import resolve_system_fields
from .services.standard_payloads import active_standard_payload
from .services.system_field_group_assembler import apply_group_contracts
from .services.system_field_groups import list_system_field_groups
from .services.template_block_rules import apply_template_block_rules
from .services.excel_report_source import apply_excel_source, apply_pdf_source, build_source_document
from .services.rule_admin import RuleAdminRepository
from .services.protocol_report_source import refresh_protocol_source
from .services.protocol_document import apply_protocol_document
from .services.report_template_runtime import resolve_runtime_template
from .source_api import create_source_router
from .report_utils import (
    binding_label, default_report_data, flatten_values, manual_edit_locked, resolved_report_title,
)
from .report_word_api import create_report_word_router
from .report_lims_api import create_report_lims_router
from .report_source_api import create_report_source_router
from .onlyoffice_bridge_api import create_onlyoffice_bridge_router


settings = get_settings()
database = Database(settings)
rule_admin = RuleAdminRepository(database, settings.data_dir.parent / "mapping" / "template-mapping.json")
auth = AuthManager(database, settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[*settings.allowed_origins, settings.onlyoffice_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_auth_router(auth))
app.include_router(create_onlyoffice_bridge_router(settings, auth))
app.include_router(create_admin_router(rule_admin, settings, auth))
app.include_router(create_management_router(database, settings, auth))
app.include_router(create_lims_router(database, settings, auth))


def source_response(item: dict) -> SourceDocument:
    return build_source_document(item, settings.api_prefix)


app.include_router(create_source_router(database, settings, auth, source_response))


def report_response(item: dict) -> ReportTask:
    output_name = item.get("output_name")
    return ReportTask(
        **item,
        download_url=f"{settings.api_prefix}/reports/{item['id']}/file" if output_name else None,
    )


def required_source(source_id: str) -> dict:
    item = database.get_source(source_id)
    if not item:
        raise HTTPException(404, "数据源不存在")
    return item


def required_report(report_id: str) -> dict:
    item = database.get_report(report_id)
    if not item:
        raise HTTPException(404, "报告不存在")
    return item


def required_owned_report(report_id: str, user: dict) -> dict:
    item = required_report(report_id)
    if item.get("created_by") != user["id"]:
        raise HTTPException(404, "报告不存在")
    return item


def _apply_content_block_rules(snapshot: dict) -> list[dict]:
    """字段映射叠加模板设计器的内容块配置；编组没配内容块就保持原样。"""
    return apply_template_block_rules(
        snapshot, list_system_field_groups(database), database.list_lims_fields(True),
    )


def runtime_template_and_mappings(template_id: str | None = None):
    return resolve_runtime_template(settings, rule_admin, _apply_content_block_rules, template_id)


def record_generation(report_id: str, data: dict, phase: str, actor: str = "",
                      status: str = "SUCCESS", output_name: str = "", error: str = "") -> str:
    """往报告生成历史落一条记录，快照里带上本次提取到的字段内容。

    只有"真正生成"的动作才调用它：创建报告、载入 LIMS、更换数据源、重建与导出。
    打开报告或打开编辑器时为补齐缺失文件而做的渲染不算一次生成，不记录。
    """
    generation_id = uuid.uuid4().hex
    database.create_generation({
        "id": generation_id, "report_id": report_id, "generated_by": actor or None,
        "status": status, "output_name": output_name, "error_message": error,
        "generation_snapshot": {"resolved_data": data,
                                "field_sources": data.get("field_sources", {}),
                                "original_values": data.get("original_values", {}),
                                "warnings": data.get("warnings", [])},
        "generation_context": {"phase": phase,
                               "template_name": data.get("template_name", ""),
                               "template_version": data.get("template_version", ""),
                               "template_revision": data.get("template_revision", "")},
    })
    return generation_id


def render_report_word(item: dict, data: dict, payload: dict | None = None,
                       output_suffix: str = "", phase: str = "", actor: str = "") -> str:
    template, mappings, table_rules, template_meta = runtime_template_and_mappings(data.get("template_id") or None)
    data.update(template_meta)
    output_name = (f"report-{item['id']}-{output_suffix}.docx" if output_suffix
                   else f"report-{item['id']}-working.docx")
    refresh_protocol_source(database, settings, data)
    source_payloads = data.get("source_payloads", {})
    active_payload = payload or active_standard_payload(data)
    apply_group_contracts(active_payload, list_system_field_groups(database))
    if not payload:
        for source_name in ("EXCEL", "LIMS", "PDF"):
            if source_payloads.get(source_name) is active_payload:
                data.setdefault("source_payloads", {})[source_name] = active_payload
                break
    bound_codes = {str(mapping.get("standardFieldCode") or "") for mapping in mappings}
    all_fields = database.list_lims_fields()
    all_rules = database.list_system_field_rules()
    rules_by_field = {}
    for rule in all_rules:
        rules_by_field.setdefault(str(rule.get("fieldCode") or ""), []).append(rule)
    # 字段解析面向整个标准字段目录；模板绑定字段只决定 Word 渲染内容。
    # 这样生成历史可以完整记录本次源数据实际解析出的字段，而不遗漏未绑定字段。
    required_codes = {str(field.get("fieldCode") or "") for field in all_fields}
    pending_codes = list(required_codes)
    while pending_codes:
        code = pending_codes.pop()
        for rule in rules_by_field.get(code, []):
            config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
            # 收集计算规则的依赖字段
            dependencies = list(config.get("dependencies", []) or [])
            # 收集上下文变量中的字段依赖（兼容旧的 fieldCode）
            dependencies += [
                item.get("fieldCode") for item in (config.get("contextVariables", []) or [])
                if isinstance(item, dict) and item.get("fieldCode")
            ]
            # 上下文变量中的编组依赖不需要加到字段依赖中，因为编组数据从 payload 直接读取
            for dependency in dependencies:
                if dependency and dependency not in required_codes:
                    required_codes.add(dependency)
                    pending_codes.append(dependency)
    system_fields = [field for field in all_fields if field["fieldCode"] in required_codes]
    resolve_system_fields(system_fields, all_rules, active_payload, data)
    try:
        build_mapped_docx(template, settings.reports_dir / output_name, mappings,
                          active_payload, data, table_rules)
    except Exception as error:
        if phase:
            record_generation(item["id"], data, phase, actor, "FAILED", error=str(error))
        raise
    if phase:
        record_generation(item["id"], data, phase, actor, output_name=output_name)
    return output_name


def require_automatic_edit_allowed(item: dict) -> None:
    if item.get("word_edit_locked"):
        raise manual_edit_locked()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "storage": "local", "database": "mysql"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    # 浏览器会自动请求 favicon；没有图标时返回 204，避免把无关 404 混入排障日志。
    return Response(status_code=204)


@app.get(f"{settings.api_prefix}/reports", response_model=list[ReportTask])
def list_reports(user: dict = Depends(auth.require("REPORT_EDIT"))) -> list[ReportTask]:
    # GET 保持纯读：模板元数据的惰性补写由 ensure_report_file 在生成文件时完成，
    # 这里若边读边写，会与并发保存的 sync_word_fields 互相覆盖（丢失更新）
    return [report_response(item) for item in database.list_reports(user["id"])]


@app.get(f"{settings.api_prefix}/template-source-catalog")
def template_source_catalog(user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict:
    return rule_admin.report_source_catalog()


@app.post(f"{settings.api_prefix}/reports/batch-word")
def batch_export_reports(payload: dict, user: dict = Depends(auth.require("REPORT_DOWNLOAD"))) -> StreamingResponse:
    report_ids = list(dict.fromkeys(str(value) for value in payload.get("report_ids", []) if value))
    if not report_ids or len(report_ids) > 100:
        raise HTTPException(422, "请选择 1 至 100 份报告")
    archive = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for report_id in report_ids:
            item = required_owned_report(report_id, user)
            path = settings.reports_dir / f"report-{report_id}-working.docx"
            if not path.exists():
                output_name = render_report_word(item, item["resolved_data"])
                item = database.update_report(report_id, output_name=output_name, status="EDITING") or item
                path = settings.reports_dir / output_name
            base = "".join(value for value in item["title"] if value not in '\\/:*?"<>|').strip() or report_id
            name = f"{base}.docx"
            counter = 2
            while name in used_names:
                name = f"{base}-{counter}.docx"
                counter += 1
            used_names.add(name)
            try:
                output.writestr(name, export_docx_bytes(path))
            except Exception as error:
                logger.exception("批量报告导出失败 report_id=%s", report_id)
                raise HTTPException(422, f"批量报告导出失败：{error}") from error
    archive.seek(0)
    return StreamingResponse(
        archive, media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=reports-word.zip"},
    )


@app.get(f"{settings.api_prefix}/report-generations")
def personal_report_generations(page: int = 1, page_size: int = 100,
                                user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict:
    """Return only the current user's immutable report-generation records."""
    return database.list_generations(
        user_id=user["id"],
        page=max(1, page),
        page_size=min(100, max(1, page_size)),
    )


@app.get(f"{settings.api_prefix}/report-generations/{{generation_id}}/file")
def download_generation(generation_id: str,
                        user: dict = Depends(auth.require("REPORT_DOWNLOAD"))) -> Response:
    generation = database.get_generation(generation_id)
    if not generation or generation.get("generated_by") != user["id"] or generation.get("status") != "SUCCESS":
        raise HTTPException(404, "导出记录不存在")
    output_name = str(generation.get("output_name") or "")
    path = (settings.reports_dir / output_name).resolve()
    if not output_name or path.parent != settings.reports_dir.resolve() or not path.is_file():
        raise HTTPException(404, "导出文件不存在")
    return export_docx_response(path, generation["title"])


@app.get(f"{settings.api_prefix}/report-templates")
def list_report_templates(user: dict = Depends(auth.require("REPORT_CREATE"))) -> list[dict]:
    return [item for item in rule_admin.list_templates()
            if item["status"] == "ACTIVE" and item["publishedVersion"] is not None]


@app.post(f"{settings.api_prefix}/reports", response_model=ReportTask)
def create_report(request: CreateReportRequest,
                  user: dict = Depends(auth.require("REPORT_CREATE"))) -> ReportTask:
    report_id = ""
    try:
        source = required_source(request.source_document_id) if request.source_document_id else None
        if source and source.get("source_type") != "PDF":
            raise HTTPException(422, "PDF 数据源类型无效")
        excel_source = required_source(request.excel_document_id) if request.excel_document_id else None
        protocol_source = required_source(request.protocol_document_id) if request.protocol_document_id else None
        if protocol_source and protocol_source.get("source_type") != "PROTOCOL":
            raise HTTPException(422, "方案文件类型无效，请上传 DOCX 格式的 Word 方案")
        if excel_source and excel_source.get("source_type") != "EXCEL":
            raise HTTPException(422, "Excel 数据源类型无效")
        data = request.data.model_dump() if request.data else default_report_data()
        *_, template_meta = runtime_template_and_mappings(request.template_id)
        data.update(template_meta)
        if protocol_source:
            apply_protocol_document(data, protocol_source, settings.api_prefix)
        if source:
            apply_pdf_source(data, source)
        if excel_source:
            apply_excel_source(data, excel_source, settings.api_prefix)
        for source_name in ("EXCEL", "LIMS", "PDF"):
            source_payload = data.get("source_payloads", {}).get(source_name)
            if isinstance(source_payload, dict):
                apply_group_contracts(source_payload, list_system_field_groups(database))
        refresh_protocol_source(database, settings, data)
        # 在报告和首条生成历史入库前解析系统字段，确保后台详情反映本次提取结果。
        active_payload = active_standard_payload(data)
        resolve_system_fields(database.list_lims_fields(), database.list_system_field_rules(),
                              active_payload, data)
        if not data["project_name"] and data["sample"]:
            data["project_name"] = f"{data['sample']}分析报告"
        report_id = uuid.uuid4().hex
        timestamp = now_iso()
        item = database.create_report(
            {
                "id": report_id,
                "title": resolved_report_title(request.title, data),
                "status": "DATA_REVIEW",
                "source_document_id": request.source_document_id,
                "resolved_data": data,
                "created_at": timestamp,
                "updated_at": timestamp,
                "created_by": user["id"],
                "updated_by": user["id"],
            }
        )
        database.create_version(report_id, data, "初始版本")
        record_generation(report_id, data, "创建报告", user["id"])
        return report_response(item)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("报告创建失败 user_id=%s", user.get("id"))
        if report_id:
            try:
                database.delete_report(report_id)
            except Exception:
                logger.exception("清理失败的报告草稿失败 report_id=%s", report_id)
        raise HTTPException(500, f"创建报告失败：{error}") from error


@app.get(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ReportTask)
def get_report(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> ReportTask:
    return report_response(required_owned_report(report_id, user))


@app.delete(f"{settings.api_prefix}/reports/{{report_id}}")
def delete_report(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict[str, bool]:
    item = required_owned_report(report_id, user)
    try:
        output_names = database.delete_report(report_id)
    except Exception as error:
        logger.exception("报告删除失败 report_id=%s", report_id)
        raise HTTPException(500, f"删除报告失败：{error}") from error
    candidates = {
        str(item.get("output_name") or ""),
        f"report-{report_id}-working.docx",
        f"report-{report_id}.pdf",
        *output_names,
    }
    for name in candidates:
        path = (settings.reports_dir / name).resolve()
        if name and path.parent == settings.reports_dir.resolve():
            path.unlink(missing_ok=True)
    return {"deleted": True}


@app.put(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ReportTask)
def update_report(report_id: str, request: UpdateReportRequest,
                  user: dict = Depends(auth.require("REPORT_EDIT"))) -> ReportTask:
    current = required_owned_report(report_id, user)
    # 人工编辑落盘后，PUT 保存会静默丢弃用户在 Word 里的改动
    require_automatic_edit_allowed(current)
    before = flatten_values(current["resolved_data"])
    after_data = request.data.model_dump()
    after = flatten_values(after_data)
    for field_code, new_value in after.items():
        old_value = before.get(field_code, "")
        if old_value != new_value:
            database.add_change(report_id, field_code, old_value, new_value, user["display_name"])
    item = database.update_report(
        report_id,
        title=resolved_report_title(request.title, after_data),
        resolved_data=after_data,
        status="READY_TO_GENERATE",
        updated_by=user["id"],
    )
    return report_response(item)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/bindings", response_model=list[FieldBinding])
def report_bindings(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> list[FieldBinding]:
    data = required_owned_report(report_id, user)["resolved_data"]
    values = flatten_values(data)
    sources = data.get("field_sources", {})
    originals = data.get("original_values", {})
    bindings = []
    for field_code, value in values.items():
        source = sources.get(field_code, {"type": "MANUAL", "record_id": "MANUAL"})
        original = str(originals.get(field_code, value))
        bindings.append({"field_code": field_code, "label": binding_label(field_code), "current_value": value,
                         "original_value": original, "source": source, "modified": value != original})
    return bindings


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/history", response_model=list[ChangeEvent])
def report_history(report_id: str, field_code: str | None = None,
                   user: dict = Depends(auth.require("REPORT_EDIT"))) -> list[dict]:
    required_owned_report(report_id, user)
    return database.list_changes(report_id, field_code)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/versions", response_model=list[ReportVersion])
def report_versions(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> list[dict]:
    required_owned_report(report_id, user)
    return database.list_versions(report_id)


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/versions", response_model=ReportVersion)
def create_report_version(report_id: str, note: str = "手工保存",
                          user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict:
    item = required_owned_report(report_id, user)
    version = database.create_version(report_id, item["resolved_data"], note)
    database.create_generation({
        "id": uuid.uuid4().hex, "report_id": report_id, "version_id": version["id"],
        "generated_by": user["id"], "status": "SUCCESS",
        "generation_snapshot": {"resolved_data": item["resolved_data"],
                                 "field_sources": item["resolved_data"].get("field_sources", {}),
                                 "original_values": item["resolved_data"].get("original_values", {})},
        "generation_context": {"phase": "版本保存", "note": note},
    })
    return version


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/generate", response_model=ReportTask)
def generate_report(report_id: str, user: dict = Depends(auth.require("REPORT_GENERATE"))) -> ReportTask:
    try:
        logger.info("开始生成报告 report_id=%s user_id=%s", report_id, user.get("id"))
        item = required_owned_report(report_id, user)
        # 每次正式生成都重新按当前标准字段目录和提取规则解析，避免复用旧工作文件。
        output_name = render_report_word(item, item["resolved_data"])
        item = database.update_report(
            report_id, output_name=output_name, status="EDITING",
            resolved_data=item["resolved_data"], updated_by=user["id"],
        ) or item
        working_path = settings.reports_dir / output_name
        logger.info("报告工作文件已准备 report_id=%s path=%s", report_id, working_path)
        version = database.create_version(report_id, item["resolved_data"], "报告生成")
        generation_id = uuid.uuid4().hex
        database.create_generation({"id": generation_id, "report_id": report_id, "version_id": version["id"],
                                    "generated_by": user["id"], "status": "PROCESSING",
                                    "generation_snapshot": {"resolved_data": item["resolved_data"],
                                                            "field_sources": item["resolved_data"].get("field_sources", {}),
                                                            "original_values": item["resolved_data"].get("original_values", {})},
                                    "generation_context": {"phase": "导出 Word", "template_revision": item["resolved_data"].get("template_revision", "")}})
        output_name = f"report-{report_id}-export-{generation_id[:12]}.docx"
        write_export_docx(working_path, settings.reports_dir / output_name)
    except Exception as error:
        logger.exception("报告生成失败 report_id=%s", report_id)
        if "generation_id" in locals():
            database.update_generation(generation_id, status="FAILED", error_message=str(error))
        raise HTTPException(500, f"导出 Word 失败：{error}") from error
    database.update_generation(generation_id, status="SUCCESS", output_name=output_name)
    return report_response(database.update_report(
        report_id, status="GENERATED", updated_by=user["id"]
    ))


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/pdf")
def export_report_pdf(report_id: str, user: dict = Depends(auth.require("REPORT_DOWNLOAD"))) -> FileResponse:
    item = required_owned_report(report_id, user)
    source = settings.reports_dir / f"report-{report_id}-working.docx"
    if not source.exists():
        output_name = render_report_word(item, item["resolved_data"])
        item = database.update_report(report_id, output_name=output_name, status="EDITING") or item
        source = settings.reports_dir / output_name
    output = settings.reports_dir / f"report-{report_id}.pdf"
    with tempfile.TemporaryDirectory(prefix="report-pdf-") as directory:
        temporary = Path(directory)
        try:
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(temporary), str(source)],
                capture_output=True, text=True, timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HTTPException(503, f"PDF 转换服务不可用：{error}") from error
        converted = temporary / f"{source.stem}.pdf"
        if result.returncode or not converted.exists():
            message = (result.stderr or result.stdout or "未知错误").strip()
            raise HTTPException(500, f"PDF 转换失败：{message}")
        shutil.copy2(converted, output)
    return FileResponse(output, media_type="application/pdf", filename=f"{item['title']}.pdf")


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/rebuild-word", response_model=ReportTask)
def rebuild_report_word(report_id: str, user: dict = Depends(auth.require("REPORT_GENERATE"))) -> ReportTask:
    item = required_owned_report(report_id, user)
    require_automatic_edit_allowed(item)
    try:
        output_name = render_report_word(item, item["resolved_data"],
                                         phase="重建 Word", actor=user["id"])
    except Exception as error:
        logger.exception("Word 重建失败 report_id=%s", report_id)
        raise HTTPException(500, f"Word 重建失败：{error}") from error
    return report_response(database.update_report(
        report_id, status="EDITING", output_name=output_name,
        resolved_data=item["resolved_data"], updated_by=user["id"],
        # 文件已重建，未保存的编辑会话不得再回写覆盖
        onlyoffice_document_key=None,
    ))


app.include_router(create_report_word_router(
    database, settings, auth, rule_admin, required_report, required_owned_report,
    runtime_template_and_mappings, render_report_word, require_automatic_edit_allowed,
    _apply_content_block_rules,
))
app.include_router(create_report_source_router(database, settings, auth, required_owned_report,
                                               report_response, render_report_word))
app.include_router(create_report_lims_router(
    database, settings, auth, required_owned_report, report_response, render_report_word,
))

frontend_dist = settings.data_dir.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
