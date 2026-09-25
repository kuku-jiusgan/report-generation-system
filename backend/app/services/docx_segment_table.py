"""按可配置的行片段填充原型 Word 表格；保留原行与单元格格式。"""

import copy
from typing import Any

from lxml import etree

from .docx_field_values import format_value, record_value, set_control_text
from .docx_table_cells import NS, set_cell_text

W = f"{{{NS['w']}}}"


def _set_vertical_merge(cell: etree._Element, restart: bool) -> None:
    properties = cell.find("w:tcPr", NS)
    if properties is None:
        properties = etree.Element(W + "tcPr")
        cell.insert(0, properties)
    for merge in properties.findall("w:vMerge", NS):
        properties.remove(merge)
    merge = etree.SubElement(properties, W + "vMerge")
    if restart:
        merge.set(W + "val", "restart")


def apply_segment_vertical_merges(table: etree._Element,
                                  mappings: list[dict[str, Any]]) -> None:
    """Merge equal adjacent values for controls in a segment-repeat table."""
    merge_tags = {
        str(item.get("controlTag"))
        for item in mappings
        if item.get("controlTag") and (
            item.get("mergeRule") == "VERTICAL_BY_VALUE"
            or item.get("blockMergeRule") == "VERTICAL_BY_VALUE"
        )
    }
    for tag in merge_tags:
        previous_value: str | None = None
        previous_cell: etree._Element | None = None
        for row in table.xpath("./w:tr", namespaces=NS):
            controls = row.xpath(".//w:sdt[w:sdtPr/w:tag/@w:val=$tag]", namespaces=NS, tag=tag)
            control = controls[0] if controls else None
            cell = control.xpath("ancestor::w:tc[1]", namespaces=NS)[0] if control is not None else None
            value = "".join(cell.xpath(".//w:t/text()", namespaces=NS)) if cell is not None else ""
            if cell is not None and value and value == previous_value and previous_cell is not None:
                _set_vertical_merge(previous_cell, True)
                _set_vertical_merge(cell, False)
                set_control_text(control, "")
            else:
                previous_cell = cell
            previous_value = value


def validate_segment_layout(layout: dict[str, Any]) -> None:
    segments = layout.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("行片段表必须配置非空 segments")
    rows: set[int] = set()
    paths: set[str] = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("行片段配置必须是对象")
        row = segment.get("row")
        source = segment.get("sourcePath")
        detail = segment.get("detailPath")
        cells = segment.get("detailCells")
        if (type(row) is not int or row < 1
                or not isinstance(source, str) or not source.strip()
                or not isinstance(detail, str) or not detail.strip()
                or not isinstance(cells, dict) or not cells):
            raise ValueError("行片段须配置正整数 row、来源对象路径、明细路径和 detailCells")
        if row in rows or source in paths:
            raise ValueError("行片段原型行和来源对象路径不能重复")
        rows.add(row)
        paths.add(source)
    summaries = layout.get("summaryRows", [])
    if not isinstance(summaries, list):
        raise ValueError("固定行 summaryRows 必须是数组")
    for summary in summaries:
        if (not isinstance(summary, dict) or type(summary.get("row")) is not int
                or summary["row"] < 1 or summary["row"] in rows
                or summary.get("sourcePath") not in paths):
            raise ValueError("固定行须配置未占用的正整数行号，以及已有片段的来源对象路径")
        rows.add(summary["row"])


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


def _fill_cells(row: etree._Element, source: dict[str, Any], fields: dict[str, Any],
                optional: bool = False) -> None:
    cells = row.xpath("./w:tc", namespaces=NS)
    for column, path in fields.items():
        index = int(column)
        if index < 0 or index >= len(cells):
            raise ValueError(f"行片段目标单元格 {column} 超出模板表格范围")
        if isinstance(path, dict):
            paths = path.get("fields")
            if not isinstance(paths, list) or not paths:
                raise ValueError("行片段组合字段必须配置非空 fields")
            parts = [record_value(source, str(field)) for field in paths]
            value = str(path.get("separator", "")).join(str(part) for part in parts) if all(
                part not in (None, "") for part in parts) else None
        else:
            value = record_value(source, str(path))
        if value in (None, ""):
            if optional:
                _text(cells[index], "")
                continue
            raise ValueError(f"行片段字段 {path} 缺少取值")
        _text(cells[index], value)


