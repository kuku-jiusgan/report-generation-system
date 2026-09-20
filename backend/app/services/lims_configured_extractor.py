import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .system_field_rule_invariant import rules_by_field

from lxml import html

from .lims_table_utils import table_grid
from .payload_paths import set_payload_path


@dataclass(frozen=True)
class _LocatedValue:
    value: Any
    evidence: dict[str, Any]


def _rule_config(rule: dict[str, Any]) -> dict[str, Any]:
    config = rule.get("config")
    return config if isinstance(config, dict) else {}


def _extraction_type(rule: dict[str, Any]) -> str:
    return str(_rule_config(rule).get("extractionType") or "").upper()


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
    except re.error as error:
        raise ValueError(f"LIMS 提取规则正则无效：{pattern}（{error}）") from error


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


def _replace(value: str, field_code: str, rule: dict[str, Any]) -> str:
    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    pattern = str(config.get("replacePattern") or "")
    if not pattern:
        raise ValueError(f"字段 {field_code} 的正则替换未配置替换正则")
    replacement = str(config.get("replaceWith") or "")
    try:
        return re.sub(pattern, replacement, value)
    except re.error as error:
        raise ValueError(f"字段 {field_code} 的正则替换无效：{error}") from error


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
    elif transform == "REGEX_REPLACE":
        value = _replace(text, str(field.get("fieldCode") or ""), rule)
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


def _positive_int(value: Any, default: int, name: str) -> int:
    if value in (None, ""):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"LIMS 表格规则的{name}必须是整数") from error
    if result < 0:
        raise ValueError(f"LIMS 表格规则的{name}不能小于 0")
    return result


def _integer(value: Any, default: int, name: str) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"LIMS 表格规则的{name}必须是整数") from error


def _column_index(value: Any, width: int, name: str) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"LIMS 表格规则的{name}必须是整数") from error
    resolved = width + index if index < 0 else index
    if resolved < 0 or resolved >= width:
        raise ValueError(f"LIMS 表格规则的{name}超出表格列范围")
    return resolved


def _table_candidates(instance: dict[str, Any], rule: dict[str, Any]):
    config = _rule_config(rule)
    header_rows = _positive_int(config.get("headerRows"), 1, "表头行数")
    for rich_index, rich_text in enumerate(instance.get("richTexts", [])):
        section = ">".join(rich_text.get("sectionPath", []))
        if not _matches(str(config.get("sectionPattern") or ""), section):
            continue
        try:
            root = html.fragment_fromstring(rich_text.get("html") or "", create_parent="div")
        except (TypeError, ValueError):
            continue
        for table_index, table in enumerate(root.xpath(".//table"), start=1):
            rows = table_grid(table)
            if not rows:
                continue
            header = "|".join("|".join(row) for row in rows[:header_rows])
            if not _matches(str(config.get("headerPattern") or ""), header):
                continue
            rich_key = str(rich_text.get("id") or f"index:{rich_index}")
            yield rich_text, rich_key, table_index, rows


def _column_headers(rows: list[list[str]], header_rows: int) -> list[str]:
    width = max((len(row) for row in rows), default=0)
    return ["|".join(dict.fromkeys(
        row[column] for row in rows[:header_rows] if column < len(row) and row[column]
    )) for column in range(width)]


def _matching_rows(rows: list[list[str]], rule: dict[str, Any]):
    config = _rule_config(rule)
    row_pattern = str(config.get("rowPattern") or "")
    exclude_pattern = str(config.get("excludeRowPattern") or "")
    header_rows = _positive_int(config.get("headerRows"), 1, "表头行数")
    data_start = _positive_int(config.get("dataStartRow"), header_rows, "数据起始行")
    stride = max(1, _positive_int(config.get("rowStride"), 1, "行步长"))
    headers = _column_headers(rows, header_rows)
    for row_index in range(data_start, len(rows), stride):
        row = rows[row_index]
        row_text = "|".join(f"{name}={value}" for name, value in zip(headers, row))
        if not row_pattern or _matches(row_pattern, row_text):
            if not exclude_pattern or not _matches(exclude_pattern, row_text):
                yield row_index, row


