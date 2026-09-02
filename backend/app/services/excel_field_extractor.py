import hashlib
from pathlib import Path
from typing import Any

from .excel_rule_engine import ExcelRuleError, WorkbookValues
from .excel_chart_extractor import ExcelChartError, extract_residual_chart_values
from .excel_validation_payload import enrich_excel_payload


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    raw_parts = [part for part in path.removeprefix("$").lstrip(".").split(".") if part]
    is_many = any("[*]" in part for part in raw_parts)
    parts = [part.replace("[*]", "") for part in raw_parts]
    if not parts:
        raise ExcelRuleError("Excel 规则缺少标准 JSON 路径")
    if is_many and len(parts) >= 2:
        collection = payload.setdefault(parts[0], [])
        if not isinstance(collection, list):
            collection = []
            payload[parts[0]] = collection
        while len(collection) < len(value) if isinstance(value, list) else 0:
            collection.append({})
        field_name = parts[-1]
        for index, item in enumerate(value if isinstance(value, list) else []):
            if not isinstance(collection[index], dict):
                collection[index] = {}
            if isinstance(item, dict):
                collection[index].update(item)
            else:
                collection[index][field_name] = item
        return
    current = payload
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _cell(reader: WorkbookValues, config: dict[str, Any]) -> Any:
    return reader.read(str(config.get("sheet") or ""), int(config.get("row", 0)),
                       int(config.get("column", 0)), bool(config.get("required")))


def _repeat_count(reader: WorkbookValues, config: dict[str, Any]) -> int:
    source = config.get("repeatCountSource")
    count = int(_cell(reader, source)) if isinstance(source, dict) else int(config.get("repeatCount", 1))
    maximum = int(config.get("maxRepeat", 100))
    if count < 0 or count > maximum:
        raise ExcelRuleError(f"循环次数 {count} 超出 0-{maximum} 范围")
    return count


def _repeat_values(reader: WorkbookValues, config: dict[str, Any]) -> list[Any]:
    count = _repeat_count(reader, config)
    row_start, row_end = int(config.get("rowStart", 1)), int(config.get("rowEnd", 1))
    if "rowStartOffsetFromRepeatCount" in config:
        row_start = count + int(config["rowStartOffsetFromRepeatCount"])
        row_end = row_start + int(config.get("rowCount", 1)) - 1
    if row_end < row_start or row_end - row_start > 1000:
        raise ExcelRuleError("Excel 数据行范围无效")
    values: list[Any] = []
    for repeat_index in range(count):
        mode = str(config.get("valueMode") or "CELL")
        if mode.startswith("LINEAR_"):
            value = _linear_statistic(reader, config, repeat_index, mode)
            if config.get("broadcastRepeat"):
                values.extend([value] * int(config.get("valueCount", 1)))
            else:
                values.append(value)
            continue
        if mode == "HORIZONTAL_CELL":
            row = row_start + repeat_index * int(config.get("rowStep", 0))
            start = int(config.get("startColumn", 1))
            values.extend(reader.read(str(config.get("sheet") or ""), row, start + offset,
                                      bool(config.get("required")))
                          for offset in range(int(config.get("valueCount", 1))))
            continue
        for row_index, row in enumerate(range(row_start, row_end + 1)):
            if mode == "INDEX":
                value = row_index + int(config.get("indexBase", 1))
            elif mode == "REPEAT_VALUE":
                source = config.get("repeatValueSource") or {}
                value = reader.read(str(source.get("sheet") or ""),
                                    int(source.get("row", 0)) + repeat_index * int(source.get("rowStep", 0)),
                                    int(source.get("column", 0)) + repeat_index * int(source.get("columnStep", 0)),
                                    bool(config.get("required")))
            else:
                value = reader.read(str(config.get("sheet") or ""),
                                    row + repeat_index * int(config.get("rowStep", 0)) + int(config.get("rowOffset", 0)),
                                    int(config.get("startColumn", 1)) + repeat_index * int(config.get("columnStep", 0))
                                    + int(config.get("columnOffset", 0)), bool(config.get("required")))
            repeat_value = int(config.get("broadcastRepeat", 1))
            if repeat_value < 1 or repeat_value > 1000:
                raise ExcelRuleError("重复值展开次数无效")
            values.extend([value] * repeat_value)
    return values


