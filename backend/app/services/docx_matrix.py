import copy
from typing import Any

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"

def _cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS)).strip()


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


def _display_layout_value(value: Any, configuration: dict[str, Any]) -> Any:
    decimal_places = configuration.get("decimalPlaces")
    if value in (None, "") or not isinstance(decimal_places, int):
        return value
    try:
        return f"{float(value):.{decimal_places}f}"
    except (TypeError, ValueError):
        return value


def _layout_entries(layout: dict[str, Any], key: str) -> list[dict[str, Any]]:
    entries = layout.get(key) or []
    return [item for item in entries if isinstance(item, dict) and int(item.get("row", 0) or 0) > 0]


def _fill_row_fields(rows: list[etree._Element], layout: dict[str, Any],
                     records: list[dict[str, Any]]) -> None:
    """每条记录占一列：配置里的一行对应记录的一个字段。"""
    for entry in _layout_entries(layout, "rowFields"):
        row_index = int(entry["row"]) - 1
        if row_index >= len(rows):
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        for index, record in enumerate(records[:max(0, len(cells) - 1)], start=1):
            _set_cell_text(cells[index], record.get(str(entry.get("field", "")), ""))


def _fill_row_labels(rows: list[etree._Element], layout: dict[str, Any]) -> None:
    for entry in _layout_entries(layout, "rowLabels"):
        row_index = int(entry["row"]) - 1
        if row_index >= len(rows):
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        if cells:
            _set_cell_text(cells[0], str(entry.get("text", "")))


def _fill_scalar_cells(rows: list[etree._Element], layout: dict[str, Any],
                       record: dict[str, Any]) -> None:
    """整表只有一个取值的单元格，例如回归方程、相关系数、残差图。"""
    for entry in _layout_entries(layout, "scalarCells"):
        row_index, column_index = int(entry["row"]) - 1, int(entry.get("column", 0) or 0) - 1
        if row_index >= len(rows) or column_index < 0:
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        if column_index < len(cells):
            _set_cell_text(cells[column_index], record.get(str(entry.get("field", "")), ""))


def _fill_table(table: etree._Element, records: list[dict[str, Any]],
                layout: dict[str, Any]) -> None:
    rows = table.xpath("./w:tr", namespaces=NS)
    for row in rows:
        for cell in row.xpath("./w:tc", namespaces=NS)[1:]:
            _set_cell_text(cell, "")
    if not records:
        return
    _fill_row_fields(rows, layout, records)
    _fill_row_labels(rows, layout)
    _fill_scalar_cells(rows, layout, records[0])


def fill_matrix_table(table: etree._Element, records: list[dict[str, Any]],
                      layout: dict[str, Any]) -> None:
    """Fill one already-resolved prototype table without cloning it."""
    if layout.get("columnGroups"):
        _fill_horizontal_groups(table, records, layout)
        return
    _fill_table(table, records, layout)

