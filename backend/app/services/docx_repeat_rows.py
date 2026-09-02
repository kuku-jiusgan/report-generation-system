"""循环表格与矩阵表格的行填充。

这里的每一条规则都来自模板设计器：数据集合取内容块的"循环数据集合"，
行重复还是矩阵取表格规则的填充方式，保留哪些汇总行取表格规则的"保留行标签"，
矩阵版式取表格规则的"矩阵版式"。本模块不再保留任何内置的表号特例；
配置缺失或互相矛盾时记录可见警告并保留 Word 中的原有内容，不做猜测填充。
"""

import copy
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from lxml import etree

from .docx_field_values import (
    format_value, is_formula_calculation, mapping_source_path, payload_for_mapping,
    record_value, repeat_source, row_calculated_values, set_control_text, tag_of,
)
from .docx_matrix import fill_matrix_table, fill_matrix_tables
from .table_layout_rules import TableLayoutRules


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"

Warn = Callable[[str, str, str], None]


def _record_sort_key(value: Any) -> tuple[int, Decimal, str]:
    text = str(value or "").replace(",", "").strip()
    try:
        return (0, Decimal(text), "")
    except InvalidOperation:
        return (1, Decimal(0), text)


def _prepare_repeat_records(records: list[dict[str, Any]], group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = list(records)
    dedup_key = next((str(item.get("blockDedupKey") or "") for item in group if item.get("blockDedupKey")), "")
    if dedup_key:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for record in prepared:
            identity = repr(record_value(record, dedup_key))
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(record)
        prepared = unique
    sort_rule = next((str(item.get("blockSortRule") or "") for item in group if item.get("blockSortRule")), "")
    rules: list[tuple[str, bool]] = []
    for expression in sort_rule.split(","):
        parts = expression.strip().split()
        if parts:
            rules.append((parts[0], len(parts) > 1 and parts[1].upper() == "DESC"))
    for field, reverse in reversed(rules):
        # 数值按数值比较（10 > 2），非数值按文本比较；数值整体排在文本之前
        prepared.sort(key=lambda item: _record_sort_key(record_value(item, field)), reverse=reverse)
    return prepared


def _set_vertical_merge(cell: etree._Element, restart: bool) -> None:
    properties = cell.find(W + "tcPr")
    if properties is None:
        properties = etree.Element(W + "tcPr")
        cell.insert(0, properties)
    for existing in properties.findall(W + "vMerge"):
        properties.remove(existing)
    merge = etree.SubElement(properties, W + "vMerge")
    if restart:
        merge.set(W + "val", "restart")


def _cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS)).strip()


def _set_cell_text(cell: etree._Element, value: Any) -> None:
    texts = cell.xpath(".//w:t", namespaces=NS)
    if not texts:
        paragraph = cell.find(W + "p")
        if paragraph is None:
            paragraph = etree.SubElement(cell, W + "p")
        run = etree.SubElement(paragraph, W + "r")
        texts = [etree.SubElement(run, W + "t")]
    texts[0].text = "" if value is None else str(value)
    for text in texts[1:]:
        text.text = ""


def _is_preserved_summary_row(row: etree._Element, preserved_labels: tuple[str, ...]) -> bool:
    cells = row.xpath("./w:tc", namespaces=NS)
    label = _cell_text(cells[0]) if cells else ""
    return any(label.startswith(prefix) for prefix in preserved_labels)


