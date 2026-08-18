import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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
from .services.lims_normalizer import merge_instances
from .services.lims_files import migrate_stored_lims_file_urls
from .services.mapped_docx_generator import build_mapped_docx
from .services.system_field_resolver import resolve_system_fields
from .services.system_field_group_assembler import apply_group_contracts
from .services.system_field_groups import list_system_field_groups
from .services.excel_rule_defaults import ensure_excel_field_rules
from .services.excel_report_source import apply_excel_source, apply_pdf_source, build_source_document
from .services.rule_admin import RuleAdminRepository
from .services.template_compiler import compile_template
from .source_api import create_source_router
from .report_utils import (
    binding_label, default_report_data, flatten_values, resolved_report_title,
)
from .report_word_api import create_report_word_router
from .report_source_api import create_report_source_router
from .onlyoffice_bridge_api import create_onlyoffice_bridge_router


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
    ensure_excel_field_rules(database)
    migrate_stored_lims_file_urls(database, settings.lims_file_base_url)
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
    blocks = {item["id"]: item for item in snapshot.get("contentBlocks", [])}
    fields = {item["fieldCode"]: item for item in database.list_lims_fields(True)}
    result: list[dict] = []
    for source in snapshot.get("mappings", []):
        mapping = dict(source)
        field = fields.get(str(mapping.get("standardFieldCode") or ""))
        if field:
            mapping["standardFieldDataType"] = field.get("dataType", "string")
            mapping["standardFieldOutputFormat"] = field.get("outputFormat", "")
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


def _apply_group_repeat_rules(mappings: list[dict]) -> list[dict]:
    """Treat array source paths as table-row mappings without designer settings."""
    result = []
    for source in mappings:
        mapping = dict(source)
        source_path = str(mapping.get("sourcePath") or "")
        match = re.match(r"^\$\.([A-Za-z0-9_]+)\[\*\](?:\.|$)", source_path)
        if match and mapping.get("repeatType") in {None, "", "NONE"}:
            mapping["repeatType"] = "ROW"
            mapping["repeatKey"] = match.group(1)
        result.append(mapping)
    return result


def runtime_template_and_mappings() -> tuple[Path, list[dict], dict[str, str]]:
    active = rule_admin.active_runtime_template()
    if active:
        snapshot = active["snapshot"]
        published_template = active.get("templateFile")
    else:
        snapshot, published_template = rule_admin.active_runtime_rules()
    mappings = _apply_group_repeat_rules(_apply_content_block_rules(snapshot))
    if published_template:
        candidate = Path(published_template)
        if candidate.exists():
            revision = hashlib.sha256(candidate.read_bytes()).hexdigest()
            configuration = hashlib.sha256(json.dumps(
                {"mappings": mappings, "tableRules": snapshot["tableRules"]},
                ensure_ascii=False, sort_keys=True, default=str,
            ).encode("utf-8")).hexdigest()
            output = settings.template_path.parent / "compiled" / f"runtime-{revision[:12]}-{configuration[:12]}.docx"
            if not output.exists():
                report = compile_template(candidate, output, mappings, snapshot["tableRules"])
                if not report["valid"]:
                    raise RuntimeError(f"运行时模板编译失败：{len(report['errors'])} 个错误")
            return output, mappings, {
                "template_id": str(active.get("templateId", "")) if active else "",
                "template_name": str(active.get("templateName", "")) if active else "",
                "template_code": str(active.get("templateCode", "")) if active else "",
                "template_catalog_version_id": str(active.get("versionId", "")) if active else "",
                "template_version": f"V{active['versionNo']}" if active else "V1.0",
                "template_revision": revision,
            }
    output = settings.template_path.parent / "compiled" / "runtime-report-template.docx"
    report = compile_template(settings.template_path, output, mappings, snapshot["tableRules"])
    if not report["valid"]:
        raise RuntimeError(f"运行时模板编译失败：{len(report['errors'])} 个错误")
    return output, mappings, {
        "template_version": "V1.0",
        "template_revision": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def render_report_word(item: dict, data: dict, payload: dict | None = None,
                       output_suffix: str = "") -> str:
    template, mappings, template_meta = runtime_template_and_mappings()
    data.update(template_meta)
    output_name = (f"report-{item['id']}-{output_suffix}.docx" if output_suffix
                   else f"report-{item['id']}-working.docx")
    source_payloads = data.get("source_payloads", {})
    active_payload = dict(payload or source_payloads.get("LIMS") or {})
    apply_group_contracts(active_payload, list_system_field_groups(database))
    bound_codes = {str(mapping.get("standardFieldCode") or "") for mapping in mappings}
    all_fields = database.list_lims_fields()
    all_rules = database.list_system_field_rules()
    rules_by_field = {}
    for rule in all_rules:
        rules_by_field.setdefault(str(rule.get("fieldCode") or ""), []).append(rule)
    required_codes = set(bound_codes)
    pending_codes = list(bound_codes)
    while pending_codes:
        code = pending_codes.pop()
        for rule in rules_by_field.get(code, []):
            config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
            dependencies = list(config.get("dependencies", []) or []) + [item.get("fieldCode") for item in (config.get("contextVariables", []) or []) if isinstance(item, dict)]
            for dependency in dependencies:
                if dependency and dependency not in required_codes:
                    required_codes.add(dependency)
                    pending_codes.append(dependency)
    system_fields = [field for field in all_fields if field["fieldCode"] in required_codes]
    resolve_system_fields(system_fields, all_rules, active_payload, data)
    build_mapped_docx(template, settings.reports_dir / output_name, mappings, active_payload, data)
    return output_name


def manual_edit_locked() -> HTTPException:
    return HTTPException(409, {"code": "MANUAL_EDIT_LOCKED", "message": "Word 已人工编辑并保存，不能再次自动生成；请新建报告。"})


def require_automatic_edit_allowed(item: dict) -> None:
    if item.get("word_edit_locked"):
        raise manual_edit_locked()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "storage": "local", "database": "sqlite"}


