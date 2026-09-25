"""Render structured field values as native Word paragraphs and tables."""

from typing import Any

from lxml import etree

from .docx_field_values import W, format_value, set_control_text
from .rich_blocks import is_rich_value


def _paragraph(text: str) -> etree._Element:
    paragraph = etree.Element(W + "p")
    run = etree.SubElement(paragraph, W + "r")
    node = etree.SubElement(run, W + "t")
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    node.text = text
    return paragraph


def _run_text(value: dict[str, Any]) -> etree._Element:
    run = etree.Element(W + "r")
    if value.get("subscript") or value.get("superscript"):
        properties = etree.SubElement(run, W + "rPr")
        vertical = "subscript" if value.get("subscript") else "superscript"
        etree.SubElement(properties, W + "vertAlign", {W + "val": vertical})
    node = etree.SubElement(run, W + "t")
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    node.text = str(value.get("text") or "")
    return run


def _rich_paragraph(block: dict[str, Any]) -> etree._Element:
    runs = block.get("runs")
    if not isinstance(runs, list):
        return _paragraph(block["text"])
    paragraph = etree.Element(W + "p")
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("text"), str):
            raise ValueError("结构化字段存在无效的行内文本")
        paragraph.append(_run_text(run))
    return paragraph


def _cell(value: dict[str, Any], width: int, merge: str = "") -> etree._Element:
    cell = etree.Element(W + "tc")
    properties = etree.SubElement(cell, W + "tcPr")
    cell_width = etree.SubElement(properties, W + "tcW")
    cell_width.set(W + "w", str(width))
    cell_width.set(W + "type", "dxa")
    span = value.get("colspan", 1)
    if span > 1:
        etree.SubElement(properties, W + "gridSpan").set(W + "val", str(span))
    if merge:
        etree.SubElement(properties, W + "vMerge").set(W + "val", merge)
    if merge == "continue" or not value.get("runs"):
        cell.append(_paragraph(value.get("text", "") if merge != "continue" else ""))
    else:
        cell.append(_rich_paragraph(value))
    return cell


def _width(node: etree._Element | None) -> int | None:
    if node is None or node.get(W + "type") != "dxa":
        return None
    try:
        width = int(node.get(W + "w", ""))
    except ValueError as error:
        raise ValueError("Word 表格宽度不是有效的整数") from error
    return width if width > 0 else None


def _cell_width(cell: etree._Element) -> int:
    width = _width(cell.find("./" + W + "tcPr/" + W + "tcW"))
    if width is None:
        table = cell.xpath("ancestor::w:tbl[1]", namespaces={"w": W[1:-1]})[0]
        grid = table.find(W + "tblGrid")
        columns = [] if grid is None else grid.findall(W + "gridCol")
        row = cell.getparent()
        cells = row.findall(W + "tc")
        before = row.find("./" + W + "trPr/" + W + "gridBefore")
        start = int(before.get(W + "val")) if before is not None else 0
        for previous in cells[:cells.index(cell)]:
            previous_span = previous.find("./" + W + "tcPr/" + W + "gridSpan")
            start += int(previous_span.get(W + "val")) if previous_span is not None else 1
        span_node = cell.find("./" + W + "tcPr/" + W + "gridSpan")
        span = int(span_node.get(W + "val")) if span_node is not None else 1
        grid_widths = [column.get(W + "w", "") for column in columns[start:start + span]]
        if len(grid_widths) == span:
            try:
                parsed = [int(value) for value in grid_widths]
            except ValueError as error:
                raise ValueError("Word 表格列宽不是有效的整数") from error
            if all(value > 0 for value in parsed):
                width = sum(parsed)
    if width is None:
        raise ValueError("Word 表格单元格缺少可计算的宽度，无法排版内嵌表格")
    return width


def _container_width(control: etree._Element) -> int:
    cell = control.getparent()
    if cell.tag != W + "tc":
        return 9000
    table = cell.xpath("ancestor::w:tbl[1]", namespaces={"w": W[1:-1]})[0]
    table_margins = table.find("./" + W + "tblPr/" + W + "tblCellMar")
    cell_margins = cell.find("./" + W + "tcPr/" + W + "tcMar")
    margins = 0
    for side in ("left", "right"):
        local = None if cell_margins is None else _width(cell_margins.find(W + side))
        inherited = None if table_margins is None else _width(table_margins.find(W + side))
        margins += local if local is not None else inherited or 0
    available = _cell_width(cell) - margins
    if available < 1:
        raise ValueError("Word 表格单元格扣除内边距后没有可用宽度")
    return min(9000, available)


