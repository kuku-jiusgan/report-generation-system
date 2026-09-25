import hashlib
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from .excel_rule_engine import ExcelRuleError, WorkbookValues
from .excel_chart_extractor import (
    ExcelChartError,
    extract_regression_chart_values,
    extract_residual_chart_values,
)
from .excel_standard_path import excel_target_path
from .payload_paths import PayloadPathError, path_depth, set_payload_path


def _read_value(reader: WorkbookValues, config: dict[str, Any], sheet: str,
                row: int, column: int, required: bool | None = None) -> Any:
    return reader.read(sheet, row, column,
                       bool(config.get("required")) if required is None else required)


def _cell(reader: WorkbookValues, config: dict[str, Any]) -> Any:
    value = reader.read(str(config.get("sheet") or ""), int(config.get("row", 0)),
                        int(config.get("column", 0)), bool(config.get("required")))
    return _display_value(value, config)


def _merged_cell(reader: WorkbookValues, sheet: str, row: int, column: int,
                 required: bool) -> Any:
    if sheet not in reader.values.sheetnames:
        raise ExcelRuleError(f"缺少必填工作表：{sheet}")
    for merged in reader.values[sheet].merged_cells.ranges:
        if merged.min_row <= row <= merged.max_row and merged.min_col <= column <= merged.max_col:
            return reader.read(sheet, merged.min_row, merged.min_col, required)
    return reader.read(sheet, row, column, required)


def _repeat_count(reader: WorkbookValues, config: dict[str, Any]) -> int:
    source = config.get("repeatCountSource")
    count = int(_cell(reader, source)) if isinstance(source, dict) else int(config.get("repeatCount", 1))
    maximum = int(config.get("maxRepeat", 100))
    if count < 0 or count > maximum:
        raise ExcelRuleError(f"循环次数 {count} 超出 0-{maximum} 范围")
    return count


def _repeat_values(reader: WorkbookValues, config: dict[str, Any]) -> list[Any]:
    regions = config.get("regions")
    if regions is not None:
        if not isinstance(regions, list) or not regions:
            raise ExcelRuleError("多区域 Excel 规则必须至少配置一个区域")
        count = _repeat_count(reader, config)
        values: list[Any] = []
        for repeat_index in range(count):
            for region in regions:
                if not isinstance(region, dict):
                    raise ExcelRuleError("多区域 Excel 规则中的区域配置无效")
                if "repeatCount" in region or "repeatCountSource" in region or "regions" in region:
                    raise ExcelRuleError("多区域的重复次数只能在规则顶层配置")
                region_config = {**config, **region}
                region_config.pop("regions", None)
                values.extend(_repeat_values_for_indices(reader, region_config, [repeat_index]))
        return values

    return _repeat_values_for_indices(reader, config)


def _display_value(value: Any, config: dict[str, Any]) -> Any:
    if value in (None, "") or "displayDecimals" not in config:
        return value
    try:
        places = int(config["displayDecimals"])
        if places < 0 or places > 10:
            raise ValueError("精度超出范围")
        rounded = Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ExcelRuleError(f"Excel 数值格式配置或缓存无效：{value}") from error
    return f"{rounded:.{places}f}"


def _source_value(reader: WorkbookValues, config: dict[str, Any], source: dict[str, Any],
                  repeat_index: int) -> Any:
    if "literal" in source:
        if set(source) != {"literal"} or not isinstance(source["literal"], str) or not source["literal"]:
            raise ExcelRuleError("固定文字来源只能配置非空 literal，不得同时配置单元格")
        return source["literal"]
    sheet_source = source.get("sheetSource")
    sheet = str(source.get("sheet") or "")
    if sheet_source is not None:
        if not isinstance(sheet_source, dict):
            raise ExcelRuleError("动态工作表来源必须是单元格地址")
        sheet = str(reader.read(
            str(sheet_source.get("sheet") or ""),
            int(sheet_source.get("row", 0)) + repeat_index * int(sheet_source.get("rowStep", 0)),
            int(sheet_source.get("column", 0)), True,
        ) or "")
    return reader.read(sheet, int(source.get("row", 0)) + repeat_index * int(source.get("rowStep", 0)),
                       int(source.get("column", 0)) + repeat_index * int(source.get("columnStep", 0)),
                       bool(config.get("required")))