@app.get(f"{settings.api_prefix}/reports", response_model=list[ReportTask])
def list_reports(user: dict = Depends(auth.require("REPORT_EDIT"))) -> list[ReportTask]:
    items = database.list_reports(user["id"])
    _, _, template_meta = runtime_template_and_mappings()
    for index, item in enumerate(items):
        data = item["resolved_data"]
        same_revision = data.get("template_revision") == template_meta["template_revision"]
        metadata_changed = any(data.get(key) != value for key, value in template_meta.items())
        if same_revision and metadata_changed and not item.get("word_edit_locked"):
            data.update(template_meta)
            items[index] = database.update_report(item["id"], resolved_data=data)
    return [report_response(item) for item in items]


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
            item, path = ensure_report_file(required_owned_report(report_id, user))
            base = "".join(value for value in item["title"] if value not in '\\/:*?"<>|').strip() or report_id
            name = f"{base}.docx"
            counter = 2
            while name in used_names:
                name = f"{base}-{counter}.docx"
                counter += 1
            used_names.add(name)
            output.write(path, name)
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
    excel_source = required_source(request.excel_document_id) if request.excel_document_id else None
    if excel_source and excel_source.get("source_type") != "EXCEL":
        raise HTTPException(422, "Excel 数据源类型无效")
    data = request.data.model_dump() if request.data else default_report_data()
    _, _, template_meta = runtime_template_and_mappings()
    data.update(template_meta)
    if source:
        apply_pdf_source(data, source)
    if excel_source:
        apply_excel_source(data, excel_source, settings.api_prefix)
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


@app.delete(f"{settings.api_prefix}/reports/{{report_id}}")
def delete_report(report_id: str, user: dict = Depends(auth.require("REPORT_EDIT"))) -> dict[str, bool]:
    item = required_owned_report(report_id, user)
    output_names = database.delete_report(report_id)
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


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/pdf")
def export_report_pdf(report_id: str, user: dict = Depends(auth.require("REPORT_DOWNLOAD"))) -> FileResponse:
    item, source = ensure_report_file(required_owned_report(report_id, user))
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
        output_name = render_report_word(item, item["resolved_data"])
    except Exception as error:
        raise HTTPException(500, f"Word 重建失败：{error}") from error
    return report_response(database.update_report(
        report_id, status="EDITING", output_name=output_name,
        resolved_data=item["resolved_data"], updated_by=user["id"]
    ))


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims-legacy", response_model=ReportTask,
          include_in_schema=False)
def apply_lims_to_report(report_id: str, request: ApplyLimsRequest) -> ReportTask:
    raise HTTPException(410, "旧版 LIMS 接口已停用")


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims", response_model=ReportTask)
def apply_lims_instances_to_report(report_id: str, request: ApplyLimsRequest,
                                   user: dict = Depends(auth.require("REPORT_EDIT"))) -> ReportTask:
    item = required_owned_report(report_id, user)
    if item.get("word_edit_locked") and not request.force:
        raise manual_edit_locked()
    imported = database.get_lims_import(request.import_id)
    if not imported:
        raise HTTPException(404, "LIMS 导入记录不存在")
    try:
        instances = []
        for instance_id in request.instance_ids:
            payload = database.get_lims_normalized_payload(request.import_id, instance_id)
            if payload is None:
                raise KeyError(instance_id)
            instances.append(payload)
        recognition = merge_instances(instances, request.conflict_resolutions, normalized=True)
        if recognition["unresolvedConflictCount"]:
            raise HTTPException(409, {
                "message": "存在未处理的 LIMS 数据冲突",
                "conflicts": recognition["conflicts"],
            })
        payload = recognition["payload"]
        apply_group_contracts(payload, list_system_field_groups(database))
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
        word_edit_locked=0, word_edited_at=None,
    )
    database.create_version(report_id, data, f"载入 LIMS 实验记录 {', '.join(request.instance_ids)}")
    return report_response(updated)


app.include_router(create_report_word_router(
    database, settings, auth, rule_admin, required_report, required_owned_report,
    runtime_template_and_mappings, render_report_word, require_automatic_edit_allowed,
    _apply_content_block_rules,
))
app.include_router(create_report_source_router(database, settings, auth, required_owned_report,
                                               report_response, render_report_word))

frontend_dist = settings.data_dir.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
