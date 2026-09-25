"""按分组复制整张 Word 表，并调度表内行重复或矩阵填充。"""

import copy
from typing import Any, Callable

from lxml import etree

from .docx_field_values import (
    format_value, mapping_source_path, record_value, repeat_source, set_control_text, tag_of,
)
from .docx_matrix import fill_matrix_table, with_image_control_tags
from .docx_rich_blocks import set_mapped_control
from .docx_segment_table import (
    apply_segment_vertical_merges, fill_segment_heading, fill_segment_table,
)
from .table_layout_rules import TableLayoutRules, repeat_bookmark_name


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
Warn = Callable[[str, str, str], None]
RowRepeat = Callable[..., None]


def _group_records(records: list[dict[str, Any]], group_key: str) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        value = record_value(record, group_key)
        if value in (None, ""):
            raise ValueError(f"整表分组字段 {group_key} 缺失")
        grouped.setdefault(str(value), []).append(record)
    return list(grouped.values())


def _adjacent_group_heading(prototype: etree._Element, group: list[dict[str, Any]],
                            source: tuple[str, str], group_key: str,
                            ) -> tuple[etree._Element, dict[str, Any]] | None:
    mapping = next((item for item in group
                    if repeat_source(mapping_source_path(item)) == (source[0], group_key)
                    and item.get("controlTag")), None)
    heading = prototype.getprevious()
    if mapping is None or heading is None:
        return None
    controls = heading.xpath(
        "self::w:sdt[w:sdtPr/w:tag/@w:val=$tag] | .//w:sdt[w:sdtPr/w:tag/@w:val=$tag]",
        namespaces=NS, tag=str(mapping["controlTag"]),
    )
    return (heading, mapping) if controls else None


def _fill_group_heading(heading: etree._Element, mapping: dict[str, Any],
                        record: dict[str, Any], group_key: str) -> None:
    value = format_value(record_value(record, group_key), mapping)
    for control in heading.xpath(
        "self::w:sdt[w:sdtPr/w:tag/@w:val=$tag] | .//w:sdt[w:sdtPr/w:tag/@w:val=$tag]",
        namespaces=NS, tag=str(mapping["controlTag"]),
    ):
        set_control_text(control, value, image=mapping.get("dataType") == "image")


def _clone_repeat_blocks(prototype: etree._Element, heading: etree._Element | None,
                         group_count: int,
                         ) -> tuple[list[etree._Element], list[etree._Element]]:
    parent = prototype.getparent()
    insert_at = parent.index(prototype) + 1
    tables = [prototype]
    headings = [heading] if heading is not None else []
    for _ in range(1, group_count):
        parent.insert(insert_at, etree.Element(f"{{{W_NS}}}p"))
        insert_at += 1
        if heading is not None:
            cloned_heading = copy.deepcopy(heading)
            parent.insert(insert_at, cloned_heading)
            headings.append(cloned_heading)
            insert_at += 1
        cloned_table = copy.deepcopy(prototype)
        parent.insert(insert_at, cloned_table)
        tables.append(cloned_table)
        insert_at += 1
    return tables, headings


def _relative_path(mapping: dict[str, Any], source: tuple[str, str]) -> str:
    parsed = repeat_source(mapping_source_path(mapping))
    return parsed[1] if parsed and parsed[0] == source[0] else ""


def _control_rows(table: etree._Element, tag: str) -> list[tuple[int, int]]:
    """Return (row, cell) positions for a content-control tag in a table."""
    positions: list[tuple[int, int]] = []
    for row_index, row in enumerate(table.xpath("./w:tr", namespaces=NS), start=1):
        cells = row.xpath("./w:tc", namespaces=NS)
        for cell_index, cell in enumerate(cells, start=1):
            if cell.xpath(".//w:sdt[w:sdtPr/w:tag/@w:val=$tag]", namespaces=NS, tag=tag):
                positions.append((row_index, cell_index))
    return positions


