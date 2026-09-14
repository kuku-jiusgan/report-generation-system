import re
from pathlib import Path

import fitz


def _rule_pattern(field: dict, rule: dict) -> re.Pattern[str] | None:
    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    pattern = str(config.get("pattern") or config.get("valuePattern") or "").strip()
    if not pattern:
        label = re.escape(str(field.get("label") or field.get("fieldCode") or ""))
        pattern = rf"{label}\s*[：:]\s*([^\r\n]+)"
    try:
        return re.compile(pattern, re.IGNORECASE | re.DOTALL)
    except re.error as error:
        raise ValueError(f"字段 {field.get('fieldCode', '')} 的 PDF 提取规则正则无效：{error}") from error


def extract_pdf(path: Path, document_id: str, fields: list[dict], rules: list[dict]) -> list[dict]:
    fields_by_code = {str(field["fieldCode"]): field for field in fields}
    rules_by_field: dict[str, list[dict]] = {}
    for rule in rules:
        if rule.get("enabled", True) and str(rule.get("sourceType") or "").upper() == "PDF":
            rules_by_field.setdefault(str(rule.get("fieldCode") or ""), []).append(rule)
    results: dict[str, dict] = {}
    with fitz.open(path) as document:
        for page_index, page in enumerate(document):
            text = page.get_text("text")
            for field_code, candidates in rules_by_field.items():
                if field_code in results:
                    continue
                field = fields_by_code.get(field_code)
                if not field:
                    continue
                for rule in sorted(candidates, key=lambda item: (item.get("priority", 100), item.get("id", 0))):
                    match = _rule_pattern(field, rule).search(text)
                    if not match:
                        continue
                    value = (match.group(1) if match.groups() else match.group(0)).strip().rstrip("；;")
                    rectangles = page.search_for(value)
                    results[field_code] = {"field_code": field_code, "label": field.get("label", field_code),
                        "value": value, "confidence": 0.95, "source": {"type": "PDF", "document_id": document_id,
                        "page": page_index + 1, "quote": match.group(0).strip(), "rect": list(rectangles[0]) if rectangles else None}}
                    break
    return list(results.values())
