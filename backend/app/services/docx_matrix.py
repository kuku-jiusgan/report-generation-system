import copy
from typing import Any

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def _set_cell_text(cell: etree._Element, value: Any) -> None:
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


def _fill_table(table: etree._Element, records: list[dict[str, Any]]) -> None:
    rows = table.xpath("./w:tr", namespaces=NS)
    for row in rows:
        for cell in row.xpath("./w:tc", namespaces=NS)[1:]:
            _set_cell_text(cell, "")
    if len(rows) < 3 or not records:
        return
    fields = ((0, "solutionName"), (1, "field2"), (2, "peakArea"),
              (6, "predictedPeakArea"), (7, "residual"))
    for row_index, field in fields:
        if row_index >= len(rows):
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        for index, record in enumerate(records[:max(0, len(cells) - 1)], start=1):
            _set_cell_text(cells[index], record.get(field, ""))
    labels = ((0, "溶液名称"), (1, "实际浓度（ng/ml）"), (2, "峰面积"))
    for row_index, label in labels:
        _set_cell_text(rows[row_index].xpath("./w:tc", namespaces=NS)[0], label)
    first = records[0]
    scalar_cells = ((4, 1, "regressionEquation"), (5, 1, "correlationCoefficient"),
                    (5, 3, "interceptRatio"), (8, 1, "residualChart"))
    for row_index, column_index, field in scalar_cells:
        if row_index >= len(rows):
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        if column_index < len(cells):
            _set_cell_text(cells[column_index], first.get(field, ""))


def fill_matrix_tables(document: etree._Element, table_no: str,
                       records: list[dict[str, Any]]) -> None:
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='repeat_{table_no.lower()}_row']", namespaces=NS
    )
    if not bookmarks:
        return
    table = bookmarks[0].getparent().getparent()
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
        _fill_table(target, group)