def _repeat_values_for_indices(reader: WorkbookValues, config: dict[str, Any],
                               repeat_indices: list[int] | None = None) -> list[Any]:
    count = _repeat_count(reader, config)
    row_start, row_end = int(config.get("rowStart", 1)), int(config.get("rowEnd", 1))
    if "rowStartOffsetFromRepeatCount" in config:
        row_start = count + int(config["rowStartOffsetFromRepeatCount"])
        row_end = row_start + int(config.get("rowCount", 1)) - 1
    if row_end < row_start or row_end - row_start > 1000:
        raise ExcelRuleError("Excel 数据行范围无效")
    values: list[Any] = []
    for repeat_index in repeat_indices if repeat_indices is not None else range(count):
        mode = str(config.get("valueMode") or "CELL")
        if mode.startswith("LINEAR_"):
            raise ExcelRuleError("线性汇总字段必须直接读取 Excel 单元格，不能使用回归计算模式")
        if mode == "HORIZONTAL_CELL":
            row = row_start + repeat_index * int(config.get("rowStep", 0))
            start = int(config.get("startColumn", 1))
            count = _horizontal_count(reader, config, row, start)
            values.extend(_display_value(_read_value(reader, config, str(config.get("sheet") or ""), row,
                                               start + offset), config)
                          for offset in range(count))
            continue
        for row_index, row in enumerate(range(row_start, row_end + 1)):
            if mode == "INDEX":
                value = row_index + int(config.get("indexBase", 1))
            elif mode == "REPEAT_VALUE":
                source = config.get("repeatValueSource") or {}
                value = _source_value(reader, config, source, repeat_index)
            elif mode == "JOIN_CELLS":
                sources = config.get("valueSources")
                if not isinstance(sources, list) or not sources or any(not isinstance(item, dict) for item in sources):
                    raise ExcelRuleError("拼接单元格规则必须配置非空的 valueSources")
                parts = [_source_value(reader, config, item, repeat_index) for item in sources]
                if any(part in (None, "") for part in parts):
                    raise ExcelRuleError("拼接单元格来源缺少必填值")
                value = str(config.get("joinSeparator", "")).join(str(part) for part in parts)
            elif mode == "CELL_PAIR":
                columns = config.get("pairColumns") or []
                if len(columns) != 2:
                    raise ExcelRuleError("双单元格 Excel 规则必须配置两个 pairColumns")
                source_row = row + repeat_index * int(config.get("rowStep", 0))
                pair = [_display_value(_read_value(reader, config, str(config.get("sheet") or ""),
                                                   source_row, int(column)), config) for column in columns]
                if all(item not in (None, "") for item in pair):
                    separator = str(config.get("pairSeparator") or "，")
                    # 兼容已保存的旧默认配置，统一输出中文逗号区间。
                    if separator == "～":
                        separator = "，"
                    value = f"（{separator.join(str(item) for item in pair)}）"
                else:
                    value = None
            else:
                sheet = str(config.get("sheet") or "")
                source_row = row + repeat_index * int(config.get("rowStep", 0)) + int(config.get("rowOffset", 0))
                column = (int(config.get("startColumn", 1)) + repeat_index * int(config.get("columnStep", 0))
                          + int(config.get("columnOffset", 0)))
                if mode == "MERGED_CELL":
                    value = _merged_cell(reader, sheet, source_row, column,
                                         bool(config.get("required")))
                else:
                    value = _read_value(reader, config, sheet, source_row, column)
            if mode not in ("CELL_PAIR", "JOIN_CELLS"):
                value = _display_value(value, config)
            repeat_value = int(config.get("broadcastRepeat", 1))
            if repeat_value < 1 or repeat_value > 1000:
                raise ExcelRuleError("重复值展开次数无效")
            values.extend([value] * repeat_value)
    return values


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


def _seed_collection_path(payload: dict[str, Any], item_path: str, count: int) -> None:
    parts = [part for part in item_path.removeprefix("$").lstrip(".").split(".") if part]
    if not parts:
        raise PayloadPathError("编组集合路径不能为空")
    owner = payload
    for part in parts[:-1]:
        child = owner.get(part)
        if child is None:
            child = {}
            owner[part] = child
        if not isinstance(child, dict):
            raise PayloadPathError(f"编组集合路径冲突：{item_path}")
        owner = child
    key = parts[-1]
    existing = owner.get(key)
    if existing is None:
        owner[key] = [{} for _ in range(count)]
    elif not isinstance(existing, list) or len(existing) != count:
        raise PayloadPathError(f"编组 {item_path} 的外层记录数与 Excel 重复次数不一致")


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
        item_path = f"$.{group_code}"
        sizes[item_path] = max(sizes.get(item_path, 0), count)
    for item_path, count in sizes.items():
        if count < 1:
            continue
        _seed_collection_path(payload, item_path, count)


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
                    value = extract_residual_chart_values(
                        path,
                        int(config.get("pointsPerTest", 5)),
                        int(config.get("chartStartIndex", 0)),
                        int(config.get("chartStep", 2)),
                    )
                elif config.get("mode") == "LINEAR_REGRESSION_CHART":
                    value = extract_regression_chart_values(
                        path,
                        int(config.get("pointsPerTest", 1)),
                        int(config.get("chartStartIndex", 0)),
                        int(config.get("chartStep", 2)),
                    )
                else:
                    value = _cell(reader, config) if config.get("mode") == "FIXED_CELL" else _repeat_values(reader, config)
            except (ExcelRuleError, ExcelChartError, KeyError, TypeError, ValueError) as error:
                if config.get("required"):
                    raise ExcelRuleError(f"字段 {field_code} 提取失败：{error}") from error
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
        payload_key = str(group.get("groupCode") or "").strip()
        item_path = f"$.{payload_key}" if payload_key else ""
        mappings = group.get("sourceMappings") or []
        if not item_path or str(group.get("cardinality") or "ONE").upper() != "MANY":
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
                for row_number, row in enumerate(rows[1:], start=2):
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
                        target[raw_parts[-1].replace("[*]", "")] = (
                            reader.read(sheet_name, row_number, index + 1)
                            if index < len(row) else None
                        )
                    records.append(record)
                if records:
                    existing = payload.get(payload_key)
                    if existing is not None and not isinstance(existing, list):
                        raise ExcelRuleError(f"编组 {group.get('groupCode')} 的数据列表冲突：{payload_key}")
                    payload[payload_key] = (existing or []) + records