def _inferred_segment_layout(table: etree._Element, group: list[dict[str, Any]],
                             source: tuple[str, str]) -> dict[str, Any] | None:
    """Infer multiple row-repeat regions from bindings that contain distinct detail arrays."""
    segments: dict[tuple[int, str, str], dict[str, Any]] = {}
    summaries: dict[tuple[int, str], dict[str, Any]] = {}
    detail_roots: set[tuple[str, str]] = set()
    for mapping in group:
        path = _relative_path(mapping, source)
        tag = str(mapping.get("controlTag") or "")
        if not path or not tag:
            continue
        positions = _control_rows(table, tag)
        if not positions:
            continue
        if "[*]." in path:
            before, field = path.split("[*].", 1)
            if "." not in before:
                continue
            source_path, detail_path = before.rsplit(".", 1)
            detail_roots.add((source_path, detail_path))
            for row, cell in positions:
                key = (row, source_path, detail_path)
                segment = segments.setdefault(key, {
                    "row": row, "sourcePath": source_path, "detailPath": detail_path,
                    "detailCells": {},
                })
                segment["detailCells"][str(cell - 1)] = field
            continue
        if "." in path:
            source_path, field = path.rsplit(".", 1)
        else:
            source_path, field = "", path
        for row, cell in positions:
            key = (row, source_path)
            summary = summaries.setdefault(key, {"row": row, "sourcePath": source_path,
                                                  "cells": {}, "rootCells": {}})
            target = summary["cells"] if source_path else summary["rootCells"]
            target[str(cell - 1)] = field
    if len(detail_roots) < 2:
        return None
    segment_list = list(segments.values())
    if len({item["row"] for item in segment_list}) != len(segment_list):
        return None
    segment_paths = {item["sourcePath"] for item in segment_list}
    summary_list: list[dict[str, Any]] = []
    for summary in summaries.values():
        if summary["row"] in {item["row"] for item in segment_list}:
            continue
        if summary["sourcePath"] and summary["sourcePath"] not in segment_paths:
            continue
        if not summary["sourcePath"]:
            summary["sourcePath"] = next(iter(segment_paths))
        summary = {key: value for key, value in summary.items() if value}
        summary_list.append(summary)
    return {"segments": sorted(segment_list, key=lambda item: item["row"]),
            "summaryRows": sorted(summary_list, key=lambda item: item["row"])}


def _bound_matrix_layout(table: etree._Element, configured: dict[str, Any],
                         group: list[dict[str, Any]], source: tuple[str, str],
                         warn: Warn, table_no: str) -> tuple[dict[str, Any], str, bool]:
    """用 Word 行内控件绑定校正矩阵字段，并确定唯一的明细数组层。"""
    result = with_image_control_tags(configured, group)
    mappings = {str(item["controlTag"]): item for item in group if item.get("controlTag")}
    rows = table.xpath("./w:tr", namespaces=NS)
    configured_entries = [item for item in result.get("rowFields") or []
                          if isinstance(item, dict)]
    detail_keys = {
        str(item.get("field") or "").split("[*].", 1)[0]
        for item in configured_entries if "[*]." in str(item.get("field") or "")
    }
    if not detail_keys:
        configured_rows = {int(item.get("row", 0) or 0) for item in configured_entries}
        for row_number, row in enumerate(rows, start=1):
            if row_number not in configured_rows:
                continue
            for tag in row.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS):
                mapping = mappings.get(str(tag))
                path = _relative_path(mapping, source) if mapping else ""
                if "[*]." in path:
                    detail_keys.add(path.split("[*].", 1)[0])
    if len(detail_keys) > 1:
        warn("MATRIX_DETAIL_LEVEL_CONFLICT", table_no,
             f"矩阵逐列字段分布在多个明细层（{'、'.join(sorted(detail_keys))}），已保留 Word 原有内容。")
        return result, "", False
    detail_key = next(iter(detail_keys), "")
    if detail_key:
        entries: dict[int, dict[str, Any]] = {}
        for item in configured_entries:
            row_number = int(item.get("row", 0) or 0)
            field = str(item.get("field") or "")
            if "[*]." in field:
                key, field = field.split("[*].", 1)
                if key != detail_key:
                    continue
            entries[row_number] = {**item, "field": field}
        prefix = detail_key + "[*]."
        for row_number, row in enumerate(rows, start=1):
            bound = [mappings.get(str(tag)) for tag in row.xpath(
                ".//w:sdtPr/w:tag/@w:val", namespaces=NS,
            )]
            paths = [_relative_path(item, source) for item in bound if item]
            detail_paths = [path for path in paths if path.startswith(prefix)]
            if len(detail_paths) > 1:
                warn("MATRIX_ROW_BINDING_CONFLICT", table_no,
                     f"矩阵第 {row_number} 行绑定了多个逐列字段，已保留 Word 原有内容。")
                return result, "", False
            if not detail_paths:
                if paths:
                    entries.pop(row_number, None)
                continue
            entry = entries.setdefault(row_number, {"row": row_number})
            entry["field"] = detail_paths[0][len(prefix):]
        result["rowFields"] = [entries[key] for key in sorted(entries)]
    return result, detail_key, True


