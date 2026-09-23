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


def _table(rows: list[list[dict[str, Any]]]) -> etree._Element:
    if not rows or not rows[0]:
        raise ValueError("结构化字段的表格没有行或列")
    columns = sum(cell["colspan"] for cell in rows[0])
    if columns > 32:
        raise ValueError("结构化字段的表格列数超过 32")
    unit = max(1, 9000 // columns)
    table = etree.Element(W + "tbl")
    properties = etree.SubElement(table, W + "tblPr")
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
    for value in values:
        blocks = value.get("blocks")
        if not isinstance(blocks, list):
            raise ValueError("结构化字段缺少内容块")
        for block in blocks:
            if block.get("type") == "paragraph" and isinstance(block.get("text"), str):
                nodes.append(_rich_paragraph(block))
            elif block.get("type") == "table" and isinstance(block.get("rows"), list):
                nodes.append(_table(block["rows"]))
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
