import hashlib
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Database, now_iso
from .admin_api import create_admin_router
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
from .services.pdf_extractor import extract_pdf
from .services.rule_admin import RuleAdminRepository
from .services.template_compiler import compile_template


settings = get_settings()
database = Database(settings.database_path)
rule_admin = RuleAdminRepository(database, settings.data_dir.parent / "mapping" / "template-mapping.json")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    database.initialize()
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
app.include_router(create_admin_router(rule_admin, settings))
app.include_router(create_lims_router(database, settings))


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


def render_report_word(item: dict, data: dict, payload: dict | None = None) -> str:
    template, mappings = runtime_template_and_mappings()
    output_name = f"report-{item['id']}.docx"
    active_payload = payload or data.get("source_payloads", {}).get("LIMS") or {}
    build_mapped_docx(template, settings.reports_dir / output_name, mappings, active_payload, data)
    return output_name


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
async def upload_source(file: UploadFile = File(...)) -> SourceDocument:
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
def preview_source(source_id: str) -> FileResponse:
    item = required_source(source_id)
    return FileResponse(settings.uploads_dir / item["stored_name"], media_type="application/pdf", filename=item["file_name"])


@app.post(f"{settings.api_prefix}/source-documents/{{source_id}}/extract", response_model=SourceDocument)
def extract_source(source_id: str) -> SourceDocument:
    item = required_source(source_id)
    try:
        fields = extract_pdf(settings.uploads_dir / item["stored_name"], source_id)
    except Exception as error:
        raise HTTPException(422, f"PDF 解析失败：{error}") from error
    return source_response(database.update_extracted_fields(source_id, fields))


@app.get(f"{settings.api_prefix}/reports", response_model=list[ReportTask])
def list_reports() -> list[ReportTask]:
    return [report_response(item) for item in database.list_reports()]


@app.post(f"{settings.api_prefix}/reports", response_model=ReportTask)
def create_report(request: CreateReportRequest) -> ReportTask:
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
            "title": request.title or data["project_name"] or "未命名报告",
            "status": "DATA_REVIEW",
            "source_document_id": request.source_document_id,
            "resolved_data": data,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    database.create_version(report_id, data, "初始版本")
    return report_response(item)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ReportTask)
def get_report(report_id: str) -> ReportTask:
    return report_response(required_report(report_id))


@app.put(f"{settings.api_prefix}/reports/{{report_id}}", response_model=ReportTask)
def update_report(report_id: str, request: UpdateReportRequest) -> ReportTask:
    current = required_report(report_id)
    before = flatten_values(current["resolved_data"])
    after_data = request.data.model_dump()
    after = flatten_values(after_data)
    for field_code, new_value in after.items():
        old_value = before.get(field_code, "")
        if old_value != new_value:
            database.add_change(report_id, field_code, old_value, new_value)
    item = database.update_report(
        report_id,
        title=request.title or request.data.project_name or "未命名报告",
        resolved_data=after_data,
        status="READY_TO_GENERATE",
    )
    return report_response(item)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/bindings", response_model=list[FieldBinding])
def report_bindings(report_id: str) -> list[FieldBinding]:
    data = required_report(report_id)["resolved_data"]
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
def report_history(report_id: str, field_code: str | None = None) -> list[dict]:
    required_report(report_id)
    return database.list_changes(report_id, field_code)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/versions", response_model=list[ReportVersion])
def report_versions(report_id: str) -> list[dict]:
    required_report(report_id)
    return database.list_versions(report_id)


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/versions", response_model=ReportVersion)
def create_report_version(report_id: str, note: str = "手工保存") -> dict:
    item = required_report(report_id)
    return database.create_version(report_id, item["resolved_data"], note)


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/submit-review", response_model=ReportTask)
def submit_review(report_id: str) -> ReportTask:
    item = required_report(report_id)
    if not item["resolved_data"].get("report_no"):
        raise HTTPException(422, "报告编号不能为空")
    database.create_version(report_id, item["resolved_data"], "提交审核")
    return report_response(database.update_report(report_id, status="IN_REVIEW"))


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/generate", response_model=ReportTask)
def generate_report(report_id: str) -> ReportTask:
    item = required_report(report_id)
    try:
        output_name = render_report_word(item, item["resolved_data"])
    except Exception as error:
        raise HTTPException(500, f"报告生成失败：{error}") from error
    return report_response(database.update_report(report_id, status="GENERATED", output_name=output_name))


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/rebuild-word", response_model=ReportTask)
def rebuild_report_word(report_id: str) -> ReportTask:
    item = required_report(report_id)
    try:
        output_name = render_report_word(item, item["resolved_data"])
    except Exception as error:
        raise HTTPException(500, f"Word 重建失败：{error}") from error
    return report_response(database.update_report(report_id, status="EDITING", output_name=output_name))


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims-legacy", response_model=ReportTask,
          include_in_schema=False)
