from typing import Any

from ..schemas import SourceDocument
from .excel_validation_payload import enrich_excel_payload, merge_excel_validation_results


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
    payloads["LIMS"] = merge_excel_validation_results(payloads.get("LIMS") or {}, excel_payload)
    payloads["EXCEL_DOCUMENT"] = {
        "id": source["id"], "fileName": source["file_name"], "sha256": source.get("sha256", ""),
        "downloadUrl": f"{api_prefix}/source-documents/{source['id']}/preview",
    }
    warnings = data.setdefault("warnings", [])
    for warning in source.get("warnings", []):
        if warning not in warnings:
            warnings.append(warning)
    project = excel_payload.get("project", {}) if isinstance(excel_payload, dict) else {}
    if not data.get("project_name") and isinstance(project, dict):
        data["project_name"] = str(project.get("name") or "")


def apply_pdf_source(data: dict[str, Any], source: dict[str, Any]) -> None:
    for field in source["extracted_fields"]:
        code, value = field["field_code"], field["value"]
        if code in data and not data[code]:
            data[code] = value
        data.setdefault("field_sources", {})[code] = field["source"]
        data.setdefault("original_values", {})[code] = value
