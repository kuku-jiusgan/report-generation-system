from typing import Any

from .excel_validation_payload import enrich_excel_payload, merge_excel_validation_results


def replace_report_source(data: dict[str, Any], source: dict[str, Any], source_type: str,
                          api_prefix: str) -> dict[str, Any]:
    payloads = dict(data.get("source_payloads", {}))
    if source_type == "EXCEL":
        excel_payload = enrich_excel_payload(source.get("payload") or {})
        payloads["EXCEL"] = excel_payload
        payloads["LIMS"] = merge_excel_validation_results(payloads.get("LIMS") or {}, excel_payload)
        payloads["EXCEL_DOCUMENT"] = {
            "id": source["id"], "fileName": source["file_name"],
            "sha256": source.get("sha256", ""),
            "downloadUrl": f"{api_prefix}/source-documents/{source['id']}/preview",
        }
        project = excel_payload.get("project", {})
        if isinstance(project, dict) and project.get("name"):
            data["project_name"] = str(project["name"])
    else:
        values = dict(data.get("original_values", {}))
        sources = dict(data.get("field_sources", {}))
        old_pdf_codes = [code for code, detail in sources.items()
                         if isinstance(detail, dict) and detail.get("type") == "PDF"]
        for code in old_pdf_codes:
            values.pop(code, None)
            sources.pop(code, None)
            # 顶层键是渲染时的直接取值来源，必须一并清除，否则旧 PDF 值会残留进新报告
            data.pop(code, None)
        for field in source.get("extracted_fields", []):
            code = str(field.get("field_code") or "")
            if code:
                values[code] = field.get("value", "")
                sources[code] = field.get("source", {"type": "PDF", "document_id": source["id"]})
        data["original_values"] = values
        data["field_sources"] = sources
        payloads["PDF_DOCUMENT"] = {
            "id": source["id"], "fileName": source["file_name"], "sha256": source.get("sha256", ""),
        }
    data["source_payloads"] = payloads
    warnings = data.setdefault("warnings", [])
    for warning in source.get("warnings", []):
        if warning not in warnings:
            warnings.append(warning)
    return data
