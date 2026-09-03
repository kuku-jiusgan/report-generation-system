"""转置矩阵表的填充：一条记录占一列。

配置里的一行对应记录的一个字段（rowFields），整表只有一个取值的格子用 scalarCells。
横向分组不在这里——那属于"向下填充 + 向右分组"，见 docx_group_columns。
本模块只负责定位原型表并按版式写值，不含任何具体业务表号或字段名。
"""

import copy
from typing import Any, Callable

from lxml import etree

from .docx_table_cells import NS, set_cell_text
from .table_layout_rules import repeat_bookmark_name


Warn = Callable[[str, str, str], None]


def _layout_entries(layout: dict[str, Any], key: str) -> list[dict[str, Any]]:
    entries = layout.get(key) or []
    return [item for item in entries if isinstance(item, dict) and int(item.get("row", 0) or 0) > 0]


def _fill_row_fields(rows: list[etree._Element], layout: dict[str, Any],
                     records: list[dict[str, Any]]) -> None:
    """每条记录占一列：配置里的一行对应记录的一个字段。"""
    for entry in _layout_entries(layout, "rowFields"):
        row_index = int(entry["row"]) - 1
        if row_index >= len(rows):
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        for index, record in enumerate(records[:max(0, len(cells) - 1)], start=1):
            set_cell_text(cells[index], record.get(str(entry.get("field", "")), ""))


def _fill_row_labels(rows: list[etree._Element], layout: dict[str, Any]) -> None:
    for entry in _layout_entries(layout, "rowLabels"):
        row_index = int(entry["row"]) - 1
        if row_index >= len(rows):
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        if cells:
            set_cell_text(cells[0], str(entry.get("text", "")))


def _fill_scalar_cells(rows: list[etree._Element], layout: dict[str, Any],
                       record: dict[str, Any]) -> None:
    """整表只有一个取值的单元格，例如回归方程、相关系数、残差图。"""
    for entry in _layout_entries(layout, "scalarCells"):
        row_index, column_index = int(entry["row"]) - 1, int(entry.get("column", 0) or 0) - 1
        if row_index >= len(rows) or column_index < 0:
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        if column_index < len(cells):
            set_cell_text(cells[column_index], record.get(str(entry.get("field", "")), ""))


def _fill_table(table: etree._Element, records: list[dict[str, Any]],
                layout: dict[str, Any]) -> None:
    rows = table.xpath("./w:tr", namespaces=NS)
    for row in rows:
        for cell in row.xpath("./w:tc", namespaces=NS)[1:]:
            set_cell_text(cell, "")
    if not records:
        return
    _fill_row_fields(rows, layout, records)
    _fill_row_labels(rows, layout)
    _fill_scalar_cells(rows, layout, records[0])


def fill_matrix_table(table: etree._Element, records: list[dict[str, Any]],
                      layout: dict[str, Any]) -> None:
    """Fill one already-resolved prototype table without cloning it."""
    _fill_table(table, records, layout)


def fill_matrix_tables(document: etree._Element, table_no: str, records: list[dict[str, Any]],
                       layout: dict[str, Any], warn: Warn, physical_index: int = 0) -> None:
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='{repeat_bookmark_name(table_no)}']", namespaces=NS
    )
    if bookmarks:
        table = bookmarks[0].xpath("ancestor::w:tbl[1]", namespaces=NS)[0]
    else:
        tables = document.xpath(".//w:tbl", namespaces=NS)
        if physical_index < 1 or physical_index > len(tables):
            warn("MATRIX_TABLE_NOT_FOUND", table_no,
                 "找不到该矩阵表的原型表：字段没有绑定到 Word 表格，表格规则里也没有配置"
                 "Word 正文表格序号；请在模板设计器中补齐其中一项。")
            return
        table = tables[physical_index - 1]
    first_row_cells = table.xpath("./w:tr[1]/w:tc", namespaces=NS)
    group_size = max(1, len(first_row_cells) - 1)
    groups = [records[index:index + group_size] for index in range(0, len(records), group_size)] or [[]]
    parent, insert_at = table.getparent(), table.getparent().index(table)
    tables = [table]
    for offset in range(1, len(groups)):
        cloned = copy.deepcopy(table)
        for bookmark in cloned.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
            bookmark.getparent().remove(bookmark)
        parent.insert(insert_at + offset, cloned)
        tables.append(cloned)
    for target, group in zip(tables, groups):
        _fill_table(target, group, layout)