def _clear_unmapped_summary_cells(row: etree._Element, direct_tags: set[str]) -> None:
    cells = row.xpath("./w:tc", namespaces=NS)
    for cell in cells[1:]:
        cell_tags = set(cell.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
        if not cell_tags.intersection(direct_tags):
            _set_cell_text(cell, "")


def _group_source(table_no: str, group: list[dict[str, Any]], report_data: dict[str, Any],
                  warn: Warn) -> tuple[str, str] | None:
    """循环表的数据集合以内容块配置为准，字段路径只作为未配置时的回退。"""
    block_source = next((repeat_source(item.get("blockSourcePath", "")) for item in group
                         if repeat_source(item.get("blockSourcePath", ""))), None)
    field_source = next((repeat_source(mapping_source_path(item, report_data)) for item in group
                         if repeat_source(mapping_source_path(item, report_data))), None)
    if block_source and field_source and block_source[0] != field_source[0]:
        warn("BLOCK_SOURCE_MISMATCH", table_no,
             f"内容块的循环数据集合是 {block_source[0]}，字段却取自 {field_source[0]}，"
             f"按内容块配置填充；请在模板设计器中对齐两者。")
    if not block_source and field_source:
        warn("BLOCK_SOURCE_MISSING", table_no,
             f"内容块没有配置循环数据集合，暂按字段路径的 {field_source[0]} 填充；"
             f"请在模板设计器中补填。")
    return block_source or field_source


def _is_matrix(table_no: str, group: list[dict[str, Any]], layout: TableLayoutRules, warn: Warn) -> bool:
    rule_matrix = layout.is_matrix(table_no)
    block_matrix = any(str(item.get("contentBlockKind") or "") == "MATRIX" for item in group)
    if rule_matrix != block_matrix:
        warn("MATRIX_MODE_MISMATCH", table_no,
             f"表格规则的填充方式是{'矩阵' if rule_matrix else '按行重复'}，"
             f"内容块类型却是{'矩阵' if block_matrix else '循环表格'}；两者都按矩阵处理，请在模板设计器中统一。")
    return rule_matrix or block_matrix


def _fill_matrix_block(document: etree._Element, table_no: str, records: list[dict[str, Any]],
                       empty_behavior: str, layout: TableLayoutRules, warn: Warn,
                       mappings: list[dict[str, Any]]) -> None:
    if not records and empty_behavior == "HIDE":
        bookmark = document.xpath(
            f".//w:bookmarkStart[@w:name='repeat_{table_no.lower()}_row']", namespaces=NS
        )
        if bookmark:
            table = bookmark[0].getparent().getparent()
            table.getparent().remove(table)
        return
    matrix_layout = layout.matrix_layout(table_no)
    if not matrix_layout:
        warn("MATRIX_LAYOUT_MISSING", table_no,
             "该表按矩阵填充，但表格规则里没有可用的矩阵版式；已保留 Word 模板中的原有内容，"
             "请在模板设计器的表格布局中补充矩阵版式。")
        return
    fill_matrix_tables(document, table_no, records, matrix_layout,
                       layout.anchored_index(document, table_no, mappings))


def _reset_prototype_row(prototype: etree._Element, group_tags: set[str]) -> None:
    # 单元格里控件之外的文字属于模板固定内容（例如单位后缀），只清空整格都没有
    # 映射控件的单元格；早期版本连这些前后缀一起抹掉了。
    for cell in prototype.xpath("./w:tc", namespaces=NS):
        cell_tags = set(cell.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
        if cell_tags & group_tags:
            continue
        for text in cell.xpath(".//w:t", namespaces=NS):
            text.text = ""


def _drop_stale_rows(parent: etree._Element, insert_at: int, direct_tags: set[str],
                     preserved_labels: tuple[str, ...]) -> None:
    for old_row in list(parent)[insert_at + 1:]:
        if old_row.tag != W + "tr":
            continue
        row_tags = set(old_row.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
        if row_tags & direct_tags:
            continue
        if _is_preserved_summary_row(old_row, preserved_labels):
            _clear_unmapped_summary_cells(old_row, direct_tags)
            continue
        parent.remove(old_row)


def _clone_rows(prototype: etree._Element, parent: etree._Element, insert_at: int,
                records: list[dict[str, Any]]) -> list[etree._Element]:
    if not records:
        for control in prototype.xpath(".//w:sdt", namespaces=NS):
            set_control_text(control, "")
        return []
    rows = [prototype]
    for offset in range(1, len(records)):
        cloned = copy.deepcopy(prototype)
        for bookmark in cloned.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
            bookmark.getparent().remove(bookmark)
        parent.insert(insert_at + offset, cloned)
        rows.append(cloned)
    return rows


def _write_row_values(rows: list[etree._Element], records: list[dict[str, Any]], table_no: str,
                      group: list[dict[str, Any]], source: tuple[str, str], report_data: dict[str, Any],
                      values: dict[str, Any], warn: Warn) -> None:
    for row, record in zip(rows, records):
        controls = {tag_of(control): control for control in row.xpath(".//w:sdt", namespaces=NS)}
        row_values = row_calculated_values(group, record, values, report_data)
        for mapping in group:
            control = controls.get(mapping.get("controlTag", ""))
            if control is None:
                continue
            if is_formula_calculation(mapping):
                set_control_text(control, format_value(row_values.get(str(mapping.get("fieldCode"))), mapping))
                continue
            repeat_path = repeat_source(mapping_source_path(mapping, report_data))
            if not repeat_path:
                continue
            if repeat_path[0] != source[0]:
                warn("FIELD_SOURCE_MISMATCH", table_no,
                     f"字段“{mapping.get('wordLabel') or mapping.get('fieldCode')}”取自 {repeat_path[0]}，"
                     f"与本表的数据集合 {source[0]} 不一致，已跳过填充。")
                continue
            set_control_text(control, format_value(record_value(record, repeat_path[1]), mapping))


def _apply_vertical_merge(rows: list[etree._Element], records: list[dict[str, Any]],
                          group: list[dict[str, Any]], report_data: dict[str, Any]) -> None:
    block_merge = next((item.get("blockMergeRule") for item in group if item.get("blockMergeRule")), "NONE")
    for mapping in group:
        if block_merge != "VERTICAL_BY_VALUE" and mapping.get("mergeRule") != "VERTICAL_BY_VALUE":
            continue
        tag = mapping.get("controlTag", "")
        previous: Any = object()
        previous_cell: etree._Element | None = None
        for row, record in zip(rows, records):
            repeat_path = repeat_source(mapping_source_path(mapping, report_data))
            value = record_value(record, repeat_path[1]) if repeat_path else None
            controls = {tag_of(control): control for control in row.xpath(".//w:sdt", namespaces=NS)}
            control = controls.get(tag)
            cell = control.xpath("ancestor::w:tc[1]", namespaces=NS)[0] if control is not None else None
            if cell is not None and value not in (None, "") and value == previous and previous_cell is not None:
                _set_vertical_merge(previous_cell, True)
                _set_vertical_merge(cell, False)
                set_control_text(control, "")
            else:
                previous_cell = cell
            previous = value


def _group_mappings(mappings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for mapping in mappings:
        if mapping.get("enabled", True) and mapping.get("repeatType") == "ROW" and mapping.get("tableNo"):
            groups.setdefault(mapping["tableNo"], []).append(mapping)
    return groups


def _fill_row_repeat_table(document: etree._Element, table_no: str, group: list[dict[str, Any]],
                           mappings: list[dict[str, Any]], records: list[dict[str, Any]],
                           source: tuple[str, str], empty_behavior: str, report_data: dict[str, Any],
                           values: dict[str, Any], layout: TableLayoutRules, warn: Warn) -> None:
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='repeat_{table_no.lower()}_row']", namespaces=NS
    )
    if not bookmarks:
        warn("PROTOTYPE_ROW_MISSING", table_no,
             "Word 模板里找不到该表的原型行书签，已保留原有内容；请在模板设计器中重新绑定字段位置。")
        return
    prototype = bookmarks[0].getparent()
    parent = prototype.getparent()
    insert_at = parent.index(prototype)
    _reset_prototype_row(prototype, {item.get("controlTag", "") for item in group})
    direct_tags = {item.get("controlTag", "") for item in mappings
                   if item.get("controlTag") and item.get("repeatType") != "ROW"}
    _drop_stale_rows(parent, insert_at, direct_tags, layout.preserved_row_labels(table_no))
    if not records and empty_behavior == "HIDE":
        parent.remove(prototype)
        return
    rows = _clone_rows(prototype, parent, insert_at, records)
    _write_row_values(rows, records, table_no, group, source, report_data, values, warn)
    if len(rows) > 1:
        _apply_vertical_merge(rows, records, group, report_data)


def _group_records(records: list[dict[str, Any]], group_key: str) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        value = record_value(record, group_key)
        if value in (None, ""):
            raise ValueError(f"整表分组字段 {group_key} 缺失")
        grouped.setdefault(str(value), []).append(record)
    return list(grouped.values())


def _fill_table_repeat(document: etree._Element, table_no: str, group: list[dict[str, Any]],
                       mappings: list[dict[str, Any]], records: list[dict[str, Any]],
                       source: tuple[str, str], empty_behavior: str, report_data: dict[str, Any],
                       values: dict[str, Any], layout: TableLayoutRules, warn: Warn) -> None:
    rule = layout.rule(table_no)
    group_key = str(rule.get("groupKey") or "").strip()
    if not group_key:
        warn("TABLE_REPEAT_GROUP_KEY_MISSING", table_no, "按分组复制整表时必须配置分组字段。")
        return
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='repeat_{table_no.lower()}_row']", namespaces=NS
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
    parent, insert_at = prototype.getparent(), prototype.getparent().index(prototype)
    tables = [prototype]
    for offset in range(1, len(record_groups)):
        cloned = copy.deepcopy(prototype)
        parent.insert(insert_at + offset, cloned)
        tables.append(cloned)
    inner_mode = str(rule.get("innerMode") or "ROW_REPEAT")
    matrix_layout = layout.matrix_layout(table_no)
    for table, grouped_records in zip(tables, record_groups):
        if inner_mode == "MATRIX":
            if not matrix_layout:
                warn("MATRIX_LAYOUT_MISSING", table_no, "整表复制的表内模式为矩阵，但未配置矩阵版式。")
                return
            fill_matrix_table(table, grouped_records, matrix_layout)
            continue
        _fill_row_repeat_table(table, table_no, group, mappings, grouped_records, source,
                               empty_behavior, report_data, values, layout, warn)


def fill_repeat_rows(document: etree._Element, mappings: list[dict[str, Any]], payload: dict[str, Any],
                     report_data: dict[str, Any], values: dict[str, Any],
                     layout: TableLayoutRules, warn: Warn) -> None:
    for table_no, group in _group_mappings(mappings).items():
        source = _group_source(table_no, group, report_data, warn)
        if not source:
            warn("BLOCK_SOURCE_MISSING", table_no,
                 "内容块和字段都没有配置循环数据集合，已保留 Word 模板中的原有内容。")
            continue
        source_mapping = next((item for item in group
                               if repeat_source(mapping_source_path(item, report_data))), group[0])
        source_payload = payload_for_mapping(source_mapping, payload, report_data)
        records = source_payload.get(source[0])
        records = _prepare_repeat_records(records if isinstance(records, list) else [], group)
        empty_behavior = next((item.get("blockEmptyBehavior") for item in group
                               if item.get("blockEmptyBehavior")), "KEEP")
        if layout.is_table_repeat(table_no):
            _fill_table_repeat(document, table_no, group, mappings, records, source,
                               empty_behavior, report_data, values, layout, warn)
            continue
        if _is_matrix(table_no, group, layout, warn):
            _fill_matrix_block(document, table_no, records, empty_behavior, layout, warn, group)
            continue
        _fill_row_repeat_table(document, table_no, group, mappings, records, source,
                               empty_behavior, report_data, values, layout, warn)
