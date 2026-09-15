"""循环表格中保留的汇总行处理。"""

from typing import Any, Callable

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

FillLevelControls = Callable[..., None]


def is_preserved_summary_row(row: etree._Element, preserved_labels: tuple[str, ...]) -> bool:
    cells = row.xpath("./w:tc", namespaces=NS)
    label = "".join(cells[0].xpath(".//w:t/text()", namespaces=NS)).strip() if cells else ""
    return any(label.startswith(prefix) for prefix in preserved_labels)


def clear_unmapped_summary_cells(row: etree._Element, direct_tags: set[str]) -> None:
    cells = row.xpath("./w:tc", namespaces=NS)
    for cell in cells[1:]:
        cell_tags = set(cell.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
        if cell_tags.intersection(direct_tags):
            continue
        texts = cell.xpath(".//w:t", namespaces=NS)
        for text in texts:
            text.text = ""


def fill_preserved_summary_rows(parent: etree._Element, rows: list[etree._Element],
                                records: list[dict[str, Any]], table_no: str,
                                group: list[dict[str, Any]], source: tuple[str, str],
                                report_data: dict[str, Any], values: dict[str, Any],
                                layout: Any, warn: Callable[[str, str, str], None],
                                detail_key: str, fill_level_controls: FillLevelControls) -> None:
    """使用首条编组记录填写未复制的保留汇总行。"""
    labels = layout.preserved_row_labels(table_no)
    if not labels or not records:
        return
    data_rows = set(rows)
    for row in parent.xpath("./w:tr", namespaces=NS):
        if row in data_rows or not is_preserved_summary_row(row, labels):
            continue
        fill_level_controls(row.xpath("./w:tc", namespaces=NS), records[0], None, detail_key,
                             table_no, group, source, report_data, values, warn)
