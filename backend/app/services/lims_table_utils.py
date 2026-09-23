import re
from typing import Any

from lxml import html


def clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def cell_value(cell: html.HtmlElement) -> str:
    text = clean_cell(cell.text_content())
    if text:
        return text
    image_urls = [str(value).strip() for value in cell.xpath(".//img/@src") if str(value).strip()]
    return "；".join(dict.fromkeys(image_urls))


def column_value(row: list[str], column: int | None) -> str:
    return clean_cell(row[column]) if column is not None and column < len(row) else ""


def _grid(table: html.HtmlElement) -> tuple[list[list[str]], list[list[html.HtmlElement | None]]]:
    grid: list[list[str]] = []
    cells: list[list[html.HtmlElement | None]] = []
    spans: dict[int, tuple[int, str, html.HtmlElement]] = {}
    for tr in table.xpath("./thead/tr|./tbody/tr|./tfoot/tr|./tr"):
        row: list[str] = []
        cell_row: list[html.HtmlElement | None] = []
        column = 0

        def consume_spans() -> None:
            nonlocal column
            while column in spans:
                remaining, text, cell = spans[column]
                row.append(text)
                cell_row.append(cell)
                if remaining <= 1:
                    del spans[column]
                else:
                    spans[column] = (remaining - 1, text, cell)
                column += 1

        consume_spans()
        for cell in tr.xpath("./th|./td"):
            consume_spans()
            text = cell_value(cell)
            colspan = max(1, int(cell.get("colspan") or 1))
            rowspan = max(1, int(cell.get("rowspan") or 1))
            for _ in range(colspan):
                row.append(text)
                cell_row.append(cell)
                if rowspan > 1:
                    spans[column] = (rowspan - 1, text, cell)
                column += 1
        consume_spans()
        if any(row):
            grid.append(row)
            cells.append(cell_row)
    width = max((len(row) for row in grid), default=0)
    return ([row + [""] * (width - len(row)) for row in grid],
            [row + [None] * (width - len(row)) for row in cells])


def table_grid(table: html.HtmlElement) -> list[list[str]]:
    """Expand an HTML table into a rectangular grid, including merged cells."""
    return _grid(table)[0]


def table_cell_grid(table: html.HtmlElement) -> list[list[html.HtmlElement | None]]:
    """Return source cells at the same row/column positions as table_grid."""
    return _grid(table)[1]
