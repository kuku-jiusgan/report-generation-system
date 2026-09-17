"""转置矩阵表的填充：一条记录占一列。

配置里的一行对应记录的一个字段（rowFields），整表只有一个取值的格子用 scalarCells。
横向分组不在这里——那属于"向下填充 + 向右分组"，见 docx_group_columns。
本模块只负责定位原型表并按版式写值，不含任何具体业务表号或字段名。
"""

import copy
from typing import Any, Callable

from lxml import etree

from .docx_table_cells import (
    NS, cell_width, grid_after, grid_span, set_cell_text, set_cell_width, set_grid_span,
    stretch_merged_row, sync_table_grid,
)
from .table_layout_rules import repeat_bookmark_name


Warn = Callable[[str, str, str], None]


def with_image_control_tags(layout: dict[str, Any],
                            mappings: list[dict[str, Any]]) -> dict[str, Any]:
    """把图片字段的内容控件标签注入矩阵固定单元格配置。"""
    result = copy.deepcopy(layout)
    by_field: dict[str, dict[str, Any] | None] = {}
    for item in mappings:
        if item.get("dataType") != "image" or not item.get("controlTag"):
            continue
        keys = [str(item.get("fieldCode") or "").split(".")[-1]]
        source_path = str(item.get("sourcePath") or "")
        if source_path:
            keys.append(source_path.rsplit(".", 1)[-1])
        for key in keys:
            if not key:
                continue
            if key in by_field and by_field[key] != item:
                by_field[key] = None
            elif key not in by_field:
                by_field[key] = item
    for entry in result.get("scalarCells") or []:
        if not isinstance(entry, dict):
            continue
        mapping = by_field.get(str(entry.get("field") or ""))
        if mapping is not None:
            entry["controlTag"] = mapping["controlTag"]
            entry["dataType"] = "image"
    return result


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
            set_cell_text(cells[index], record.get(str(entry.get("field", "")), ""))


def _fill_row_labels(rows: list[etree._Element], layout: dict[str, Any]) -> None:
    for entry in _layout_entries(layout, "rowLabels"):
        row_index = int(entry["row"]) - 1
        if row_index >= len(rows):
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        if cells:
            set_cell_text(cells[0], str(entry.get("text", "")))


def _fill_scalar_cells(rows: list[etree._Element], layout: dict[str, Any],
                       record: dict[str, Any]) -> None:
    """整表只有一个取值的单元格，例如回归方程、相关系数、残差图。"""
    for entry in _layout_entries(layout, "scalarCells"):
        row_index, column_index = int(entry["row"]) - 1, int(entry.get("column", 0) or 0) - 1
        if row_index >= len(rows) or column_index < 0:
            continue
        cells = rows[row_index].xpath("./w:tc", namespaces=NS)
        if column_index < len(cells):
            value = record.get(str(entry.get("field", "")), "")
            control_tag = str(entry.get("controlTag") or "")
            if entry.get("dataType") == "image":
                if not control_tag:
                    continue
                controls = cells[column_index].xpath(
                    ".//w:sdt[w:sdtPr/w:tag/@w:val=$tag]", namespaces=NS, tag=control_tag,
                )
                if controls:
                    set_cell_text(controls[0], value)
                # 图片字段只能交给图片内容控件处理，不能把 Data URL 降级成普通文字。
                continue
            set_cell_text(cells[column_index], value)


def _fill_table(table: etree._Element, records: list[dict[str, Any]],
                layout: dict[str, Any]) -> None:
    rows = table.xpath("./w:tr", namespaces=NS)
    for row in rows:
        for cell in row.xpath("./w:tc", namespaces=NS)[1:]:
            set_cell_text(cell, "")
    if not records:
        return
    _fill_row_fields(rows, layout, records)
    _fill_row_labels(rows, layout)
    _fill_scalar_cells(rows, layout, records[0])


def _column_policy(layout: dict[str, Any]) -> dict[str, Any] | None:
    policy = layout.get("columnPolicy")
    if policy is None:
        return None
    if not isinstance(policy, dict):
        raise ValueError("矩阵横向扩展的 columnPolicy 必须是 JSON 对象")
    if str(policy.get("mode") or "DATA_LENGTH") != "DATA_LENGTH":
        raise ValueError("矩阵横向扩展的 mode 只能是 DATA_LENGTH")
    if str(policy.get("overflow") or "") != "HORIZONTAL":
        raise ValueError("矩阵横向扩展的 overflow 只能是 HORIZONTAL")
    if not _layout_entries(layout, "rowFields"):
        raise ValueError("启用矩阵横向扩展时，rowFields 不能为空")
    return policy


def _horizontal_count(table: etree._Element, records: list[dict[str, Any]],
                      policy: dict[str, Any]) -> int:
    first_row = table.xpath("./w:tr[1]", namespaces=NS)
    prototype = max(0, len(first_row[0].xpath("./w:tc", namespaces=NS)) - 1) if first_row else 0
    try:
        minimum = max(1, int(policy.get("minColumns", prototype or 1)))
    except (TypeError, ValueError):
        raise ValueError("矩阵横向扩展的 minColumns 必须是正整数")
    return max(prototype, minimum, len(records))


