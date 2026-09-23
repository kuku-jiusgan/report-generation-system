"""按可配置的行片段填充原型 Word 表格；保留原行与单元格格式。"""

import copy
from typing import Any

from lxml import etree

from .docx_field_values import record_value, set_control_text
from .docx_table_cells import NS, set_cell_text

W = f"{{{NS['w']}}}"


def _text(cell: etree._Element, value: Any) -> None:
    controls = cell.xpath(".//w:sdt", namespaces=NS)
    if controls:
        set_control_text(controls[0], "" if value is None else str(value))
    else:
        lines = str(value or "").split("\n")
        set_cell_text(cell, lines[0])
        first = cell.xpath(".//w:t", namespaces=NS)[0]
        run = first.getparent()
        for line in lines[1:]:
            etree.SubElement(run, W + "br")
            etree.SubElement(run, W + "t").text = line


def _fill_cells(row: etree._Element, source: dict[str, Any], fields: dict[str, str],
                optional: bool = False) -> None:
    cells = row.xpath("./w:tc", namespaces=NS)
    for column, path in fields.items():
        index = int(column)
        if index < 0 or index >= len(cells):
            raise ValueError(f"行片段目标单元格 {column} 超出模板表格范围")
        value = record_value(source, path)
        if value in (None, ""):
            if optional:
                _text(cells[index], "")
                continue
            raise ValueError(f"行片段字段 {path} 缺少取值")
        _text(cells[index], value)


def fill_segment_table(table: etree._Element, record: dict[str, Any],
                       layout: dict[str, Any]) -> None:
    original = table.xpath("./w:tr", namespaces=NS)
    segments = layout.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("行片段表必须配置非空 segments")
    detail_path = str(layout.get("detailPath") or "")
    details = record_value(record, detail_path)
    if not isinstance(details, list):
        raise ValueError(f"行片段明细 {detail_path} 缺失或不是数组")
    prepared: list[tuple[etree._Element, list[etree._Element], dict[str, Any]]] = []
    used_rows: set[int] = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("行片段配置必须是对象")
        row_number, start, count = (int(segment[key]) for key in ("row", "start", "count"))
        if row_number < 1 or row_number > len(original) or row_number in used_rows:
            raise ValueError(f"行片段原型行 {row_number} 无效或重复")
        if start < 0 or count < 1 or start + count > len(details):
            raise ValueError(f"行片段 {row_number} 的明细范围超出数据条数")
        used_rows.add(row_number)
        prototype = original[row_number - 1]
        clones = [prototype] + [copy.deepcopy(prototype) for _ in range(count - 1)]
        prepared.append((prototype, clones, segment))
    if sum(len(items) for _, items, _ in prepared) != len(details):
        raise ValueError("行片段配置未完整覆盖明细记录")
    for prototype, clones, segment in sorted(prepared, key=lambda item: int(item[2]["row"]), reverse=True):
        parent = prototype.getparent()
        index = parent.index(prototype)
        for offset, clone in enumerate(clones[1:], 1):
            for bookmark in clone.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
                bookmark.getparent().remove(bookmark)
            parent.insert(index + offset, clone)
        for offset, row in enumerate(clones):
            detail = details[int(segment["start"]) + offset]
            if not isinstance(detail, dict):
                raise ValueError("行片段明细记录必须是对象")
            _fill_cells(row, record, segment.get("groupCells") or {})
            _fill_cells(row, detail, segment.get("detailCells") or {})
    for summary in layout.get("summaryRows") or []:
        row_number = int(summary["row"])
        if row_number < 1 or row_number > len(original) or row_number in used_rows:
            raise ValueError(f"汇总行 {row_number} 无效或与明细原型行冲突")
        _fill_cells(original[row_number - 1], record, summary.get("cells") or {},
                    bool(summary.get("optional")))


def fill_segment_heading(heading: etree._Element, record: dict[str, Any],
                         layout: dict[str, Any]) -> None:
    field = str(layout.get("headingField") or "")
    value = record_value(record, field)
    if value in (None, ""):
        raise ValueError(f"行片段表标题字段 {field} 缺失")
    pattern = str(layout.get("headingFormat") or "{value}")
    if pattern.count("{value}") != 1:
        raise ValueError("行片段表标题格式必须且只能包含一次 {value}")
    texts = heading.xpath(".//w:t", namespaces=NS)
    if not texts:
        raise ValueError("行片段表标题段落没有可填写的文字")
    texts[0].text = pattern.replace("{value}", str(value))
    for text in texts[1:]:
        text.text = ""