def _table(rows: list[list[dict[str, Any]]], available_width: int) -> etree._Element:
    if not rows or not rows[0]:
        raise ValueError("结构化字段的表格没有行或列")
    columns = sum(cell["colspan"] for cell in rows[0])
    if columns > 32:
        raise ValueError("结构化字段的表格列数超过 32")
    unit = available_width // columns
    if unit < 1:
        raise ValueError("Word 表格单元格宽度不足以容纳内嵌表格列")
    table = etree.Element(W + "tbl")
    properties = etree.SubElement(table, W + "tblPr")
    if available_width < 9000:
        etree.SubElement(properties, W + "tblW", {W + "w": str(unit * columns), W + "type": "dxa"})
        etree.SubElement(properties, W + "tblLayout", {W + "type": "fixed"})
    else:
        etree.SubElement(properties, W + "tblW", {W + "w": "0", W + "type": "auto"})
    borders = etree.SubElement(properties, W + "tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        etree.SubElement(borders, W + side, {W + "val": "single", W + "sz": "4"})
    grid = etree.SubElement(table, W + "tblGrid")
    for _ in range(columns):
        etree.SubElement(grid, W + "gridCol", {W + "w": str(unit)})
    active: dict[int, tuple[int, dict[str, Any]]] = {}
    for source_row in rows:
        row = etree.SubElement(table, W + "tr")
        column = 0
        index = 0
        next_active: dict[int, tuple[int, dict[str, Any]]] = {}
        while column < columns:
            if column in active:
                remaining, source = active[column]
                span = source["colspan"]
                row.append(_cell(source, unit * span, "continue"))
                if remaining > 1:
                    next_active[column] = (remaining - 1, source)
            else:
                if index >= len(source_row):
                    raise ValueError("结构化字段的表格行列或跨行配置不一致")
                source = source_row[index]
                index += 1
                span = source["colspan"]
                if source["rowspan"] > 1:
                    row.append(_cell(source, unit * span, "restart"))
                    next_active[column] = (source["rowspan"] - 1, source)
                else:
                    row.append(_cell(source, unit * span))
            if column + span > columns or any(position in active and position != column
                                              for position in range(column, column + span)):
                raise ValueError("结构化字段的表格合并单元格位置冲突")
            column += span
        if index != len(source_row):
            raise ValueError("结构化字段的表格行超出表格宽度")
        active = next_active
    if active:
        raise ValueError("结构化字段的表格跨行数超出表格范围")
    return table


def set_control_rich_blocks(control: etree._Element, values: list[dict[str, Any]]) -> None:
    content = control.find(W + "sdtContent")
    if content is None or control.getparent().tag not in {W + "body", W + "tc", W + "hdr", W + "ftr"}:
        raise ValueError("结构化字段必须绑定段落级或表格单元格内的块级内容控件")
    if not values or not all(is_rich_value(value) for value in values):
        raise ValueError("结构化字段的记录格式不一致")
    nodes = []
    available_width = None
    for value in values:
        blocks = value.get("blocks")
        if not isinstance(blocks, list):
            raise ValueError("结构化字段缺少内容块")
        for block in blocks:
            if block.get("type") == "paragraph" and isinstance(block.get("text"), str):
                nodes.append(_rich_paragraph(block))
            elif block.get("type") == "table" and isinstance(block.get("rows"), list):
                if available_width is None:
                    available_width = _container_width(control)
                nodes.append(_table(block["rows"], available_width))
            else:
                raise ValueError("结构化字段存在无效的段落或表格")
    for child in list(content):
        content.remove(child)
    for node in nodes:
        content.append(node)
    if not nodes or nodes[-1].tag == W + "tbl":
        content.append(_paragraph(""))


def set_mapped_control(control: etree._Element, value: Any, mapping: dict[str, Any]) -> None:
    if is_rich_value(value):
        set_control_rich_blocks(control, [value])
    elif isinstance(value, list) and value and any(is_rich_value(item) for item in value):
        set_control_rich_blocks(control, value)
    else:
        set_control_text(control, format_value(value, mapping), image=mapping.get("dataType") == "image")
