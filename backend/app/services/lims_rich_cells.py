"""Extract ordered text and nested tables from configured LIMS HTML cells."""

from typing import Any

from lxml import html

from .lims_table_utils import clean_cell, table_cell_grid
from .rich_blocks import RICH_BLOCKS


def _text(node: html.HtmlElement) -> str:
    if node.xpath(".//img | self::img"):
        raise ValueError("LIMS 单元格包含图片，当前结构化字段不支持图片，请检查源数据")
    # ponytail: 当前保留段落和表格的结构，单元格内字符样式仍按纯文本处理；
    # 若需保留加粗/字体，升级块格式并在 Word 渲染器中增加行内样式节点。
    return clean_cell(node.text_content())


def _table(table: html.HtmlElement) -> dict[str, Any]:
    rows = []
    for tr in table.xpath("./thead/tr|./tbody/tr|./tfoot/tr|./tr"):
        cells = []
        for cell in tr.xpath("./th|./td"):
            if cell.xpath(".//table"):
                raise ValueError("LIMS 单元格内的表格不能再嵌套表格")
            try:
                colspan = int(cell.get("colspan") or 1)
                rowspan = int(cell.get("rowspan") or 1)
            except ValueError as error:
                raise ValueError("LIMS 内嵌表格的合并行列数无效") from error
            if colspan < 1 or rowspan < 1:
                raise ValueError("LIMS 内嵌表格的合并行列数必须大于 0")
            cells.append({"text": _text(cell), "colspan": colspan, "rowspan": rowspan})
        if cells:
            rows.append(cells)
    if not rows:
        raise ValueError("LIMS 内嵌表格没有数据行")
    return {"type": "table", "rows": rows}


def rich_cell(cell: html.HtmlElement, transform_text) -> dict[str, Any] | None:
    blocks: list[dict[str, Any]] = []

    def add_text(value: str) -> None:
        cleaned = clean_cell(value)
        if not cleaned:
            return
        text = transform_text(cleaned)
        if text:
            blocks.append({"type": "paragraph", "text": text})

    add_text(cell.text or "")
    for child in cell:
        if child.tag == "table":
            blocks.append(_table(child))
        elif child.xpath(".//table"):
            raise ValueError("LIMS 单元格的段落内嵌表格暂不支持，请检查源数据")
        else:
            add_text(_text(child))
        add_text(child.tail or "")
    return {"type": RICH_BLOCKS, "blocks": blocks} if blocks else None


def rich_table_cell(table: html.HtmlElement, row: int, column: int, transform_text) -> dict[str, Any] | None:
    grid = table_cell_grid(table)
    if row >= len(grid) or column >= len(grid[row]) or grid[row][column] is None:
        raise ValueError(f"LIMS 表格原始单元格与提取位置不一致：第 {row + 1} 行第 {column + 1} 列")
    return rich_cell(grid[row][column], transform_text)