def _linear_statistic(reader: WorkbookValues, config: dict[str, Any], repeat_index: int,
                      mode: str) -> Any:
    sheet = str(config.get("sheet") or "")
    row_step = int(config.get("rowStep", 0))
    column = int(config.get("startColumn", 1))
    count = int(config.get("valueCount", 5))
    x_row = int(config.get("xRow", 1)) + repeat_index * row_step
    y_row = int(config.get("yRow", 1)) + repeat_index * row_step
    pairs = [(reader.read(sheet, x_row, column + offset), reader.read(sheet, y_row, column + offset))
             for offset in range(count)]
    numeric = [(float(x), float(y)) for x, y in pairs if x not in (None, "") and y not in (None, "")]
    if len(numeric) < 2:
        return None
    xs, ys = zip(*numeric)
    x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if not denominator:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in numeric) / denominator
    intercept = y_mean - slope * x_mean
    if mode == "LINEAR_EQUATION":
        sign = "+" if intercept >= 0 else "-"
        return f"y = {slope:.4f}x {sign} {abs(intercept):.4f}"
    fitted = [slope * x + intercept for x in xs]
    residual = sum((y - estimate) ** 2 for y, estimate in zip(ys, fitted))
    total = sum((y - y_mean) ** 2 for y in ys)
    if mode == "LINEAR_R2":
        return round(1 - residual / total, 6) if total else 1.0
    center = ys[len(ys) // 2]
    return round(abs(intercept) / center * 100, 2) if center else None


def _normalize_cardinality(value: Any, field: dict[str, Any], field_code: str,
                           warnings: list[str]) -> Any:
    if field.get("cardinality") != "ONE" or not isinstance(value, list):
        return value
    available = [item for item in value if item not in (None, "")]
    if len(available) > 1:
        warnings.append(f"单值字段 {field_code} 提取到 {len(available)} 个值，使用第一个有效值")
    return available[0] if available else None


def _path_values(payload: dict[str, Any], path: str) -> list[Any]:
    parts = [part.replace("[*]", "") for part in path.removeprefix("$").lstrip(".").split(".") if part]
    current: Any = payload
    for part in parts:
        if isinstance(current, list):
            current = [item.get(part) if isinstance(item, dict) else None for item in current]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return []
    return current if isinstance(current, list) else []


def _generated_sequences(payload: dict[str, Any], fields: dict[str, dict[str, Any]],
                         config: dict[str, Any]) -> list[int | None]:
    dependency = fields.get(str(config.get("sequenceDependency") or ""))
    if not dependency:
        raise ExcelRuleError("序号依据字段不存在")
    path = str(dependency.get("legacyJsonPath") or dependency["fieldCode"])
    values = _path_values(payload, path)
    group_size = int(config.get("rowEnd", 1)) - int(config.get("rowStart", 1)) + 1
    if group_size <= 0:
        raise ExcelRuleError("序号规则的数据行范围无效")
    result: list[int | None] = []
    for offset in range(0, len(values), group_size):
        number = 0
        for value in values[offset:offset + group_size]:
            if value in (None, ""):
                result.append(None)
            else:
                number += 1
                result.append(number)
    return result


def extract_excel_fields(path: Path, fields: list[dict[str, Any]], rules: list[dict[str, Any]]) -> dict[str, Any]:
    reader, payload = WorkbookValues(path), {}
    fields_by_code = {str(field["fieldCode"]): field for field in fields}
    rules_by_field: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        if rule.get("enabled", True) and rule.get("sourceType") == "EXCEL":
            rules_by_field.setdefault(str(rule["fieldCode"]), []).append(rule)
    generated: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for field_code, candidates in rules_by_field.items():
        field = fields_by_code.get(field_code)
        if not field:
            continue
        for rule in sorted(candidates, key=lambda item: (item.get("priority", 100), item.get("id", 0))):
            config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
            if config.get("generateSequence"):
                generated.append((field_code, field, config))
                break
            try:
                if config.get("mode") == "CHART_IMAGE":
                    value = extract_residual_chart_values(path, int(config.get("pointsPerTest", 5)))
                else:
                    value = _cell(reader, config) if config.get("mode") == "FIXED_CELL" else _repeat_values(reader, config)
            except (ExcelRuleError, ExcelChartError, KeyError, TypeError, ValueError) as error:
                reader.warnings.append(f"字段 {field_code} 提取失败：{error}")
                continue
            value = _normalize_cardinality(value, field, field_code, reader.warnings)
            if value not in (None, "", []):
                _set_path(payload, str(config.get("sourcePath") or field.get("legacyJsonPath") or field_code), value)
                break
    for field_code, field, config in generated:
        try:
            value = _generated_sequences(payload, fields_by_code, config)
            _set_path(payload, str(config.get("sourcePath") or field.get("legacyJsonPath") or field_code), value)
        except (ExcelRuleError, KeyError, TypeError, ValueError) as error:
            reader.warnings.append(f"字段 {field_code} 序号生成失败：{error}")
    enrich_excel_payload(payload)
    conclusion = payload.get("systemSuitabilityConclusion")
    records = payload.get("systemSuitability")
    if conclusion not in (None, "") and isinstance(records, list) and records:
        records[0]["conclusion"] = conclusion
    payload["_meta"] = {"format": "CONFIGURED_FIELD_RULES", "warnings": reader.warnings,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return payload