def apply_lims_to_report(report_id: str, request: ApplyLimsRequest) -> ReportTask:
    item = required_report(report_id)
    imported = database.get_lims_import(request.import_id)
    if not imported:
        raise HTTPException(404, "LIMS 导入记录不存在")
    try:
        payload = parse_lims_workbook(settings.lims_dir / imported["stored_name"], request.instance_id)
    except KeyError as error:
        raise HTTPException(404, "LIMS 实验实例不存在") from error
    except Exception as error:
        raise HTTPException(422, f"LIMS 数据读取失败：{error}") from error

    data = dict(item["resolved_data"])
    sample = payload.get("samples", [{}])[0] if payload.get("samples") else {}
    author = next((entry.get("field3") for entry in payload.get("approval", [])
                   if entry.get("field1") == "编制" and entry.get("field3")), payload.get("createdBy", ""))
    values = {
        "report_no": payload.get("document", {}).get("code") or payload["instanceId"],
        "project_name": payload.get("project", {}).get("name") or payload.get("title", ""),
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
        sources[code] = {"type": "LIMS", "record_id": sample.get("sourceRecordId") or payload["instanceId"]}
        originals[code] = value
        if old_value != value:
            database.add_change(report_id, code, old_value, value, reason="载入 LIMS 数据")
    data["field_sources"] = sources
    data["original_values"] = originals
    source_payloads = dict(data.get("source_payloads", {}))
    source_payloads["LIMS"] = payload
    data["source_payloads"] = source_payloads
    try:
        output_name = render_report_word(item, data, payload)
    except Exception as error:
        raise HTTPException(500, f"LIMS 数据填充 Word 失败：{error}") from error
    updated = database.update_report(
        report_id, title=data.get("project_name") or "未命名报告", resolved_data=data,
        status="EDITING", output_name=output_name,
    )
    database.create_version(report_id, data, f"载入 LIMS 实例 {request.instance_id}")
    return report_response(updated)


@app.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims", response_model=ReportTask)
def apply_lims_instances_to_report(report_id: str, request: ApplyLimsRequest) -> ReportTask:
    item = required_report(report_id)
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
            database.add_change(report_id, code, old_value, value, reason="载入 LIMS 数据")
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
        report_id, title=data.get("project_name") or "未命名报告", resolved_data=data,
        status="EDITING", output_name=output_name,
    )
    database.create_version(report_id, data, f"载入 LIMS 实验记录 {', '.join(request.instance_ids)}")
    return report_response(updated)


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/file")
def download_report(report_id: str) -> FileResponse:
    item = required_report(report_id)
    if not item.get("output_name"):
        raise HTTPException(409, "请先生成报告")
    path = settings.reports_dir / item["output_name"]
    if not path.exists():
        raise HTTPException(404, "报告文件不存在")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{item['title']}.docx",
    )


def ensure_report_file(item: dict) -> tuple[dict, Path]:
    if not item.get("output_name"):
        output_name = render_report_word(item, item["resolved_data"])
        item = database.update_report(item["id"], status="EDITING", output_name=output_name)
    path = settings.reports_dir / item["output_name"]
    if not path.exists():
        output_name = render_report_word(item, item["resolved_data"])
        item = database.update_report(item["id"], output_name=output_name)
        path = settings.reports_dir / output_name
    return item, path


@app.get(f"{settings.api_prefix}/onlyoffice/reports/{{report_id}}/config")
def onlyoffice_config(report_id: str) -> dict:
    if not settings.onlyoffice_jwt_secret:
        raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请设置 REPORT_ONLYOFFICE_JWT_SECRET")
    item, path = ensure_report_file(required_report(report_id))
    config = {
        "document": {
            "fileType": "docx",
            "key": document_key(report_id, path),
            "title": f"{item['resolved_data'].get('report_no') or item['title']}.docx",
            "url": f"{settings.public_base_url}{settings.api_prefix}/reports/{report_id}/file",
            "permissions": {"edit": True, "download": True, "print": True, "review": True},
        },
        "documentType": "word",
        "editorConfig": {
            "callbackUrl": f"{settings.public_base_url}{settings.api_prefix}/onlyoffice/callback/{report_id}",
            "lang": "zh-CN",
            "mode": "edit",
            "user": {"id": "local-user", "name": "当前用户"},
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
            temp_path.replace(output)
            database.create_version(report_id, item["resolved_data"], "ONLYOFFICE 自动保存")
            database.update_report(report_id, status="EDITING")
        except Exception as error:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(502, f"保存 ONLYOFFICE 文件失败：{error}") from error
    return {"error": 0}


frontend_dist = settings.data_dir.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
