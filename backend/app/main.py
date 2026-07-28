import hashlib
import json
import shutil
import time
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Database, now_iso
from .admin_api import create_admin_router
from .auth import AuthManager, create_auth_router
from .management_api import create_management_router
from .lims_api import create_lims_router
from .schemas import (
    ApplyLimsRequest,
    ChangeEvent,
    CreateReportRequest,
    FieldBinding,
    ReportTask,
    ReportVersion,
    SourceDocument,
    UpdateReportRequest,
)
from .services.lims_excel import parse_lims_workbook
from .services.lims_normalizer import merge_instances
from .services.mapped_docx_generator import build_mapped_docx
from .services.word_sync import read_bound_values
from .services.pdf_extractor import extract_pdf
from .services.rule_admin import RuleAdminRepository
from .services.template_compiler import compile_template


settings = get_settings()
database = Database(settings.database_path)
rule_admin = RuleAdminRepository(database, settings.data_dir.parent / "mapping" / "template-mapping.json")
auth = AuthManager(database, settings)
REPORT_LIFECYCLE_MIGRATION = "2026_report_lifecycle_reset_v1"


def apply_report_lifecycle_migration() -> None:
    if database.migration_applied(REPORT_LIFECYCLE_MIGRATION):
        return
    database.clear_report_test_data()
    for directory in (settings.reports_dir, settings.uploads_dir):
        for path in directory.iterdir():
            if path.name == ".gitkeep":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    database.mark_migration_applied(REPORT_LIFECYCLE_MIGRATION)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    database.initialize()
    apply_report_lifecycle_migration()
    bootstrap_user_id = auth.bootstrap()
    if bootstrap_user_id:
        database.backfill_report_ownership(bootstrap_user_id)
    rule_admin.seed()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_auth_router(auth))
app.include_router(create_admin_router(rule_admin, settings, auth))
app.include_router(create_management_router(database, settings, auth))
app.include_router(create_lims_router(database, settings, auth))


def source_response(item: dict) -> SourceDocument:
    return SourceDocument(
        **item,
        preview_url=f"{settings.api_prefix}/source-documents/{item['id']}/preview",
    )


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


def default_report_data() -> dict:
    return {
        "report_no": "",
        "customer": "",
        "sample": "",
        "project_name": "",
        "report_date": "",
        "conclusion": "",
        "author": "",
        "reviewer": "",
        "approver": "",
        "template_version": "V1.0",
        "test_items": [],
        "field_sources": {},
        "original_values": {},
        "source_payloads": {},
    }


def resolved_report_title(title: str | None, data: dict) -> str:
    """Keep an explicit name, otherwise derive a stable report title from its data."""
    explicit = str(title or "").strip()
    if explicit and explicit != "未命名报告":
        return explicit
    project_name = str(data.get("project_name") or "").strip()
    if project_name:
        return project_name
    sample = str(data.get("sample") or "").strip()
    if sample:
        return f"{sample}分析报告"
    report_no = str(data.get("report_no") or "").strip()
    return report_no or "未命名报告"


def has_custom_report_title(item: dict) -> bool:
    title = str(item.get("title") or "").strip()
    data = item.get("resolved_data") or {}
    automatic = {"", "未命名报告", str(data.get("project_name") or "").strip(),
                 str(data.get("report_no") or "").strip()}
    sample = str(data.get("sample") or "").strip()
    if sample:
        automatic.add(f"{sample}分析报告")
    return title not in automatic


def _apply_content_block_rules(snapshot: dict) -> list[dict]:
    blocks = {item["id"]: item for item in snapshot.get("contentBlocks", [])}
    result: list[dict] = []
    for source in snapshot.get("mappings", []):
        mapping = dict(source)
        block = blocks.get(mapping.get("blockId"))
        if block:
            mapping["contentBlockId"] = block["id"]
            mapping["contentBlockKind"] = block.get("kind", "MAPPED_FIELD")
            mapping["blockSourcePath"] = block.get("sourcePath", "")
            mapping["blockDedupKey"] = block.get("dedupKey", "")
            mapping["blockSortRule"] = block.get("sortRule", "")
            mapping["blockEmptyBehavior"] = block.get("emptyBehavior", "KEEP")
            mapping["blockMergeRule"] = block.get("mergeRule", "NONE")
            mapping["prototypeLocation"] = block.get("prototypeLocation", "")
            if block.get("kind") in {"REPEATING_TABLE", "MATRIX"}:
                mapping["repeatType"] = "ROW"
                mapping["repeatKey"] = block.get("repeatKey", "")
                mapping["tableNo"] = block.get("tableNo", "") or mapping.get("tableNo", "")
        result.append(mapping)
    return result