def _matrix_records(grouped_records: list[dict[str, Any]], detail_key: str,
                    table_no: str, warn: Warn) -> list[dict[str, Any]] | None:
    if not detail_key:
        return grouped_records
    details: list[dict[str, Any]] = []
    for record in grouped_records:
        nested = record_value(record, detail_key)
        if not isinstance(nested, list):
            warn("MATRIX_DETAIL_LEVEL_MISSING", table_no,
                 f"矩阵明细层 {detail_key} 缺失或不是数组，已保留 Word 原有内容。")
            return None
        details.extend(item for item in nested if isinstance(item, dict))
    return details


def _fill_bound_scalars(table: etree._Element, grouped_records: list[dict[str, Any]],
                        detail_key: str, group: list[dict[str, Any]],
                        source: tuple[str, str], table_no: str, warn: Warn) -> None:
    """固定行按控件绑定取值；单值数组允许一项，多项则视为配置冲突。"""
    if not grouped_records:
        return
    controls: dict[str, list[etree._Element]] = {}
    for control in table.xpath(".//w:sdt", namespaces=NS):
        controls.setdefault(tag_of(control), []).append(control)
    for mapping in group:
        path = _relative_path(mapping, source)
        tag = str(mapping.get("controlTag") or "")
        if not path or not tag or tag not in controls:
            continue
        if detail_key and (path == detail_key or path.startswith(detail_key + "[*].")):
            continue
        resolved: list[Any] = []
        for record in grouped_records:
            value = record_value(record, path)
            if isinstance(value, list):
                if len(value) != 1:
                    if value:
                        warn("MATRIX_SCALAR_NOT_UNIQUE", table_no,
                             f"固定字段“{mapping.get('wordLabel') or mapping.get('fieldCode')}”取得 {len(value)} 个值，"
                             "无法确定应写入哪一个。")
                    resolved = []
                    break
                value = value[0]
            if not isinstance(value, dict):
                resolved.append(value)
        if not resolved:
            continue
        unique = {repr(value) for value in resolved}
        if len(unique) > 1:
            warn("MATRIX_SCALAR_NOT_UNIQUE", table_no,
                 f"固定字段“{mapping.get('wordLabel') or mapping.get('fieldCode')}”在同一分组中取得多个不同值，"
                 "无法确定应写入哪一个。")
            continue
        for control in controls[tag]:
            set_mapped_control(control, resolved[0], mapping)


def _fill_matrix(table: etree._Element, grouped_records: list[dict[str, Any]],
                 matrix_layout: dict[str, Any], group: list[dict[str, Any]],
                 source: tuple[str, str], table_no: str, warn: Warn) -> bool:
    resolved, detail_key, valid = _bound_matrix_layout(
        table, matrix_layout, group, source, warn, table_no,
    )
    if not valid:
        return False
    if not resolved.get("rowFields"):
        warn("MATRIX_ROW_FIELDS_MISSING", table_no, "矩阵没有配置逐列数据行，已保留 Word 原有内容。")
        return False
    records = _matrix_records(grouped_records, detail_key, table_no, warn)
    if records is None:
        return False
    fill_matrix_table(table, records, resolved)
    _fill_bound_scalars(table, grouped_records, detail_key, group, source, table_no, warn)
    return True


