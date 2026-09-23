"""Extract ordered text and nested tables from configured LIMS HTML cells."""

import re
from typing import Any

from lxml import html

from .lims_table_utils import clean_cell, table_cell_grid
from .rich_blocks import RICH_BLOCKS


def _is_vertical_style(node: html.HtmlElement, value: str) -> bool:
    style = str(node.get("style") or "").lower().replace(" ", "")
    return f"vertical-align:{value}" in style


def _runs(node: html.HtmlElement, subscript: bool = False,
          superscript: bool = False) -> list[dict[str, Any]]:
    tag = str(node.tag).lower()
    subscript = subscript or tag == "sub" or _is_vertical_style(node, "sub")
    superscript = superscript or tag == "sup" or _is_vertical_style(node, "super")
    if subscript and superscript:
        raise ValueError("LIMS 文本同时包含下标和上标样式")
    runs: list[dict[str, Any]] = []
    if node.text:
        runs.append({"text": node.text, "subscript": subscript, "superscript": superscript})
    for child in node:
        runs.extend(_runs(child, subscript, superscript))
        if child.tail:
            runs.append({"text": child.tail, "subscript": subscript, "superscript": superscript})
    return runs


def _rich_text(node: html.HtmlElement) -> tuple[str, list[dict[str, Any]]]:
    if node.xpath(".//img | self::img"):
        raise ValueError("LIMS 单元格包含图片，当前结构化字段不支持图片，请检查源数据")
    runs: list[dict[str, Any]] = []
    for source in _runs(node):
        text = clean_cell(source["text"])
        if not text:
            continue
        current = {"text": text}
        if source["subscript"]:
            current["subscript"] = True
        if source["superscript"]:
            current["superscript"] = True
        if runs and runs[-1].get("subscript") == current.get("subscript") \
                and runs[-1].get("superscript") == current.get("superscript"):
            runs[-1]["text"] += text
        else:
            runs.append(current)
    return "".join(run["text"] for run in runs), runs


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
            text, runs = _rich_text(cell)
            value = {"text": text, "colspan": colspan, "rowspan": rowspan}
            if any(run.get("subscript") or run.get("superscript") for run in runs):
                value["runs"] = runs
            cells.append(value)
        if cells:
            rows.append(cells)
    if not rows:
        raise ValueError("LIMS 内嵌表格没有数据行")
    return {"type": "table", "rows": rows}


def rich_cell(cell: html.HtmlElement, transform_text) -> dict[str, Any] | None:
    blocks: list[dict[str, Any]] = []

    def add_text(value: str, runs: list[dict[str, Any]] | None = None,
                 merge: bool = False) -> None:
        normalized = re.sub(r"\s+", " ", str(value or ""))
        leading = normalized[:len(normalized) - len(normalized.lstrip())]
        trailing = normalized[len(normalized.rstrip()):]
        cleaned = normalized.strip()
        if not cleaned:
            return
        text = transform_text(cleaned)
        if text:
            text = leading + text + trailing
            block: dict[str, Any] = {"type": "paragraph", "text": text}
            if runs and any(run.get("subscript") or run.get("superscript") for run in runs):
                block["runs"] = runs
            if merge and blocks and blocks[-1].get("type") == "paragraph":
                previous = blocks[-1]
                previous["text"] += block["text"]
                if "runs" in block:
                    previous.setdefault("runs", [{"text": previous["text"][:-len(block["text"])]}])
                    previous["runs"].extend(block["runs"])
                elif "runs" in previous:
                    previous["runs"].append({"text": block["text"]})
            else:
                blocks.append(block)

    add_text(cell.text or "")
    for child in cell:
        if child.tag == "table":
            blocks.append(_table(child))
        elif child.xpath(".//table"):
            raise ValueError("LIMS 单元格的段落内嵌表格暂不支持，请检查源数据")
        else:
            text, runs = _rich_text(child)
            add_text(text, runs, merge=child.tag in {"sub", "sup", "span"})
        add_text(child.tail or "", merge=child.tag in {"sub", "sup", "span"})
    return {"type": RICH_BLOCKS, "blocks": blocks} if blocks else None


def rich_table_cell(table: html.HtmlElement, row: int, column: int, transform_text) -> dict[str, Any] | None:
    grid = table_cell_grid(table)
    if row >= len(grid) or column >= len(grid[row]) or grid[row][column] is None:
        raise ValueError(f"LIMS 表格原始单元格与提取位置不一致：第 {row + 1} 行第 {column + 1} 列")
    return rich_cell(grid[row][column], transform_text)
