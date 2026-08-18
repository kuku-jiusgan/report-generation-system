from lxml import etree

from backend.app.services.docx_matrix import fill_matrix_tables as _fill_matrix_table


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _matrix_document() -> etree._Element:
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    for row_index in range(9):
        row = etree.SubElement(table, W + "tr")
        if row_index == 0:
            etree.SubElement(row, W + "bookmarkStart", {W + "name": "repeat_t20_row"})
        for _ in range(6):
            cell = etree.SubElement(row, W + "tc")
            paragraph = etree.SubElement(cell, W + "p")
            run = etree.SubElement(paragraph, W + "r")
            etree.SubElement(run, W + "t")
    return document


def _cell_text(document: etree._Element, row: int, column: int) -> str:
    cell = document.xpath(".//w:tbl/w:tr", namespaces=NS)[row].xpath("./w:tc", namespaces=NS)[column]
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS))


def test_linearity_matrix_fills_detail_and_statistic_rows() -> None:
    document = _matrix_document()
    records = [{
        "solutionName": "C1", "field2": 2.57, "peakArea": 14889,
        "regressionEquation": "y = 5886.7751x + 969.9591",
        "correlationCoefficient": 0.999918, "interceptRatio": 0.64,
        "predictedPeakArea": 14944, "residual": -55, "residualChart": "data:image/png;base64,AAA=",
    }]

    _fill_matrix_table(document, "T20", records)

    assert _cell_text(document, 0, 1) == "C1"
    assert _cell_text(document, 1, 1) == "2.57"
    assert _cell_text(document, 2, 1) == "14889"
    assert _cell_text(document, 4, 1) == "y = 5886.7751x + 969.9591"
    assert _cell_text(document, 5, 1) == "0.999918"
    assert _cell_text(document, 5, 3) == "0.64"
    assert _cell_text(document, 6, 1) == "14944"
    assert _cell_text(document, 7, 1) == "-55"
    assert _cell_text(document, 8, 1) == "data:image/png;base64,AAA="


def test_linearity_matrix_clones_one_table_per_five_points() -> None:
    document = _matrix_document()
    records = [{"solutionName": f"C{index % 5 + 1}"} for index in range(10)]

    _fill_matrix_table(document, "T20", records)

    tables = document.xpath(".//w:tbl", namespaces=NS)
    assert len(tables) == 2
    assert "".join(tables[0].xpath("./w:tr[1]/w:tc[2]//w:t/text()", namespaces=NS)) == "C1"
    assert "".join(tables[1].xpath("./w:tr[1]/w:tc[2]//w:t/text()", namespaces=NS)) == "C1"
