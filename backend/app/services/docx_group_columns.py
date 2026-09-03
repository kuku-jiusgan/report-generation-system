"""表格的横向分组扩列：一个分组的单元格整块向右复制。

向下填充已经解决了"一条记录一行、哪一格填哪个字段由控件绑定决定"。有些表还有
第二个维度：同样的几列要按某个字段（例如杂质名称）重复若干组。这里只做横向那一步，
纵向仍然交给原来的循环行填充。

一个分组占哪几列不需要配置：绑定了分组字段的那个表头格，它的 gridSpan 就是分组宽度。
整块复制单元格，子列标题、内容控件、字段对应关系都跟着单元格走，不用再声明一遍。
"""

import copy
from typing import Any, Callable

from lxml import etree

from .docx_table_cells import (
    NS, W, cell_width, grid_after, grid_span, set_cell_text, set_cell_width,
    stretch_merged_row, sync_table_grid,
)


Warn = Callable[[str, str, str], None]
EQUAL_WIDTH = "EQUAL"


def _cell_columns(row: etree._Element) -> list[tuple[etree._Element, int, int]]:
    """行里每一格覆盖的网格列区间（起始列, 结束列），列号从 1 开始。"""
    spans, column = [], 1
    for cell in row.xpath("./w:tc", namespaces=NS):
        width = grid_span(cell)
        spans.append((cell, column, column + width - 1))
        column += width
    return spans


def find_group_span(rows: list[etree._Element], group_tag: str) -> tuple[int, int] | None:
    """分组字段控件所在格覆盖的列区间，就是一个分组的宽度。"""
    for row in rows:
        for cell, start, end in _cell_columns(row):
            if group_tag in cell.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS):
                return start, end
    return None


def _block_cells(row: etree._Element, span: tuple[int, int]) -> list[etree._Element]:
    """落在分组跨度内、需要按分组复制的单元格。"""
    start, end = span
    return [cell for cell, first, last in _cell_columns(row) if first >= start and last <= end]


def _scaled_widths(prototype: list[int], group_count: int, equal: bool) -> list[int]:
    region = sum(prototype)
    weights = [1.0] * len(prototype) if equal else [float(value) for value in prototype]
    total = sum(weights) * group_count or 1.0
    return [max(1, round(region * weight / total)) for weight in weights]


def _clone_block(row: etree._Element, block: list[etree._Element], group_count: int,
                 widths: list[int]) -> list[list[etree._Element]]:
    """把一个分组的单元格整块复制成 group_count 组，返回每组的单元格。"""
    for cell, width in zip(block, widths):
        set_cell_width(cell, width)
    blocks = [block]
    anchor = block[-1]
    for _ in range(group_count - 1):
        clone = [copy.deepcopy(cell) for cell in block]
        for cell in clone:
            for bookmark in cell.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
                bookmark.getparent().remove(bookmark)
        for cell in clone:
            anchor.addnext(cell)
            anchor = cell
        blocks.append(clone)
    return blocks


def expand_group_columns(table: etree._Element, span: tuple[int, int], group_count: int,
                         equal_width: bool) -> list[list[list[etree._Element]]]:
    """把整张表按分组数向右扩列，返回每一行各分组的单元格。

    列宽保持原表总宽度：分组区间的宽度按组数平摊，其余列不动。
    """
    rows = table.xpath("./w:tr", namespaces=NS)
    prototype = next(([cell_width(cell) for cell in _block_cells(row, span)] for row in rows
                      if len(_block_cells(row, span)) > 1), [])
    if not prototype:
        prototype = [cell_width(cell) for cell in _block_cells(rows[0], span)] if rows else []
    widths = _scaled_widths(prototype, group_count, equal_width) if prototype else []
    expanded: list[list[list[etree._Element]]] = []
    for row in rows:
        block = _block_cells(row, span)
        expanded.append(_clone_block(row, block, group_count, widths) if block else [])
    _sync_grid(table, rows, span, widths, group_count)
    return expanded


def _sync_grid(table: etree._Element, rows: list[etree._Element], span: tuple[int, int],
               widths: list[int], group_count: int) -> None:
    grid = table.find(W + "tblGrid")
    columns = grid.findall(W + "gridCol") if grid is not None else []
    original = []
    for column in columns:
        try:
            original.append(max(1, int(column.get(W + "w") or 1)))
        except (TypeError, ValueError):
            original.append(1)
    start, end = span
    leading = original[:start - 1]
    trailing = original[end:]
    sync_table_grid(table, leading + widths * group_count + trailing)
    total = len(leading) + len(widths) * group_count + len(trailing)
    for row in rows:
        used = sum(grid_span(cell) for cell in row.xpath("./w:tc", namespaces=NS)) + grid_after(row)
        if used != total:
            stretch_merged_row(row, total)


def fill_group_headers(blocks: list[list[etree._Element]], group_tag: str,
                       names: list[str]) -> None:
    """分组表头格：每一组写自己的分组名。"""
    for cells, name in zip(blocks, names):
        for cell in cells:
            if group_tag in cell.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS):
                set_cell_text(cell, name)
