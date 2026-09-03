"""Word 表格单元格的低层读写helper。

只做 WordprocessingML 结构操作（文字、宽度、合并跨度、网格），
不含任何业务规则；矩阵填充与循环行填充共用这一份实现。
"""

import copy
from typing import Any

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS)).strip()


def set_cell_text(cell: etree._Element, value: Any) -> None:
    texts = cell.xpath(".//w:t", namespaces=NS)
    if not texts:
        content = cell.find(".//" + W + "sdtContent")
        owner = content if content is not None else cell
        paragraph = owner.find(W + "p")
        if paragraph is None:
            paragraph = etree.SubElement(owner, W + "p")
        texts = [etree.SubElement(etree.SubElement(paragraph, W + "r"), W + "t")]
    texts[0].text = "" if value is None else str(value)
    for text in texts[1:]:
        text.text = ""


def _properties(cell: etree._Element) -> etree._Element:
    properties = cell.find(W + "tcPr")
    if properties is None:
        properties = etree.Element(W + "tcPr")
        cell.insert(0, properties)
    return properties


def set_cell_width(cell: etree._Element, width: int) -> None:
    properties = _properties(cell)
    width_node = properties.find(W + "tcW")
    if width_node is None:
        width_node = etree.SubElement(properties, W + "tcW")
    width_node.set(W + "w", str(max(1, int(width))))
    width_node.set(W + "type", "dxa")


def cell_width(cell: etree._Element, default: int = 1) -> int:
    try:
        return max(1, int(cell.xpath("string(./w:tcPr/w:tcW/@w:w)", namespaces=NS)))
    except (TypeError, ValueError):
        return default


def set_grid_span(cell: etree._Element, span: int) -> None:
    properties = _properties(cell)
    node = properties.find(W + "gridSpan")
    if node is None:
        node = etree.SubElement(properties, W + "gridSpan")
    node.set(W + "val", str(max(1, int(span))))


def grid_span(cell: etree._Element) -> int:
    try:
        return max(1, int(cell.xpath("string(./w:tcPr/w:gridSpan/@w:val)", namespaces=NS)))
    except (TypeError, ValueError):
        return 1


def grid_after(row: etree._Element) -> int:
    """行尾保留的空网格列数；模板用它让部分行比表格窄一列。"""
    try:
        return max(0, int(row.xpath("string(./w:trPr/w:gridAfter/@w:val)", namespaces=NS)))
    except (TypeError, ValueError):
        return 0


def sync_table_grid(table: etree._Element, widths: list[int]) -> None:
    grid = table.find(W + "tblGrid")
    if grid is None:
        grid = etree.Element(W + "tblGrid")
        table.insert(1, grid)
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        etree.SubElement(grid, W + "gridCol").set(W + "w", str(max(1, int(width))))


def resize_row(row: etree._Element, target: int) -> list[etree._Element]:
    """把一行的单元格数量调整到 target 个，缺的按最后一格克隆。"""
    cells = row.xpath("./w:tc", namespaces=NS)
    while len(cells) > target:
        row.remove(cells.pop())
    while len(cells) < target:
        source = cells[-1] if len(cells) > 1 else cells[0]
        clone = copy.deepcopy(source)
        row.append(clone)
        cells.append(clone)
    return cells


def stretch_merged_row(row: etree._Element, grid_columns: int) -> None:
    """整行合并的行（例如结论行）不参与扩列，只把末格跨度补到新的表格宽度。

    行占用的网格数必须与 tblGrid 一致，否则 Word 会认为表格结构损坏。
    """
    cells = row.xpath("./w:tc", namespaces=NS)
    if len(cells) < 2:
        return
    used = sum(grid_span(cell) for cell in cells) + grid_after(row)
    if used != grid_columns:
        set_grid_span(cells[-1], grid_span(cells[-1]) + grid_columns - used)
