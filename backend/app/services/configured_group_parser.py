import re
from typing import Any


def _matches(pattern: Any, text: str) -> bool:
    value = str(pattern or "")
    if not value:
        return True
    try:
        return bool(re.search(value, text, re.IGNORECASE))
    except re.error as error:
        raise ValueError(f"编组来源映射正则无效：{value}") from error


def _column_index(headers: list[str], pattern: Any) -> int | None:
    value = str(pattern or "")
    if not value:
        return None
    for index, header in enumerate(headers):
        if _matches(value, header):
            return index
    return None


def apply_configured_group_tables(
    rows: list[list[str]], section_path: str, groups: list[dict[str, Any]],
    evidence: dict[str, Any], output: dict[str, list[dict[str, Any]]],
) -> set[str]:
    """Apply group-level Excel/LIMS table mappings to a normalized payload."""
    if not rows:
        return set()
    headers = rows[0]
    header_text = "|".join(headers)
    matched_targets: set[str] = set()
    for group in groups:
        if not group.get("enabled", True):
            continue
        target = str(group.get("groupCode") or "").strip()
        if not target:
            continue
        for mapping in group.get("sourceMappings") or []:
            if str(mapping.get("sourceType") or "").upper() != "LIMS":
                continue
            if not _matches(mapping.get("sectionPattern") or mapping.get("worksheetPattern"), section_path):
                continue
            if not _matches(mapping.get("headerPattern"), header_text):
                continue
            columns = mapping.get("columnMappings", mapping.get("fieldMappings", mapping.get("columns", [])))
            indexes = [(item, _column_index(headers, item.get("columnPattern", item.get("column"))))
                       for item in columns if isinstance(item, dict)]
            indexes = [(item, index) for item, index in indexes if index is not None]
            if not indexes:
                continue
            row_pattern = mapping.get("rowPattern")
            for row in rows[1:]:
                if not any(str(value or "").strip() for value in row):
                    continue
                row_text = "|".join(
                    f"{header}={str(value or '').strip()}" for header, value in zip(headers, row)
                )
                if not _matches(row_pattern, row_text):
                    continue
                record = {str(item["fieldCode"]).split(".")[-1]:
                          (str(row[index]).strip() if index < len(row) else "")
                          for item, index in indexes}
                record["evidence"] = evidence
                output.setdefault(target, []).append(record)
            matched_targets.add(target)
    return matched_targets
