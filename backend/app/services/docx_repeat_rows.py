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
    format_value, is_formula_calculation, mapping_source_path,
    record_value, repeat_source, row_calculated_values, set_control_text, tag_of,
)
from .docx_group_columns import expand_group_columns, fill_group_headers, find_group_span
from .docx_matrix import fill_matrix_tables, with_image_control_tags
from .docx_summary_rows import (
    clear_unmapped_summary_cells, fill_preserved_summary_rows, is_preserved_summary_row,
)
from .table_layout_rules import TableLayoutRules, repeat_bookmark_name
from .docx_table_repeat import fill_table_repeat


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


def _group_source(table_no: str, group: list[dict[str, Any]], warn: Warn) -> tuple[str, str] | None:
    """循环表的数据集合优先使用编组 itemPath，其次才是内容块显式路径。"""
    group_source = next((repeat_source(item.get("groupItemPath", "")) for item in group
                         if repeat_source(item.get("groupItemPath", ""))), None)
    block_source = next((repeat_source(item.get("blockSourcePath", "")) for item in group
                         if repeat_source(item.get("blockSourcePath", ""))), None)
    field_source = next((repeat_source(mapping_source_path(item)) for item in group
                         if repeat_source(mapping_source_path(item))), None)
    if group_source and block_source and group_source[0] != block_source[0]:
        warn("BLOCK_SOURCE_MISMATCH", table_no,
             f"内容块的循环数据集合是 {block_source[0]}，编组集合路径是 {group_source[0]}，请修正模板配置。")
    if group_source and field_source and group_source[0] != field_source[0]:
        warn("BLOCK_SOURCE_MISMATCH", table_no,
             f"编组集合路径是 {group_source[0]}，字段却取自 {field_source[0]}，已跳过不一致字段。")
    if not group_source and not block_source:
        warn("BLOCK_SOURCE_MISSING", table_no, "编组未配置循环数据集合 itemPath，无法确定循环来源。")
        return None
    return group_source or block_source


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
            f".//w:bookmarkStart[@w:name='{repeat_bookmark_name(table_no)}']", namespaces=NS
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
    fill_matrix_tables(document, table_no, records, with_image_control_tags(matrix_layout, mappings), warn,
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
        if is_preserved_summary_row(old_row, preserved_labels):
            clear_unmapped_summary_cells(old_row, direct_tags)
            continue
        parent.remove(old_row)


def _clone_rows(prototype: etree._Element, parent: etree._Element, insert_at: int,
                records: list[dict[str, Any]],
                empty_mappings: list[dict[str, Any]] | None = None) -> list[etree._Element]:
    if not records:
        empty_values = {
            str(mapping.get("controlTag")): format_value(None, mapping)
            for mapping in (empty_mappings or [])
            if mapping.get("controlTag")
        }
        for control in prototype.xpath(".//w:sdt", namespaces=NS):
            set_control_text(control, empty_values.get(tag_of(control), ""))
        return []
    rows = [prototype]
    for offset in range(1, len(records)):
        cloned = copy.deepcopy(prototype)
        for bookmark in cloned.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
            bookmark.getparent().remove(bookmark)
        parent.insert(insert_at + offset, cloned)
        rows.append(cloned)
    return rows


def _write_cell_values(cells: list[etree._Element], record: dict[str, Any], table_no: str,
                       group: list[dict[str, Any]], source: tuple[str, str],
                       report_data: dict[str, Any], values: dict[str, Any], warn: Warn) -> None:
    """把一条记录写进这些单元格里的控件；哪一格填哪个字段由控件绑定决定。"""
    controls: dict[str, etree._Element] = {}
    for cell in cells:
        for control in cell.xpath(".//w:sdt", namespaces=NS):
            controls[tag_of(control)] = control
    row_values = row_calculated_values(group, record, values, report_data)
    for mapping in group:
        control = controls.get(mapping.get("controlTag", ""))
        if control is None:
            continue
        if is_formula_calculation(mapping):
            set_control_text(control, format_value(row_values.get(str(mapping.get("fieldCode"))), mapping))
            continue
        repeat_path = repeat_source(mapping_source_path(mapping))
        if not repeat_path:
            continue
        if repeat_path[0] != source[0]:
            warn("FIELD_SOURCE_MISMATCH", table_no,
                 f"字段“{mapping.get('wordLabel') or mapping.get('fieldCode')}”取自 {repeat_path[0]}，"
                 f"与本表的数据集合 {source[0]} 不一致，已跳过填充。")
            continue
        set_control_text(control, format_value(record_value(record, repeat_path[1]), mapping))


def _write_row_values(rows: list[etree._Element], records: list[dict[str, Any]], table_no: str,
                      group: list[dict[str, Any]], source: tuple[str, str], report_data: dict[str, Any],
                      values: dict[str, Any], warn: Warn) -> None:
    for row, record in zip(rows, records):
        _write_cell_values(row.xpath("./w:tc", namespaces=NS), record, table_no, group, source,
                           report_data, values, warn)


def _apply_vertical_merge(rows: list[etree._Element],
                          units: list[tuple[dict[str, Any], dict[str, Any] | None]],
                          group: list[dict[str, Any]], report_data: dict[str, Any],
                          detail_key: str) -> None:
    block_merge = next((item.get("blockMergeRule") for item in group if item.get("blockMergeRule")), "NONE")
    for mapping in group:
        if block_merge != "VERTICAL_BY_VALUE" and mapping.get("mergeRule") != "VERTICAL_BY_VALUE":
            continue
        tag = mapping.get("controlTag", "")
        previous: Any = object()
        previous_cell: etree._Element | None = None
        for row, (group_record, detail_record) in zip(rows, units):
            repeat_path = repeat_source(mapping_source_path(mapping))
            value = _level_value(repeat_path, group_record, detail_record, detail_key) if repeat_path else None
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


def _prototype_row(document: etree._Element, table_no: str, mappings: list[dict[str, Any]],
                   layout: TableLayoutRules, warn: Warn) -> etree._Element | None:
    """原型数据行：配了"原型数据行位置"就按行号取，否则退回编译期埋下的书签。"""
    data_row = layout.data_row_start(table_no)
    table = document if document.tag == W + "tbl" else None
    if table is None:
        index = layout.anchored_index(document, table_no, mappings)
        tables = document.xpath(".//w:tbl", namespaces=NS)
        table = tables[index - 1] if index > 0 else None
    if data_row > 0 and table is not None:
        rows = table.xpath("./w:tr", namespaces=NS)
        if data_row > len(rows):
            warn("PROTOTYPE_ROW_MISSING", table_no,
                 f"表格布局里的原型数据行是第 {data_row} 行，但 Word 里这张表只有 {len(rows)} 行。")
            return None
        return rows[data_row - 1]
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='{repeat_bookmark_name(table_no)}']", namespaces=NS
    )
    if not bookmarks:
        warn("PROTOTYPE_ROW_MISSING", table_no,
             "Word 模板里找不到该表的原型行书签，已保留原有内容；请在模板设计器中重新绑定字段位置。")
        return None
    return bookmarks[0].getparent()


