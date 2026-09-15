import hashlib
import re
from pathlib import Path
from typing import Any

from .excel_rule_engine import ExcelRuleError, WorkbookValues
from .excel_chart_extractor import ExcelChartError, extract_residual_chart_values
from .excel_standard_path import excel_target_path
from .payload_paths import PayloadPathError, path_depth, set_payload_path


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
                x_row = int(config.get("xRow", 1)) + repeat_index * int(config.get("rowStep", 0))
                y_row = int(config.get("yRow", 1)) + repeat_index * int(config.get("rowStep", 0))
                count = _horizontal_count(reader, config, x_row, int(config.get("startColumn", 1)), y_row)
                values.extend([value] * count)
            else:
                values.append(value)
            continue
        if mode == "HORIZONTAL_CELL":
            row = row_start + repeat_index * int(config.get("rowStep", 0))
            start = int(config.get("startColumn", 1))
            count = _horizontal_count(reader, config, row, start)
            values.extend(reader.read(str(config.get("sheet") or ""), row, start + offset,
                                      bool(config.get("required")))
                          for offset in range(count))
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
    x_row = int(config.get("xRow", 1)) + repeat_index * row_step
    y_row = int(config.get("yRow", 1)) + repeat_index * row_step
    count = _horizontal_count(reader, config, x_row, column, y_row)
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


def _horizontal_count(reader: WorkbookValues, config: dict[str, Any], row: int,
                      start_column: int, paired_row: int | None = None) -> int:
    mode = str(config.get("valueCountMode") or "CONFIGURED")
    if mode == "CONFIGURED":
        try:
            count = int(config["valueCount"])
        except (KeyError, TypeError, ValueError) as error:
            raise ExcelRuleError("横向 Excel 规则必须配置 valueCount 或使用 UNTIL_BLANK") from error
        if count < 1 or count > int(config.get("maxValueCount", 1000)):
            raise ExcelRuleError("横向 Excel 规则的 valueCount 超出允许范围")
        return count
    if mode != "UNTIL_BLANK":
        raise ExcelRuleError("横向 Excel 规则的 valueCountMode 只能是 CONFIGURED 或 UNTIL_BLANK")
    try:
        maximum = int(config.get("maxValueCount", 1000))
    except (TypeError, ValueError) as error:
        raise ExcelRuleError("横向 Excel 规则的 maxValueCount 必须是正整数") from error
    if maximum < 1 or maximum > 10000:
        raise ExcelRuleError("横向 Excel 规则的 maxValueCount 必须在 1 到 10000 之间")
    count = 0
    for offset in range(maximum):
        value = reader.read(str(config.get("sheet") or ""), row, start_column + offset)
        paired = reader.read(str(config.get("sheet") or ""), paired_row, start_column + offset) if paired_row else value
        if value in (None, "") and paired in (None, ""):
            break
        count += 1
    return count


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
            collected: list[Any] = []
            for item in current:
                value = item.get(part) if isinstance(item, dict) else None
                collected.extend(value) if isinstance(value, list) else collected.append(value)
            current = collected
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


def _seed_group_collections(reader: WorkbookValues, payload: dict[str, Any],
                            pending: list[tuple[str, str, Any]],
                            fields: dict[str, dict[str, Any]],
                            configs: dict[str, dict[str, Any]]) -> None:
    """先按 Excel 规则的重复次数建立编组外层，供嵌套字段切分明细。"""
    sizes: dict[str, int] = {}
    for field_code, target, _ in pending:
        if path_depth(target) < 2:
            continue
        field = fields.get(field_code) or {}
        group_code = str(field.get("groupCode") or "").strip()
        if not group_code:
            continue
        config = configs.get(field_code) or {}
        try:
            count = _repeat_count(reader, config)
        except (ExcelRuleError, TypeError, ValueError):
            continue
        sizes[group_code] = max(sizes.get(group_code, 0), count)
    for group_code, count in sizes.items():
        if count < 1:
            continue
        existing = payload.get(group_code)
        if existing is None:
            payload[group_code] = [{} for _ in range(count)]
        elif not isinstance(existing, list) or len(existing) != count:
            raise PayloadPathError(
                f"编组 {group_code} 的外层记录数与 Excel 重复次数不一致"
            )