def _table_evidence(instance: dict[str, Any], rich_text: dict[str, Any],
                    table_index: int, headers: list[str]) -> dict[str, Any]:
    evidence = dict(rich_text.get("evidence") or {})
    evidence.update({
        "type": "LIMS", "instanceId": instance.get("instanceId"),
        "instanceTitle": instance.get("title", ""), "sectionPath": rich_text.get("sectionPath", []),
        "richTextId": rich_text.get("id"), "tableIndex": table_index, "headers": headers,
    })
    return evidence


def _find_index(values: list[str], pattern: str) -> int | None:
    return next((index for index, value in enumerate(values) if _matches(pattern, value)), None)


def _row_values(rows: list[list[str]], rule: dict[str, Any]) -> list[tuple[int, int, Any]]:
    config = _rule_config(rule)
    header_rows = _positive_int(config.get("headerRows"), 1, "表头行数")
    headers = _column_headers(rows, header_rows)
    column = config.get("sourceColumnIndex")
    if column in (None, ""):
        column = _find_index(headers, str(config.get("sourcePath") or config.get("columnPattern") or ""))
    else:
        column = _column_index(column, len(headers), "取值列序号")
    if column is None:
        return []
    return [(row_index, column, row[column] if column < len(row) else "")
            for row_index, row in _matching_rows(rows, rule)]


def _column_values(rows: list[list[str]], rule: dict[str, Any]) -> list[tuple[int, int, Any]]:
    config = _rule_config(rule)
    width = max((len(row) for row in rows), default=0)
    row_label_column = _column_index(config.get("rowLabelColumn", 0), width, "行标题列序号")
    source_row = config.get("sourceRowIndex")
    if source_row in (None, ""):
        pattern = str(config.get("sourcePath") or "")
        source_row = next((index for index, row in enumerate(rows)
                           if row_label_column < len(row) and _matches(pattern, row[row_label_column])), None)
    else:
        source_row = _positive_int(source_row, 0, "取值行序号")
        if source_row >= len(rows):
            raise ValueError("LIMS 表格规则的取值行序号超出表格行范围")
    if source_row is None:
        return []
    start = _positive_int(config.get("dataStartColumn"), 1, "数据起始列")
    stride = max(1, _positive_int(config.get("columnStride"), 1, "列步长"))
    column_pattern = str(config.get("columnPattern") or "")
    headers = _column_headers(rows, _positive_int(config.get("headerRows"), 1, "表头行数"))
    return [(source_row, column, rows[source_row][column] if column < len(rows[source_row]) else "")
            for column in range(start, len(headers), stride)
            if not column_pattern or _matches(column_pattern, headers[column])]


def _matrix_value(rows: list[list[str]], row: int, column: int, config: dict[str, Any]) -> Any:
    value_row = config.get("valueRowIndex")
    value_column = config.get("valueColumnIndex")
    target_row = row + _integer(config.get("valueRowOffset"), 0, "取值行偏移")
    if value_row not in (None, ""):
        target_row = _positive_int(value_row, 0, "固定取值行序号")
    if target_row < 0 or target_row >= len(rows):
        raise ValueError("LIMS 表格规则的目标取值行超出表格范围")
    if value_column in (None, ""):
        target_column = column + _integer(config.get("valueColumnOffset"), 0, "取值列偏移")
    else:
        target_column = _column_index(value_column, len(rows[target_row]), "固定取值列序号")
    if target_column < 0 or target_column >= len(rows[target_row]):
        raise ValueError("LIMS 表格规则的目标取值列超出表格范围")
    return rows[target_row][target_column]