def runtime_template_and_mappings() -> tuple[Path, list[dict]]:
    snapshot, published_template = rule_admin.active_runtime_rules()
    mappings = _apply_content_block_rules(snapshot)
    if published_template:
        candidate = Path(published_template)
        if candidate.exists():
            return candidate, mappings
    output = settings.template_path.parent / "compiled" / "runtime-report-template.docx"
    report = compile_template(settings.template_path, output, mappings, snapshot["tableRules"])
    if not report["valid"]:
        raise RuntimeError(f"运行时模板编译失败：{len(report['errors'])} 个错误")
    return output, mappings


def render_report_word(item: dict, data: dict, payload: dict | None = None,
                       output_suffix: str = "") -> str:
    template, mappings = runtime_template_and_mappings()
    output_name = (f"report-{item['id']}-{output_suffix}.docx" if output_suffix
                   else f"report-{item['id']}-working.docx")
    active_payload = payload or data.get("source_payloads", {}).get("LIMS") or {}
    build_mapped_docx(template, settings.reports_dir / output_name, mappings, active_payload, data)
    return output_name


def manual_edit_locked() -> HTTPException:
    return HTTPException(409, {"code": "MANUAL_EDIT_LOCKED", "message": "Word 已人工编辑并保存，不能再次自动生成；请新建报告。"})


def require_automatic_edit_allowed(item: dict) -> None:
    if item.get("word_edit_locked"):
        raise manual_edit_locked()


def document_key(report_id: str, path: Path) -> str:
    document_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return f"{report_id}-{document_hash}"


def flatten_values(data: dict) -> dict[str, str]:
    values = {
        key: str(data.get(key) or "")
        for key in ("report_no", "customer", "sample", "project_name", "report_date", "conclusion", "author", "reviewer", "approver")
    }
    for item in data.get("test_items", []):
        for field in ("category", "name", "method", "requirement", "result", "unit", "conclusion"):
            values[f"testItems[id={item['id']}].{field}"] = str(item.get(field) or "")
    return values


def binding_label(field_code: str) -> str:
    labels = {"report_no": "报告编号", "customer": "客户名称", "sample": "样品名称", "project_name": "项目名称",
              "report_date": "报告日期", "conclusion": "报告结论", "author": "编制人", "reviewer": "复核人", "approver": "批准人"}
    if field_code in labels:
        return labels[field_code]
    field = field_code.rsplit(".", 1)[-1]
    return {"category": "分类", "name": "检测项目", "method": "检测方法", "requirement": "技术要求",
            "result": "检测结果", "unit": "单位", "conclusion": "结论"}.get(field, field)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "storage": "local", "database": "sqlite"}


@app.post(f"{settings.api_prefix}/source-documents", response_model=SourceDocument)
async def upload_source(file: UploadFile = File(...),
                        user: dict = Depends(auth.require("REPORT_EDIT"))) -> SourceDocument:
    original_name = Path(file.filename or "").name
    if Path(original_name).suffix.lower() != ".pdf":
        raise HTTPException(400, "仅支持 PDF 文件")
    source_id = uuid.uuid4().hex
    stored_name = f"{source_id}.pdf"
    target = settings.uploads_dir / stored_name
    size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb} MB")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    item = database.create_source(
        {"id": source_id, "file_name": original_name, "stored_name": stored_name, "size": size, "created_at": now_iso()}
    )
    return source_response(item)


