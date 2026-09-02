import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from lxml import html


def _parts(path: str) -> list[str]:
    value = path.strip().removeprefix("$").lstrip(".")
    return [part for part in value.replace("[*]", "").split(".") if part]


def _read_path(source: Any, path: str) -> Any:
    values = [source]
    raw_parts = path.strip().removeprefix("$").lstrip(".").split(".")
    for raw_part in raw_parts:
        many = raw_part.endswith("[*]")
        part = raw_part[:-3] if many else raw_part
        next_values: list[Any] = []
        for value in values:
            current = value.get(part) if isinstance(value, dict) else None
            if many and isinstance(current, list):
                next_values.extend(current)
            elif current is not None:
                next_values.append(current)
        values = next_values
    if "[*]" in path:
        return values
    return values[0] if values else None


def _matches(pattern: str, text: str) -> bool:
    if not pattern:
        return True
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return pattern.lower() in text.lower()


def _capture(value: Any, pattern: str, field_code: str = "") -> Any:
    if not pattern or value in (None, ""):
        return value
    try:
        match = re.search(pattern, str(value), re.IGNORECASE | re.DOTALL)
    except re.error as error:
        raise ValueError(f"字段 {field_code} 的 valuePattern 正则无效：{pattern}（{error}）") from error
    if not match:
        return None
    return match.group(1) if match.groups() else match.group(0)


def _transform(value: Any, field: dict[str, Any], rule: dict[str, Any]) -> Any:
    if value in (None, ""):
        value = field.get("defaultValue") or None
    if value is None:
        return None
    transform = str(rule.get("transform") or "TRIM").upper()
    text = re.sub(r"\s+", " ", str(value)).strip()
    if transform == "UPPER":
        value = text.upper()
    elif transform == "LOWER":
        value = text.lower()
    elif transform in {"NUMBER", "DECIMAL"} or field.get("dataType") == "decimal":
        try:
            number = Decimal(text.replace(",", "").replace("%", ""))
            output_format = str(field.get("outputFormat") or "")
            if output_format.isdigit():
                number = number.quantize(Decimal(1).scaleb(-int(output_format)))
            value = str(number)
        except InvalidOperation:
            return None
    elif transform == "DATE" or field.get("dataType") == "date":
        output_format = str(field.get("outputFormat") or "%Y-%m-%d")
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00")).strftime(output_format)
        except ValueError:
            value = text
    else:
        value = text
    validation = str(field.get("validationRegex") or "")
    if validation:
        try:
            matched = re.fullmatch(validation, str(value))
        except re.error as error:
            raise ValueError(
                f"字段 {field.get('fieldCode') or ''} 的 validationRegex 正则无效：{validation}（{error}）") from error
        if not matched:
            return None
    return value


def _table_values(instance: dict[str, Any], rule: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for rich_text in instance.get("richTexts", []):
        section = ">".join(rich_text.get("sectionPath", []))
        if not _matches(str(rule.get("sectionPattern") or ""), section):
            continue
        try:
            root = html.fragment_fromstring(rich_text.get("html") or "", create_parent="div")
        except (TypeError, ValueError):
            continue
        for table in root.xpath(".//table"):
            rows = [[re.sub(r"\s+", " ", "".join(cell.itertext())).strip()
                     for cell in row.xpath("./th|./td")] for row in table.xpath(".//tr")]
            if not rows:
                continue
            header = "|".join(rows[0])
            if not _matches(str(rule.get("headerPattern") or ""), header):
                continue
            config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
            row_pattern = str(rule.get("rowPattern") or config.get("rowPattern") or "")
            source_header = str(rule.get("sourcePath") or "")
            try:
                column = next(index for index, name in enumerate(rows[0])
                              if _matches(source_header, name))
            except StopIteration:
                continue
            values.extend(
                row[column] for row in rows[1:]
                if len(row) > column and row[column]
                and (not row_pattern or _matches(
                    row_pattern, "|".join(f"{name}={value}" for name, value in zip(rows[0], row))
                ))
            )
    return values


def _extract(instance: dict[str, Any], payload: dict[str, Any], rule: dict[str, Any]) -> Any:
    source_type = str(rule.get("sourceType") or "NORMALIZED_PATH")
    if source_type == "NORMALIZED_PATH":
        return _read_path(payload, str(rule.get("sourcePath") or ""))
    if source_type == "RAW_UNIT_FIELD":
        values = []
        for item in instance.get("rawStructured", []):
            if rule.get("sourceUnitType") and item.get("unitType") != rule["sourceUnitType"]:
                continue
            value = _read_path(item.get("data", {}), str(rule.get("sourcePath") or ""))
            if value not in (None, ""):
                values.append(value)
        return values
    if source_type == "RICH_TEXT_REGEX":
        values = []
        for item in instance.get("richTexts", []):
            section = ">".join(item.get("sectionPath", []))
            if _matches(str(rule.get("sectionPattern") or ""), section):
                value = item.get("plainText", "")
                if value not in (None, ""):
                    values.append(value)
        return values
    if source_type == "HTML_TABLE_COLUMN":
        return _table_values(instance, rule)
    return None


def _write(payload: dict[str, Any], field: dict[str, Any], value: Any) -> None:
    path = field.get("legacyJsonPath") or field.get("fieldCode") or ""
    parts = _parts(str(path))
    if not parts:
        return
    if field.get("cardinality") == "MANY":
        collection = payload.setdefault(parts[0], [])
        key = parts[-1]
        values = value if isinstance(value, list) else [value]
        for index, item_value in enumerate(values):
            if item_value in (None, ""):
                continue
            while index >= len(collection):
                collection.append({})
            if isinstance(collection[index], dict):
                collection[index][key] = item_value
        return
    target = payload
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def apply_configured_extraction(
    instance: dict[str, Any],
    payload: dict[str, Any],
    fields: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    by_field: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        if rule.get("enabled", True):
            by_field.setdefault(str(rule.get("fieldCode") or ""), []).append(rule)
    for field in fields:
        if not field.get("enabled", True):
            continue
        candidates = sorted(by_field.get(field["fieldCode"], []), key=lambda item: item.get("priority", 100))
        for rule in candidates:
            extracted = _extract(instance, payload, rule)
            values = extracted if isinstance(extracted, list) else [extracted]
            transformed = [_transform(_capture(value, str(rule.get("valuePattern") or ""), field.get("fieldCode", "")),
                                       field, rule)
                           for value in values]
            if field.get("cardinality") == "MANY":
                if any(value not in (None, "") for value in transformed):
                    # 保留行位置：空值不回填，避免后续行整体前移错位
                    _write(payload, field, transformed)
                    break
                continue
            available = next((value for value in transformed if value not in (None, "")), None)
            if available is not None:
                _write(payload, field, available)
                break
    return payload