def _matrix_values(rows: list[list[str]], rule: dict[str, Any]) -> list[tuple[int, int, Any]]:
    config = _rule_config(rule)
    header_rows = _positive_int(config.get("headerRows"), 1, "表头行数")
    row_start = _positive_int(config.get("dataStartRow"), header_rows, "数据起始行")
    column_start = _positive_int(config.get("dataStartColumn"), 1, "数据起始列")
    row_stride = max(1, _positive_int(config.get("rowStride"), 1, "行步长"))
    column_stride = max(1, _positive_int(config.get("columnStride"), 1, "列步长"))
    row_pattern = str(config.get("rowPattern") or "")
    exclude_pattern = str(config.get("excludeRowPattern") or "")
    column_pattern = str(config.get("columnPattern") or "")
    headers = _column_headers(rows, header_rows)
    if row_start >= len(rows):
        return []
    output = []
    # A fixed value row (for example the impurity name in the matrix header)
    # defines one record per selected column.  Iterating every data row would
    # repeat that same header value once for each injection.
    row_indexes = ([row_start] if config.get("valueRowIndex") not in (None, "")
                   else range(row_start, len(rows), row_stride))
    for row in row_indexes:
        row_text = "|".join(rows[row])
        if (row_pattern and not _matches(row_pattern, row_text)) or (exclude_pattern and _matches(exclude_pattern, row_text)):
            continue
        for column in range(column_start, len(headers), column_stride):
            if column_pattern and not _matches(column_pattern, headers[column]):
                continue
            output.append((row, column, _matrix_value(rows, row, column, config)))
    return output


def _template_value(value: Any, rows: list[list[str]], row: int, column: int,
                    headers: list[str], config: dict[str, Any]) -> Any:
    template = str(config.get("valueTemplate") or "")
    if not template:
        return value
    header = headers[column] if column < len(headers) else ""
    header = _capture(header, str(config.get("headerValuePattern") or ""))
    variables = {
        "value": value, "header": header or "", "rowIndex": row, "columnIndex": column,
        "rowHeader": rows[row][0] if row < len(rows) and rows[row] else "",
    }
    try:
        return template.format_map(variables)
    except (KeyError, ValueError) as error:
        raise ValueError(f"LIMS 表格规则的取值模板无效：{error}") from error