def _group_tag(group: list[dict[str, Any]], group_field: str) -> str:
    for mapping in group:
        path = repeat_source(mapping_source_path(mapping))
        if path and path[1] == group_field and mapping.get("controlTag"):
            return str(mapping["controlTag"])
    return ""


def _detail_keys(group: list[dict[str, Any]]) -> list[str]:
    keys = []
    for mapping in group:
        path = repeat_source(mapping_source_path(mapping))
        if path and "[*]" in path[1]:
            keys.append(path[1].split("[*]", 1)[0])
    return list(dict.fromkeys(keys))


def _detail_key(group: list[dict[str, Any]], table_no: str, warn: Warn,
                prototype: etree._Element | None = None) -> str:
    """由原型数据行上的控件确定行数组，汇总行的数组不参与明细展开。"""
    candidates = group
    if prototype is not None:
        prototype_tags = set(prototype.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
        bound = [item for item in group if str(item.get("controlTag") or "") in prototype_tags]
        if bound:
            candidates = bound
    unique = _detail_keys(candidates)
    if len(unique) > 1:
        warn("MULTIPLE_DETAIL_LEVELS", table_no,
             f"该编组的字段分布在多个明细数组里（{'、'.join(unique)}），一张表只能有一个明细层；"
             f"请检查原型数据行上的字段绑定。")
    return unique[0] if unique else ""


def _row_units(records: list[dict[str, Any]],
               detail_key: str) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """行单元：有明细层就展开成每条明细一行，否则分组记录本身就是一行。"""
    if detail_key and not any(isinstance(record.get(detail_key), list) for record in records):
        # 数据集合本身就是 `$.<detail_key>[*]` 的明细数组，而不是包含该数组的
        # 外层分组。此时同一条记录同时承担两层取值，通配路径才能正常写入。
        return [(record, record) for record in records]
    units: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for record in records:
        if not detail_key:
            units.append((record, None))
            continue
        units.extend((record, detail) for detail in _group_rows(record, detail_key))
    return units


def _group_rows(record: dict[str, Any], detail_key: str) -> list[dict[str, Any]]:
    """一个分组下的明细记录；没有明细层时分组本身就是唯一一行。"""
    if not detail_key:
        return [record]
    rows = record.get(detail_key)
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def _is_detail_path(path: tuple[str, str], detail_key: str) -> bool:
    relative = path[1]
    prefix = f"{detail_key}[*]"
    return bool(detail_key) and (relative == prefix or relative.startswith(prefix + "."))


def _level_value(path: tuple[str, str], group_record: dict[str, Any],
                 detail_record: dict[str, Any] | None, detail_key: str) -> Any:
    """明细数组从行记录取值，其他嵌套数组按单条汇总值解包。"""
    if _is_detail_path(path, detail_key):
        if detail_record is None:
            return None
        return record_value(detail_record, path[1].split("[*].", 1)[-1])
    value = record_value(group_record, path[1])
    if "[*]" not in path[1] or not isinstance(value, list):
        return value
    return value[0] if len(value) == 1 else None


def _fixed_level_value(path: tuple[str, str], group_record: dict[str, Any],
                       detail_key: str, mapping: dict[str, Any], table_no: str,
                       warn: Warn) -> Any:
    """汇总/固定字段允许单元素数组；多元素时显式报警并不猜取。"""
    value = record_value(group_record, path[1])
    if _is_detail_path(path, detail_key) or "[*]" not in path[1] or not isinstance(value, list):
        return value
    if len(value) > 1:
        warn("SUMMARY_VALUE_NOT_UNIQUE", table_no,
             f"固定字段“{mapping.get('wordLabel') or mapping.get('fieldCode')}”在每个分组中有 {len(value)} 个值，"
             "无法确定应写入哪一个。")
        return None
    return value[0] if value else None


def _fill_level_controls(cells: list[etree._Element], group_record: dict[str, Any],
                         detail_record: dict[str, Any] | None, detail_key: str, table_no: str,
                         group: list[dict[str, Any]], source: tuple[str, str],
                         report_data: dict[str, Any], values: dict[str, Any], warn: Warn) -> None:
    """按原型行确定的明细层取行值，其余字段从当前分组记录取固定值。"""
    controls: dict[str, etree._Element] = {}
    for cell in cells:
        for control in cell.xpath(".//w:sdt", namespaces=NS):
            controls[tag_of(control)] = control
    row_values = row_calculated_values(group, detail_record or group_record, values, report_data)
    for mapping in group:
        control = controls.get(str(mapping.get("controlTag") or ""))
        if control is None:
            continue
        if is_formula_calculation(mapping):
            set_control_text(control, format_value(row_values.get(str(mapping.get("fieldCode"))), mapping))
            continue
        path = repeat_source(mapping_source_path(mapping))
        if not path:
            warn("FIELD_PATH_MISSING", table_no,
                 f"字段“{mapping.get('wordLabel') or mapping.get('fieldCode')}”在标准字段目录里没有可用的"
                 f"取值路径（多半是所属编组的数据集合路径没配），已跳过填充。")
            continue
        if path[0] != source[0]:
            warn("FIELD_SOURCE_MISMATCH", table_no,
                 f"字段“{mapping.get('wordLabel') or mapping.get('fieldCode')}”取自 {path[0]}，"
                 f"与本表的数据集合 {source[0]} 不一致，已跳过填充。")
            continue
        if _is_detail_path(path, detail_key) and detail_record is None:
            continue
        value = (_level_value(path, group_record, detail_record, detail_key)
                 if _is_detail_path(path, detail_key)
                 else _fixed_level_value(path, group_record, detail_key, mapping, table_no, warn))
        set_control_text(control, format_value(value, mapping))


def _fill_grouped_table(table: etree._Element, prototype: etree._Element, table_no: str,
                        group: list[dict[str, Any]], records: list[dict[str, Any]],
                        source: tuple[str, str], report_data: dict[str, Any], values: dict[str, Any],
                        layout: TableLayoutRules, warn: Warn) -> None:
    """向下填充 + 向右分组：编组数组的每个元素就是一个分组，明细数组就是行。"""
    group_field = layout.group_field(table_no)
    tag = _group_tag(group, group_field)
    if not tag:
        warn("GROUP_FIELD_NOT_BOUND", table_no,
             f"表格配置了横向分组字段 {group_field}，但它没有绑定到 Word 里的内容控件；"
             f"请先在模板设计器里把该字段绑到分组表头格。")
        return
    rows = table.xpath("./w:tr", namespaces=NS)
    span = find_group_span(rows, tag)
    if not span:
        warn("GROUP_SPAN_NOT_FOUND", table_no,
             f"在 Word 表格里找不到横向分组字段 {group_field} 的控件，无法确定一个分组占几列。")
        return
    groups = [item for item in records if isinstance(item, dict)
              and record_value(item, group_field) not in (None, "")]
    if not groups:
        warn("GROUP_VALUES_MISSING", table_no,
             f"数据里没有字段 {group_field} 的取值，无法确定横向分组，已保留 Word 原有内容。")
        return
    names = [str(record_value(item, group_field)) for item in groups]
    detail_key = _detail_key(group, table_no, warn, prototype)
    width, start = span[1] - span[0] + 1, span[0]
    for row_blocks in expand_group_columns(table, span, len(groups), layout.equal_group_columns(table_no)):
        fill_group_headers(row_blocks, tag, names)

    def blocks_of(row: etree._Element) -> list[list[etree._Element]]:
        cells = row.xpath("./w:tc", namespaces=NS)
        return [cells[start - 1 + index * width:start - 1 + (index + 1) * width]
                for index in range(len(groups))]

    detail_rows = [_group_rows(item, detail_key) for item in groups]
    parent, insert_at = prototype.getparent(), prototype.getparent().index(prototype)
    row_count = max((len(items) for items in detail_rows), default=0)
    data_rows = _clone_rows(prototype, parent, insert_at, list(range(row_count)))
    for index, row in enumerate(data_rows):
        shared = row.xpath("./w:tc", namespaces=NS)[:start - 1]
        first = next(((groups[position], items[index]) for position, items in enumerate(detail_rows)
                      if index < len(items)), None)
        if first:
            _fill_level_controls(shared, first[0], first[1], detail_key, table_no, group, source,
                                 report_data, values, warn)
        for position, cells in enumerate(blocks_of(row)):
            if index < len(detail_rows[position]):
                _fill_level_controls(cells, groups[position], detail_rows[position][index],
                                     detail_key, table_no, group, source, report_data, values, warn)
    group_tags = {str(item.get("controlTag") or "") for item in group if item.get("controlTag")}
    for row in table.xpath("./w:tr", namespaces=NS):
        tags = set(row.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
        if row in data_rows or not (tags & group_tags) or tag in tags:
            continue
        for position, cells in enumerate(blocks_of(row)):
            _fill_level_controls(cells, groups[position], None, detail_key, table_no, group,
                                 source, report_data, values, warn)


def _fill_row_repeat_table(document: etree._Element, table_no: str, group: list[dict[str, Any]],
                           mappings: list[dict[str, Any]], records: list[dict[str, Any]],
                           source: tuple[str, str], empty_behavior: str, report_data: dict[str, Any],
                           values: dict[str, Any], layout: TableLayoutRules, warn: Warn) -> None:
    prototype = _prototype_row(document, table_no, mappings, layout, warn)
    if prototype is None:
        return
    parent = prototype.getparent()
    insert_at = parent.index(prototype)
    _reset_prototype_row(prototype, {item.get("controlTag", "") for item in group})
    if not records and empty_behavior == "HIDE":
        parent.remove(prototype)
        return
    if layout.group_field(table_no):
        _fill_grouped_table(prototype.xpath("ancestor::w:tbl[1]", namespaces=NS)[0],
                            prototype, table_no, group, records, source, report_data,
                            values, layout, warn)
        return
    direct_tags = {item.get("controlTag", "") for item in mappings
                   if item.get("controlTag") and item.get("repeatType") != "ROW"}
    _drop_stale_rows(parent, insert_at, direct_tags, layout.preserved_row_labels(table_no))
    detail_key = _detail_key(group, table_no, warn, prototype)
    units = _row_units(records, detail_key)
    rows = _clone_rows(prototype, parent, insert_at, units, group)
    for row, (group_record, detail_record) in zip(rows, units):
        _fill_level_controls(row.xpath("./w:tc", namespaces=NS), group_record, detail_record,
                             detail_key, table_no, group, source, report_data, values, warn)
    fill_preserved_summary_rows(parent, rows, records, table_no, group, source, report_data,
                                values, layout, warn, detail_key, _fill_level_controls)
    if len(rows) > 1:
        _apply_vertical_merge(rows, units, group, report_data, detail_key)


def fill_repeat_rows(document: etree._Element, mappings: list[dict[str, Any]], payload: dict[str, Any],
                     report_data: dict[str, Any], values: dict[str, Any],
                     layout: TableLayoutRules, warn: Warn) -> None:
    for table_no, group in _group_mappings(mappings).items():
        source = _group_source(table_no, group, warn)
        if not source:
            warn("BLOCK_SOURCE_MISSING", table_no,
                 "内容块和字段都没有配置循环数据集合，已保留 Word 模板中的原有内容。")
            continue
        source_mapping = next((item for item in group
                               if (repeat_source(mapping_source_path(item)) or ('', ''))[0] == source[0]), None)
        if source_mapping is None:
            warn('BLOCK_SOURCE_MISSING', table_no, '循环表没有属于目标编组的字段映射，请修正模板绑定。')
            continue
        # payload 是字段解析完成后的渲染视图，里面既有选定的直接来源记录，也有按标准路径
        # 落位的 AI/计算字段。循环表必须读取这份视图，不能根据首个字段重新切回 Excel/LIMS
        # 命名空间，否则同一编组内的派生字段会在 Word 写入阶段丢失。
        raw_records = payload.get(source[0])
        empty_behavior = next((item.get("blockEmptyBehavior") for item in group
                               if item.get("blockEmptyBehavior")), "KEEP")
        if raw_records is None and source[0] not in payload:
            # 可选编组没有出现在当前来源时，仍按内容块的“无数据时”规则处理；
            # 否则 KEEP 会跳过原型行，导致控件里的模板示例文字泄漏到报告。
            records = []
        elif isinstance(raw_records, list):
            records = raw_records
        else:
            warn("BLOCK_SOURCE_NOT_ARRAY", table_no,
                 f"循环集合 {source[0]} 缺失或不是数组，无法填充 Word 表格。")
            continue
        records = _prepare_repeat_records(records, group)
        if layout.is_table_repeat(table_no):
            fill_table_repeat(document, table_no, group, mappings, records, source,
                              empty_behavior, report_data, values, layout, warn,
                              _fill_row_repeat_table)
            continue
        if _is_matrix(table_no, group, layout, warn):
            _fill_matrix_block(document, table_no, records, empty_behavior, layout, warn, group)
            continue
        _fill_row_repeat_table(document, table_no, group, mappings, records, source,
                               empty_behavior, report_data, values, layout, warn)