def fill_segment_table(table: etree._Element, record: dict[str, Any],
                       layout: dict[str, Any]) -> None:
    validate_segment_layout(layout)
    original = table.xpath("./w:tr", namespaces=NS)
    segments = layout.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("行片段表必须配置非空 segments")
    prepared: list[tuple[etree._Element, list[etree._Element], dict[str, Any], dict[str, Any], list[Any]]] = []
    used_rows: set[int] = set()
    source_paths: set[str] = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("行片段配置必须是对象")
        row_number = int(segment["row"])
        source_path = str(segment.get("sourcePath") or "")
        detail_path = str(segment.get("detailPath") or "")
        if not source_path or source_path in source_paths or not detail_path:
            raise ValueError("行片段必须配置互不重复的来源对象路径及明细路径")
        source = record_value(record, source_path)
        if not isinstance(source, dict):
            raise ValueError(f"行片段来源对象 {source_path} 缺失")
        details = record_value(source, detail_path)
        if not isinstance(details, list) or not details:
            raise ValueError(f"行片段 {row_number} 的明细数据缺失或为空")
        if row_number < 1 or row_number > len(original) or row_number in used_rows:
            raise ValueError(f"行片段原型行 {row_number} 无效或重复")
        source_paths.add(source_path)
        used_rows.add(row_number)
        prototype = original[row_number - 1]
        clones = [prototype] + [copy.deepcopy(prototype) for _ in range(len(details) - 1)]
        prepared.append((prototype, clones, segment, source, details))
    for prototype, clones, segment, source, details in sorted(
        prepared, key=lambda item: int(item[2]["row"]), reverse=True,
    ):
        parent = prototype.getparent()
        index = parent.index(prototype)
        for offset, clone in enumerate(clones[1:], 1):
            for bookmark in clone.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
                bookmark.getparent().remove(bookmark)
            parent.insert(index + offset, clone)
        for offset, row in enumerate(clones):
            detail = details[offset]
            if not isinstance(detail, dict):
                raise ValueError("行片段明细记录必须是对象")
            _fill_cells(row, detail, segment.get("detailCells") or {})
    for summary in layout.get("summaryRows") or []:
        row_number = int(summary["row"])
        if row_number < 1 or row_number > len(original) or row_number in used_rows:
            raise ValueError(f"汇总行 {row_number} 无效或与明细原型行冲突")
        source_path = str(summary.get("sourcePath") or "")
        source = record_value(record, source_path)
        if not isinstance(source, dict):
            raise ValueError(f"汇总行 {row_number} 的来源对象 {source_path} 缺失")
        _fill_cells(original[row_number - 1], source, summary.get("cells") or {},
                    bool(summary.get("optional")))
        _fill_cells(original[row_number - 1], record, summary.get("rootCells") or {},
                    bool(summary.get("optional")))


def fill_segment_heading(heading: etree._Element, record: dict[str, Any],
                         layout: dict[str, Any],
                         field_mapping: dict[str, Any] | None = None) -> None:
    field = str(layout.get("headingField") or "")
    value = record_value(record, field)
    if value in (None, ""):
        raise ValueError(f"行片段表标题字段 {field} 缺失")
    rendered = format_value(value, field_mapping or {})
    texts = heading.xpath(".//w:t", namespaces=NS)
    if not texts:
        raise ValueError("行片段表标题段落没有可填写的文字")
    texts[0].text = rendered
    for text in texts[1:]:
        text.text = ""