def extract_excel_fields(path: Path, fields: list[dict[str, Any]], rules: list[dict[str, Any]],
                         groups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    reader, payload = WorkbookValues(path), {}
    fields_by_code = {str(field["fieldCode"]): field for field in fields}
    rules_by_field: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        if rule.get("enabled", True) and rule.get("sourceType") == "EXCEL":
            rules_by_field.setdefault(str(rule["fieldCode"]), []).append(rule)
    generated: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    pending: list[tuple[str, str, Any]] = []
    pending_configs: dict[str, dict[str, Any]] = {}
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
                pending.append((field_code, excel_target_path(field, config.get("sourcePath")), value))
                pending_configs[field_code] = config
                break
    _seed_group_collections(reader, payload, pending, fields_by_code, pending_configs)
    # 分层编组里明细层要按外层数组切分，必须等分组层先把外层建好，所以按数组层数排序写入
    for field_code, target, value in sorted(pending, key=lambda item: path_depth(item[1])):
        try:
            set_payload_path(payload, target, value)
        except PayloadPathError as error:
            reader.warnings.append(f"字段 {field_code} 落位失败：{error}")
    for field_code, field, config in generated:
        target = excel_target_path(field, config.get("sourcePath"))
        try:
            set_payload_path(payload, target, _generated_sequences(payload, fields_by_code, config))
        except (ExcelRuleError, PayloadPathError, KeyError, TypeError, ValueError) as error:
            reader.warnings.append(f"字段 {field_code} 序号生成失败：{error}")
    _apply_group_source_mappings(reader, payload, fields_by_code, groups or [])
    payload["_meta"] = {"format": "CONFIGURED_FIELD_RULES", "warnings": reader.warnings,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return payload


def _apply_group_source_mappings(reader: WorkbookValues, payload: dict[str, Any],
                                 fields_by_code: dict[str, dict[str, Any]],
                                 groups: list[dict[str, Any]]) -> None:
    """按编组来源映射从 Excel 工作表读取列，并写入编组对应的数据列表。"""
    for group in groups:
        if not group.get("enabled", True):
            continue
        item_path = str(group.get("itemPath") or "").strip()
        mappings = group.get("sourceMappings") or []
        if not item_path or str(group.get("cardinality") or "ONE").upper() != "MANY":
            continue
        payload_key = str(group.get("groupCode") or "").strip()
        if not payload_key:
            continue
        for mapping in mappings:
            if str(mapping.get("sourceType") or "").upper() != "EXCEL":
                continue
            sheet = str(mapping.get("worksheetPattern") or mapping.get("sheet") or "").strip()
            if not sheet:
                continue
            try:
                sheet_names = [name for name in reader.values.sheetnames if re.search(sheet, name, re.IGNORECASE)]
            except re.error as error:
                raise ExcelRuleError(f"编组来源映射正则无效：{sheet}") from error
            for sheet_name in sheet_names:
                rows = list(reader.values[sheet_name].iter_rows(values_only=True))
                if not rows:
                    continue
                headers = [str(value or "").strip() for value in rows[0]]
                header_pattern = str(mapping.get("headerPattern") or "").strip()
                if header_pattern:
                    try:
                        if not re.search(header_pattern, "|".join(headers), re.IGNORECASE):
                            continue
                    except re.error as error:
                        raise ExcelRuleError(f"编组来源映射正则无效：{header_pattern}") from error
                indexes = []
                columns = mapping.get("columnMappings", mapping.get("fieldMappings", mapping.get("columns", [])))
                for column in columns:
                    field_code = str(column.get("fieldCode") or "").strip()
                    pattern = str(column.get("columnPattern") or column.get("column") or "").strip()
                    if field_code not in fields_by_code or not pattern:
                        continue
                    try:
                        index = next((i for i, header in enumerate(headers) if re.search(pattern, header, re.IGNORECASE)), None)
                    except re.error as error:
                        raise ExcelRuleError(f"编组来源映射正则无效：{pattern}") from error
                    if index is not None:
                        indexes.append((field_code, index))
                if not indexes:
                    continue
                records = []
                for row in rows[1:]:
                    if not any(value not in (None, "") for value in row):
                        continue
                    record = {}
                    for field_code, index in indexes:
                        field = fields_by_code[field_code]
                        key_path = str(field.get("fieldPath") or field.get("jsonKey") or field_code.rsplit(".", 1)[-1])
                        target = record
                        raw_parts = [part for part in key_path.split(".") if part]
                        for raw_part in raw_parts[:-1]:
                            part, is_array = raw_part.replace("[*]", ""), "[*]" in raw_part
                            if is_array:
                                collection = target.setdefault(part, [{}])
                                target = collection[0]
                            else:
                                target = target.setdefault(part, {})
                        target[raw_parts[-1].replace("[*]", "")] = row[index] if index < len(row) else None
                    records.append(record)
                if records:
                    existing = payload.get(payload_key)
                    if existing is not None and not isinstance(existing, list):
                        raise ExcelRuleError(f"编组 {group.get('groupCode')} 的数据列表冲突：{payload_key}")
                    payload[payload_key] = (existing or []) + records