@app.get(f"{settings.api_prefix}/source-documents/{{source_id}}/preview")
def preview_source(source_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> FileResponse:
    item = required_source(source_id)
    return FileResponse(settings.uploads_dir / item["stored_name"], media_type="application/pdf", filename=item["file_name"])


@app.post(f"{settings.api_prefix}/source-documents/{{source_id}}/extract", response_model=SourceDocument)
def extract_source(source_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> SourceDocument:
    item = required_source(source_id)
    try:
        fields = extract_pdf(settings.uploads_dir / item["stored_name"], source_id)
    except Exception as error:
        raise HTTPException(422, f"PDF 解析失败：{error}") from error
    return source_response(database.update_extracted_fields(source_id, fields))


@app.get(f"{settings.api_prefix}/reports", response_model=list[ReportTask])
def list_reports(user: dict = Depends(auth.require("REPORT_EDIT"))) -> list[ReportTask]:
    return [report_response(item) for item in database.list_reports(user["id"])]


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
                        user: dict = Depends(auth.require("REPORT_DOWNLOAD"))) -> FileResponse:
    generation = database.get_generation(generation_id)
    if not generation or generation.get("generated_by") != user["id"] or generation.get("status") != "SUCCESS":
        raise HTTPException(404, "导出记录不存在")
    output_name = str(generation.get("output_name") or "")
    path = (settings.reports_dir / output_name).resolve()
    if not output_name or path.parent != settings.reports_dir.resolve() or not path.is_file():
        raise HTTPException(404, "导出文件不存在")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{generation['title']}.docx",
    )


@app.post(f"{settings.api_prefix}/reports", response_model=ReportTask)
def create_report(request: CreateReportRequest,
                  user: dict = Depends(auth.require("REPORT_CREATE"))) -> ReportTask:
    source = required_source(request.source_document_id) if request.source_document_id else None
    data = request.data.model_dump() if request.data else default_report_data()
    if source:
        for field in source["extracted_fields"]:
            if field["field_code"] in data and not data[field["field_code"]]:
                data[field["field_code"]] = field["value"]
            code = field["field_code"]
            data.setdefault("field_sources", {})[code] = field["source"]
            data.setdefault("original_values", {})[code] = field["value"]
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
    return report_response(item)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ReportTask)
def get_report(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> ReportTask:
    return report_response(required_owned_report(report_id, user))


@app.put(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ReportTask)
def update_report(report_id: str, request: UpdateReportRequest,
                  user: dict = Depends(auth.require("REPORT_EDIT"))) -> ReportTask:
    current = required_owned_report(report_id, user)
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
    return database.create_version(report_id, item["resolved_data"], note)


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/generate", response_model=ReportTask)
def generate_report(report_id: str, user: dict = Depends(auth.require("REPORT_GENERATE"))) -> ReportTask:
    item = required_owned_report(report_id, user)
    item, working_path = ensure_report_file(item)
    version = database.create_version(report_id, item["resolved_data"], "导出 Word")
    generation_id = uuid.uuid4().hex
    database.create_generation({"id": generation_id, "report_id": report_id, "version_id": version["id"],
                                "generated_by": user["id"], "status": "PROCESSING"})
    try:
        output_name = f"report-{report_id}-export-{generation_id[:12]}.docx"
        shutil.copy2(working_path, settings.reports_dir / output_name)
    except Exception as error:
        database.update_generation(generation_id, status="FAILED", error_message=str(error))
        raise HTTPException(500, f"导出 Word 失败：{error}") from error
    database.update_generation(generation_id, status="SUCCESS", output_name=output_name)
    return report_response(database.update_report(
        report_id, status="GENERATED", updated_by=user["id"]
    ))


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/rebuild-word", response_model=ReportTask)
def rebuild_report_word(report_id: str, user: dict = Depends(auth.require("REPORT_GENERATE"))) -> ReportTask:
    item = required_owned_report(report_id, user)
    require_automatic_edit_allowed(item)
    try:
        output_name = render_report_word(item, item["resolved_data"])
    except Exception as error:
        raise HTTPException(500, f"Word 重建失败：{error}") from error
    return report_response(database.update_report(
        report_id, status="EDITING", output_name=output_name, updated_by=user["id"]
    ))


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims-legacy", response_model=ReportTask,
          include_in_schema=False)
