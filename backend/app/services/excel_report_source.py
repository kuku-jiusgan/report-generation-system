from typing import Any

from ..schemas import SourceDocument
from .excel_validation_payload import enrich_excel_payload


def build_source_document(item: dict[str, Any], api_prefix: str) -> SourceDocument:
    values = dict(item)
    payload = values.pop("payload", {})
    meta = payload.get("_meta", {}) if isinstance(payload, dict) else {}
    return SourceDocument(
        **values,
        preview_url=f"{api_prefix}/source-documents/{values['id']}/preview",
        summary={"impurityCount": meta.get("impurityCount", 0),
                 "impurityNames": meta.get("impurityNames", [])},
    )


def apply_excel_source(data: dict[str, Any], source: dict[str, Any], api_prefix: str) -> None:
    excel_payload = enrich_excel_payload(source.get("payload") or {})
    payloads = data.setdefault("source_payloads", {})
    payloads["EXCEL"] = excel_payload
    payloads["EXCEL_DOCUMENT"] = {
        "id": source["id"], "fileName": source["file_name"], "sha256": source.get("sha256", ""),
        "downloadUrl": f"{api_prefix}/source-documents/{source['id']}/preview",
    }
    warnings = data.setdefault("warnings", [])
    for warning in source.get("warnings", []):
        if warning not in warnings:
            warnings.append(warning)
    _record_excel_field_provenance(data, excel_payload)
    project = excel_payload.get("project", {}) if isinstance(excel_payload, dict) else {}
    if not data.get("project_name") and isinstance(project, dict):
        data["project_name"] = str(project.get("name") or "")


def _record_excel_field_provenance(data: dict[str, Any], payload: dict[str, Any]) -> None:
    """将 Excel 提取结果登记为字段级来源，供报告历史快照展示。"""
    custom = payload.get("custom")
    if not isinstance(custom, dict):
        return
    sources = data.setdefault("field_sources", {})
    originals = data.setdefault("original_values", {})
    for field_code, value in custom.items():
        if value in (None, "", []):
            continue
        code = str(field_code)
        sources[code] = {
            "type": "EXCEL",
            "record_id": str(payload.get("_meta", {}).get("sha256") or "EXCEL"),
            "sourcePath": code,
        }
        originals[code] = value


def apply_pdf_source(data: dict[str, Any], source: dict[str, Any]) -> None:
    pdf_payload = data.setdefault("source_payloads", {}).setdefault("PDF", {})
    for field in source["extracted_fields"]:
        code, value = field["field_code"], field["value"]
        pdf_payload[code] = value
        if code in data and not data[code]:
            data[code] = value
        data.setdefault("field_sources", {})[code] = field["source"]
        data.setdefault("original_values", {})[code] = value