def _horizontal_widths(table: etree._Element, target: int, policy: dict[str, Any]) -> list[int]:
    rows = table.xpath("./w:tr", namespaces=NS)
    if not rows:
        return []
    data_cells = rows[0].xpath("./w:tc", namespaces=NS)[1:]
    prototype = [cell_width(cell) for cell in data_cells] or [1]
    try:
        width_mode = str(policy.get("widthMode") or "PROTOTYPE")
        if width_mode == "PRESERVE_TOTAL":
            total = sum(prototype)
            base, remainder = divmod(total, target)
            return [max(1, base + (1 if index < remainder else 0)) for index in range(target)]
        if width_mode != "PROTOTYPE":
            raise ValueError("矩阵横向扩展的 widthMode 只能是 PROTOTYPE 或 PRESERVE_TOTAL")
    except (TypeError, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError("矩阵横向扩展的 widthMode 配置无效") from error
    return [prototype[index % len(prototype)] for index in range(target)]


def _expand_row(row: etree._Element, target: int, widths: list[int]) -> None:
    cells = row.xpath("./w:tc", namespaces=NS)
    if len(cells) < 2:
        return
    data_cells = cells[1:]
    while len(data_cells) < target:
        clone = copy.deepcopy(data_cells[-1])
        for bookmark in clone.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
            bookmark.getparent().remove(bookmark)
        row.append(clone)
        data_cells.append(clone)
    for cell, width in zip(data_cells[:target], widths):
        set_cell_width(cell, width)
        set_grid_span(cell, 1)
    for cell in data_cells[target:]:
        row.remove(cell)


def _sync_horizontal_grid(table: etree._Element, rows: list[etree._Element],
                          target: int, widths: list[int]) -> None:
    grid = table.find("{" + NS["w"] + "}tblGrid")
    original = []
    if grid is not None:
        for column in grid:
            try:
                original.append(max(1, int(column.get("{" + NS["w"] + "}w") or 1)))
            except (TypeError, ValueError):
                original.append(1)
    leading = original[:1] or [cell_width(rows[0].xpath("./w:tc", namespaces=NS)[0])]
    trailing = original[1 + max(0, len(rows[0].xpath("./w:tc", namespaces=NS)) - 1):] if original else []
    sync_table_grid(table, leading + widths + trailing)
    total = len(leading) + len(widths) + len(trailing)
    for row in rows:
        used = sum(grid_span(cell) for cell in row.xpath("./w:tc", namespaces=NS)) + grid_after(row)
        if used != total:
            stretch_merged_row(row, total)


def _fill_horizontal_table(table: etree._Element, records: list[dict[str, Any]],
                           layout: dict[str, Any], policy: dict[str, Any]) -> None:
    rows = table.xpath("./w:tr", namespaces=NS)
    target = _horizontal_count(table, records, policy)
    widths = _horizontal_widths(table, target, policy)
    row_fields = _layout_entries(layout, "rowFields")
    repeated_rows = {int(entry["row"]) - 1 for entry in row_fields}
    for row_index, row in enumerate(rows):
        if row_index in repeated_rows:
            _expand_row(row, target, widths)
        elif row.xpath("./w:tc", namespaces=NS):
            # Fixed/statistical rows keep their cells and only absorb the new grid width.
            continue
    _sync_horizontal_grid(table, rows, target, widths)
    for row_index in repeated_rows:
        if row_index < len(rows):
            for cell in rows[row_index].xpath("./w:tc", namespaces=NS)[1:]:
                set_cell_text(cell, "")
    if records:
        _fill_row_fields(rows, layout, records)
        _fill_row_labels(rows, layout)
        _fill_scalar_cells(rows, layout, records[0])


def fill_matrix_table(table: etree._Element, records: list[dict[str, Any]],
                      layout: dict[str, Any]) -> None:
    """Fill one already-resolved prototype table without cloning it."""
    policy = _column_policy(layout)
    if policy:
        _fill_horizontal_table(table, records, layout, policy)
    else:
        _fill_table(table, records, layout)


def fill_matrix_tables(document: etree._Element, table_no: str, records: list[dict[str, Any]],
                       layout: dict[str, Any], warn: Warn, physical_index: int = 0) -> None:
    bookmarks = document.xpath(
        f".//w:bookmarkStart[@w:name='{repeat_bookmark_name(table_no)}']", namespaces=NS
    )
    if bookmarks:
        table = bookmarks[0].xpath("ancestor::w:tbl[1]", namespaces=NS)[0]
    else:
        tables = document.xpath(".//w:tbl", namespaces=NS)
        if physical_index < 1 or physical_index > len(tables):
            warn("MATRIX_TABLE_NOT_FOUND", table_no,
                 "找不到该矩阵表的原型表：字段没有绑定到 Word 表格，表格规则里也没有配置"
                 "Word 正文表格序号；请在模板设计器中补齐其中一项。")
            return
        table = tables[physical_index - 1]
    policy = _column_policy(layout)
    if policy:
        _fill_horizontal_table(table, records, layout, policy)
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