def fill_table_repeat(document: etree._Element, table_no: str, group: list[dict[str, Any]],
                      mappings: list[dict[str, Any]], records: list[dict[str, Any]],
                      source: tuple[str, str], empty_behavior: str, report_data: dict[str, Any],
                      values: dict[str, Any], layout: TableLayoutRules, warn: Warn,
                      fill_row_repeat: RowRepeat) -> None:
    rule = layout.rule(table_no)
    group_key = str(rule.get("groupKey") or "").strip()
    if not group_key:
        warn("TABLE_REPEAT_GROUP_KEY_MISSING", table_no, "按分组复制整表时必须配置分组字段。")
        return
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='{repeat_bookmark_name(table_no)}']", namespaces=NS,
    )
    if not bookmarks:
        warn("PROTOTYPE_TABLE_MISSING", table_no, "Word 模板里找不到整表复制的原型表。")
        return
    table_nodes = bookmarks[0].xpath("ancestor::w:tbl[1]", namespaces=NS)
    if not table_nodes:
        warn("PROTOTYPE_TABLE_MISSING", table_no, "整表复制书签不在 Word 表格内。")
        return
    try:
        record_groups = _group_records(records, group_key)
    except ValueError as error:
        warn("TABLE_REPEAT_GROUP_KEY_MISSING", table_no, str(error))
        return
    prototype = table_nodes[0]
    heading_config = _adjacent_group_heading(prototype, group, source, group_key)
    inner_mode = str(rule.get("innerMode") or "ROW_REPEAT")
    matrix_layout = layout.matrix_layout(table_no)
    if inner_mode == "SEGMENT_REPEAT":
        if not matrix_layout:
            raise ValueError(f"{table_no} 缺少行片段表格配置")
        heading = prototype.getprevious() if matrix_layout.get("headingField") else None
        if matrix_layout.get("headingField") and (heading is None or heading.tag not in
                                                   (f"{{{W_NS}}}p", f"{{{W_NS}}}sdt")):
            raise ValueError(f"{table_no} 原型表前缺少可填写的标题段落")
        tables, headings = _clone_repeat_blocks(prototype, heading, len(record_groups))
        for index, (table, grouped_records) in enumerate(zip(tables, record_groups)):
            if len(grouped_records) != 1:
                raise ValueError(f"{table_no} 整表分组键 {group_key} 未唯一标识记录")
            for unavailable in matrix_layout.get("unavailableFields") or []:
                if record_value(grouped_records[0], str(unavailable["field"])) in (None, ""):
                    warn("SEGMENT_FIELD_UNAVAILABLE", table_no,
                         f"{record_value(grouped_records[0], group_key)}："
                         f"{unavailable.get('label') or unavailable['field']}缺少来源；"
                         f"{unavailable.get('source') or '请配置真实数据来源'}。")
            scalar_mappings = [item for item in group if "[*]" not in _relative_path(item, source)]
            heading_mapping = next(
                (item for item in scalar_mappings
                 if _relative_path(item, source) == str(matrix_layout.get("headingField") or "")),
                None,
            )
            if heading is not None:
                fill_segment_heading(
                    headings[index], grouped_records[0], matrix_layout, heading_mapping,
                )
            fill_segment_table(table, grouped_records[0], matrix_layout)
            _fill_bound_scalars(table, grouped_records, "", scalar_mappings, source, table_no, warn)
            apply_segment_vertical_merges(table, scalar_mappings)
        return
    tables, headings = _clone_repeat_blocks(
        prototype, heading_config[0] if heading_config else None, len(record_groups),
    )
    if heading_config:
        for heading, grouped_records in zip(headings, record_groups):
            _fill_group_heading(heading, heading_config[1], grouped_records[0], group_key)
    for table, grouped_records in zip(tables, record_groups):
        if inner_mode == "MATRIX":
            if not matrix_layout:
                warn("MATRIX_LAYOUT_MISSING", table_no, "整表复制的表内模式为矩阵，但未配置矩阵版式。")
                return
            if not _fill_matrix(table, grouped_records, matrix_layout, group, source, table_no, warn):
                return
            continue
        inferred_layout = _inferred_segment_layout(table, group, source)
        if inferred_layout:
            if len(grouped_records) != 1:
                raise ValueError(f"{table_no} 自动识别的多个按行区域要求每个整表分组只对应一条记录")
            fill_segment_table(table, grouped_records[0], inferred_layout)
            scalar_mappings = [item for item in group
                                if "[*]" not in _relative_path(item, source)]
            _fill_bound_scalars(table, grouped_records, "", scalar_mappings, source,
                                table_no, warn)
            apply_segment_vertical_merges(table, scalar_mappings)
            continue
        fill_row_repeat(table, table_no, group, mappings, grouped_records, source,
                        empty_behavior, report_data, values, layout, warn)