def _fill_horizontal_groups(table: etree._Element, records: list[dict[str, Any]], layout: dict[str, Any]) -> None:
    rows = table.xpath("./w:tr", namespaces=NS)
    if not rows:
        return
    header_rows = int(layout.get("headerRows", 2))
    data_layout = layout.get("dataRows") or {}
    data_start = int(data_layout.get("start", header_rows + 1)) - 1
    data_end = int(data_layout.get("end", len(rows))) - 1
    group = (layout.get("columnGroups") or [{}])[0]
    columns = group.get("columns") or []
    header_field = str(group.get("headerField") or "impurityName")
    sequence_field = str(data_layout.get("labelField") or "sequence")
    sort_field = str(data_layout.get("sortField") or sequence_field)
    normalized = [dict(item) for item in records if isinstance(item, dict)]
    impurities = list(dict.fromkeys(
        str(item.get(header_field) or "").strip() for item in normalized if item.get(header_field)
    ))
    if not impurities or len(rows) < header_rows or not columns:
        return
    width = len(columns)

    def resize(row: etree._Element, target: int) -> list[etree._Element]:
        cells = row.xpath("./w:tc", namespaces=NS)
        while len(cells) > target:
            row.remove(cells.pop())
        while len(cells) < target:
            source = cells[-1] if len(cells) > 1 else cells[0]
            clone = copy.deepcopy(source)
            row.append(clone)
            cells.append(clone)
        return cells

    first_cells = resize(rows[0], 1 + len(impurities))
    second_cells = resize(rows[1], 1 + len(impurities) * width)
    for index, name in enumerate(impurities):
        _set_cell_text(first_cells[index + 1], name)
        for offset, column in enumerate(columns):
            _set_cell_text(second_cells[1 + index * width + offset], column.get("label", ""))

    by_sequence: dict[str, dict[str, dict[str, Any]]] = {}
    sequence_order: dict[str, Any] = {}
    for item in normalized:
        sequence = str(item.get(sequence_field) or "").strip()
        impurity = str(item.get(header_field) or "").strip()
        if sequence and impurity:
            by_sequence.setdefault(sequence, {})[impurity] = item
            sequence_order.setdefault(sequence, item.get(sort_field))

    def sequence_key(value: str) -> tuple[bool, Any]:
        order = sequence_order.get(value, value)
        try:
            return False, float(order)
        except (TypeError, ValueError):
            return True, str(order)

    ordered_sequences = sorted(by_sequence, key=sequence_key)
    data_rows = rows[data_start:min(data_end + 1, len(rows))]
    while len(data_rows) < len(ordered_sequences) and data_rows:
        prototype = data_rows[-1]
        clone = copy.deepcopy(prototype)
        prototype.getparent().insert(prototype.getparent().index(prototype) + 1, clone)
        data_rows.append(clone)
    for row, sequence in zip(data_rows, ordered_sequences):
        cells = resize(row, 1 + len(impurities) * width)
        _set_cell_text(cells[0], sequence)
        for index, name in enumerate(impurities):
            item = by_sequence[sequence].get(name, {})
            for offset, column in enumerate(columns):
                value = item.get(str(column.get("field") or ""), "")
                _set_cell_text(cells[1 + index * width + offset], _display_layout_value(value, column))

    for summary in layout.get("summaryRows") or []:
        if not isinstance(summary, dict):
            continue
        row_index = int(summary.get("row", 0)) - 1
        if row_index < 0 or row_index >= len(rows):
            continue
        cells = resize(rows[row_index], 1 + len(impurities) * width)
        _set_cell_text(cells[0], summary.get("label", ""))
        fields = summary.get("fields") or []
        for index, name in enumerate(impurities):
            representative = next((item for item in normalized if str(item.get(header_field) or "").strip() == name), {})
            for offset, field in enumerate(fields):
                _set_cell_text(cells[1 + index * width + offset], representative.get(str(field), ""))

    conclusion = layout.get("conclusionRow") or {}
    conclusion_index = int(conclusion.get("row", 0)) - 1
    if 0 <= conclusion_index < len(rows):
        cells = rows[conclusion_index].xpath("./w:tc", namespaces=NS)
        if len(cells) > 1:
            _set_cell_text(cells[0], conclusion.get("label", "结论"))
            field = str(conclusion.get("field") or "")
            value = next((item.get(field) for item in normalized if item.get(field) not in (None, "")), "")
            if value in (None, "") and conclusion.get("template"):
                retention_values = [str(next((item.get("retentionTimeRsd") for item in normalized if str(item.get(header_field) or "").strip() == name), "")) for name in impurities]
                peak_suffix = str(conclusion.get("peakAreaRsdSuffix") or "")
                values = {"recordCount": len(ordered_sequences),
                          "impurityNames": "、".join(impurities),
                          "retentionTimeRsds": retention_values[0] if retention_values and len(set(retention_values)) == 1 else "、".join(retention_values),
                          "peakAreaRsds": "、".join(f"{next((item.get('peakAreaRsd') for item in normalized if str(item.get(header_field) or '').strip() == name), '')}{peak_suffix}" for name in impurities)}
                try:
                    value = str(conclusion["template"]).format(**values)
                except (KeyError, ValueError):
                    value = ""
            _set_cell_text(cells[1], value)


def fill_matrix_tables(document: etree._Element, table_no: str,
                       records: list[dict[str, Any]], layout: dict[str, Any],
                       physical_index: int = 0) -> None:
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='repeat_{table_no.lower()}_row']", namespaces=NS
    )
    if bookmarks:
        table = bookmarks[0].getparent().getparent()
    else:
        tables = document.xpath(".//w:tbl", namespaces=NS)
        if physical_index < 1 or physical_index > len(tables):
            return
        table = tables[physical_index - 1]
    if layout.get("columnGroups"):
        fill_matrix_table(table, records, layout)
        return
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
        _fill_table(target, group, layout)