def apply_lims_to_report(report_id: str, request: ApplyLimsRequest) -> ReportTask:
    raise HTTPException(410, "旧版 LIMS 接口已停用")


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims", response_model=ReportTask)
def apply_lims_instances_to_report(report_id: str, request: ApplyLimsRequest,
                                   user: dict = Depends(auth.require("REPORT_EDIT"))) -> ReportTask:
    item = required_owned_report(report_id, user)
    require_automatic_edit_allowed(item)
    imported = database.get_lims_import(request.import_id)
    if not imported:
        raise HTTPException(404, "LIMS 导入记录不存在")
    try:
        instances = [parse_lims_workbook(settings.lims_dir / imported["stored_name"], instance_id)
                     for instance_id in request.instance_ids]
        recognition = merge_instances(instances, request.conflict_resolutions)
        if recognition["unresolvedConflictCount"]:
            raise HTTPException(409, {
                "message": "存在未处理的 LIMS 数据冲突",
                "conflicts": recognition["conflicts"],
            })
        payload = recognition["payload"]
    except KeyError as error:
        raise HTTPException(404, f"LIMS 实验记录不存在：{error.args[0]}") from error
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(422, f"LIMS 数据读取失败：{error}") from error

    data = dict(item["resolved_data"])
    sample = payload.get("samples", [{}])[0] if payload.get("samples") else {}
    first_instance = instances[0]
    author = first_instance.get("createdBy", "")
    values = {
        "report_no": payload.get("document", {}).get("code") or "+".join(request.instance_ids),
        "project_name": payload.get("project", {}).get("name") or first_instance.get("title", ""),
        "sample": sample.get("sampleName", ""),
        "customer": sample.get("clientName", ""),
        "author": author or "",
        "template_version": payload.get("document", {}).get("version") or data.get("template_version", "V1.0"),
    }
    sources = dict(data.get("field_sources", {}))
    originals = dict(data.get("original_values", {}))
    for code, value in values.items():
        if value in (None, ""):
            continue
        old_value = str(data.get(code) or "")
        value = str(value)
        data[code] = value
        sources[code] = {"type": "LIMS", "record_id": sample.get("sourceRecordId") or request.instance_ids[0]}
        originals[code] = value
        if old_value != value:
            database.add_change(
                report_id, code, old_value, value, user["display_name"], "载入 LIMS 数据"
            )
    data["field_sources"] = sources
    data["original_values"] = originals
    source_payloads = dict(data.get("source_payloads", {}))
    source_payloads["LIMS"] = payload
    source_payloads["LIMS_RECOGNITION"] = {
        "recognizedCounts": recognition["recognizedCounts"],
        "duplicateCount": recognition["duplicateCount"],
        "unmatched": recognition["unmatched"],
        "instances": payload["instances"],
    }
    data["source_payloads"] = source_payloads
    try:
        output_name = render_report_word(item, data, payload)
    except Exception as error:
        raise HTTPException(500, f"LIMS 数据填充 Word 失败：{error}") from error
    updated = database.update_report(
        report_id, title=resolved_report_title(item.get("title"), data), resolved_data=data,
        status="EDITING", output_name=output_name, updated_by=user["id"],
    )
    database.create_version(report_id, data, f"载入 LIMS 实验记录 {', '.join(request.instance_ids)}")
    return report_response(updated)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/file")
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


@app.get(f"{settings.api_prefix}/onlyoffice/reports/{{report_id}}/config")
def onlyoffice_config(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict:
    if not settings.onlyoffice_jwt_secret:
        raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请设置 REPORT_ONLYOFFICE_JWT_SECRET")
    item, path = ensure_editable_report_file(required_owned_report(report_id, user))
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
        },
        "height": "100%",
        "width": "100%",
        "type": "desktop",
    }
    config["token"] = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
    return {"documentServerUrl": settings.onlyoffice_url, "config": config}


@app.post(f"{settings.api_prefix}/onlyoffice/callback/{{report_id}}")
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


frontend_dist = settings.data_dir.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