def _table_values(instance: dict[str, Any], rule: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    mode = str(_rule_config(rule).get("recordMode") or "ROWS").upper()
    for rich_text, _, table_index, rows in _table_candidates(instance, rule):
        config = _rule_config(rule)
        headers = _column_headers(rows, _positive_int(config.get("headerRows"), 1, "表头行数"))
        evidence = _table_evidence(instance, rich_text, table_index, headers)
        if mode == "ROWS":
            located = _row_values(rows, rule)
        elif mode == "COLUMNS":
            located = _column_values(rows, rule)
        elif mode == "MATRIX":
            located = _matrix_values(rows, rule)
        else:
            raise ValueError(f"不支持的 LIMS 表格记录方向：{mode}")
        values.extend(
            _LocatedValue(
                _template_value(value, rows, row, column, headers, config),
                {**evidence, "rowIndex": row, "columnIndex": column},
            )
            for row, column, value in located
        )
    return values


def _table_rule(rule: dict[str, Any]) -> bool:
    return rule.get("enabled", True) and _extraction_type(rule) == "HTML_TABLE_COLUMN"


def configured_table_keys(
    instance: dict[str, Any], rules: list[dict[str, Any]] | None,
) -> set[tuple[str, int]]:
    """Return tables claimed by configured HTML column extraction rules."""
    table_rules = [rule for rule in rules or [] if _table_rule(rule)]
    claimed: set[tuple[str, int]] = set()
    for rule in table_rules:
        for _, rich_key, table_index, rows in _table_candidates(instance, rule):
            if _table_values_for_rows(rows, rule):
                claimed.add((rich_key, table_index))
    return claimed


def _table_values_for_rows(rows: list[list[str]], rule: dict[str, Any]) -> list[tuple[int, int, Any]]:
    mode = str(_rule_config(rule).get("recordMode") or "ROWS").upper()
    if mode == "ROWS":
        return _row_values(rows, rule)
    if mode == "COLUMNS":
        return _column_values(rows, rule)
    if mode == "MATRIX":
        return _matrix_values(rows, rule)
    raise ValueError(f"不支持的 LIMS 表格记录方向：{mode}")


def _extract(instance: dict[str, Any], payload: dict[str, Any], rule: dict[str, Any]) -> Any:
    del payload
    source_type = _extraction_type(rule)
    config = _rule_config(rule)
    if source_type == "INSTANCE_PATH":
        return _read_path(instance, str(config.get("sourcePath") or ""))
    if source_type == "RAW_UNIT_FIELD":
        values = []
        source_paths = config.get("sourcePaths")
        paths = [str(value) for value in source_paths] if isinstance(source_paths, list) else []
        if not paths:
            paths = [str(config.get("sourcePath") or "")]
        for item in instance.get("rawStructured", []):
            unit_type = str(config.get("sourceUnitType") or "")
            if unit_type and item.get("unitType") != unit_type:
                continue
            value = None
            for path in paths:
                candidate = _read_path(item.get("data", {}), path)
                if candidate not in (None, ""):
                    value = candidate
                    break
            values.append(_LocatedValue(value, dict(item.get("evidence") or {})))
        return values
    if source_type == "RICH_TEXT_REGEX":
        values = []
        for item in instance.get("richTexts", []):
            section = ">".join(item.get("sectionPath", []))
            if _matches(str(config.get("sectionPattern") or ""), section):
                value = item.get("plainText", "")
                if value not in (None, ""):
                    values.append(_LocatedValue(value, dict(item.get("evidence") or {})))
        return values
    if source_type == "HTML_TABLE_COLUMN":
        return _table_values(instance, rule)
    raise ValueError(f"不支持的 LIMS 字段提取方式：{source_type or '未配置'}")


def _write(payload: dict[str, Any], field: dict[str, Any], value: Any,
           evidences: list[dict[str, Any] | None] | None = None) -> None:
    path = field.get("legacyJsonPath") or field.get("fieldCode") or ""
    parts = _parts(str(path))
    if not parts:
        return
    if "[*]" in str(path):
        set_payload_path(payload, str(path), value if isinstance(value, list) else [value])
        if str(path).count("[*]") == 1 and evidences:
            collection = payload.get(parts[0])
            if isinstance(collection, list):
                for index, evidence in enumerate(evidences):
                    if evidence and index < len(collection) and isinstance(collection[index], dict):
                        collection[index].setdefault("evidence", evidence)
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
                if evidences and index < len(evidences) and evidences[index]:
                    collection[index].setdefault("evidence", evidences[index])
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
    by_field = rules_by_field(rules)
    for field in fields:
        if not field.get("enabled", True):
            continue
        rule = by_field.get(field["fieldCode"])
        if not rule or not rule.get("enabled", True):
            continue
        extracted = _extract(instance, payload, rule)
        values = extracted if isinstance(extracted, list) else [extracted]
        raw_values = [value.value if isinstance(value, _LocatedValue) else value for value in values]
        evidences = [value.evidence if isinstance(value, _LocatedValue) else None for value in values]
        transformed = [_transform(_capture(value, str(_rule_config(rule).get("valuePattern") or ""), field.get("fieldCode", "")),
                                  field, rule)
                       for value in raw_values]
        target_path = str(field.get("legacyJsonPath") or field.get("fieldCode") or "")
        if field.get("cardinality") == "MANY" or "[*]" in target_path:
            if any(value not in (None, "") for value in transformed):
                # 保留行位置：空值不回填，避免后续行整体前移错位
                _write(payload, field, transformed, evidences)
            continue
        available = next((value for value in transformed if value not in (None, "")), None)
        if available is not None:
            _write(payload, field, available)
    return payload
