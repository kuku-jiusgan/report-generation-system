"""转置矩阵表：一条记录占一列。横向分组的用例见 test_docx_group_columns.py。"""

from lxml import etree
from zipfile import ZipInfo

from backend.app.services.docx_matrix import fill_matrix_table, fill_matrix_tables
from backend.app.services.docx_images import embed_image_controls


WARNINGS: list[tuple[str, str, str]] = []


def _warn(code: str, table_no: str, message: str) -> None:
    WARNINGS.append((code, table_no, message))


def _fill_matrix_table(document, table_no, records, layout) -> None:
    fill_matrix_tables(document, table_no, records, layout, _warn)

LINEARITY_LAYOUT = {
    "rowFields": [
        {"row": 1, "field": "solutionName"}, {"row": 2, "field": "field2"},
        {"row": 3, "field": "peakArea"}, {"row": 5, "field": "regressionEquation"},
        {"row": 6, "field": "correlationCoefficient"}, {"row": 7, "field": "predictedPeakArea"},
        {"row": 8, "field": "residual"},
    ],
    "scalarCells": [{"row": 6, "column": 4, "field": "interceptRatio"},
                    {"row": 9, "column": 2, "field": "residualChart",
                     "dataType": "image", "controlTag": "repeat.t20.residualChart"}],
}


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _matrix_document(row_count: int = 9) -> etree._Element:
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    for row_index in range(row_count):
        row = etree.SubElement(table, W + "tr")
        if row_index == 0:
            etree.SubElement(row, W + "bookmarkStart", {W + "name": "repeat_t20_row"})
        for column_index in range(6):
            cell = etree.SubElement(row, W + "tc")
            if row_index == 8 and column_index == 1:
                sdt = etree.SubElement(cell, W + "sdt")
                props = etree.SubElement(sdt, W + "sdtPr")
                etree.SubElement(props, W + "tag", {W + "val": "repeat.t20.residualChart"})
                content = etree.SubElement(sdt, W + "sdtContent")
                paragraph = etree.SubElement(content, W + "p")
                run = etree.SubElement(paragraph, W + "r")
                etree.SubElement(run, W + "t")
                continue
            paragraph = etree.SubElement(cell, W + "p")
            run = etree.SubElement(paragraph, W + "r")
            etree.SubElement(run, W + "t")
    return document


def _cell_text(document: etree._Element, row: int, column: int) -> str:
    cell = document.xpath(".//w:tbl/w:tr", namespaces=NS)[row].xpath("./w:tc", namespaces=NS)[column]
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS))


def _control_text(document: etree._Element, row: int, column: int, tag: str) -> str:
    cell = document.xpath(".//w:tbl/w:tr", namespaces=NS)[row].xpath("./w:tc", namespaces=NS)[column]
    return "".join(cell.xpath(
        ".//w:sdt[w:sdtPr/w:tag/@w:val=$tag]//w:t/text()", namespaces=NS, tag=tag,
    ))


def _cell_text_outside_controls(document: etree._Element, row: int, column: int) -> str:
    cell = document.xpath(".//w:tbl/w:tr", namespaces=NS)[row].xpath("./w:tc", namespaces=NS)[column]
    return "".join(cell.xpath(
        ".//w:t[not(ancestor::w:sdt)]/text()", namespaces=NS,
    ))


def test_linearity_matrix_fills_detail_and_statistic_rows() -> None:
    document = _matrix_document(row_count=10)
    records = [{
        "solutionName": "C1", "field2": 2.57, "peakArea": 14889,
        "regressionEquation": "y = 5886.7751x + 969.9591",
        "correlationCoefficient": 0.999918, "interceptRatio": 0.64,
        "predictedPeakArea": 14944, "residual": -55, "residualChart": "data:image/png;base64,AAA=",
    }]

    _fill_matrix_table(document, "T20", records, LINEARITY_LAYOUT)

    assert _cell_text(document, 0, 1) == "C1"
    assert _cell_text(document, 1, 1) == "2.57"
    assert _cell_text(document, 2, 1) == "14889"
    assert _cell_text(document, 4, 1) == "y = 5886.7751x + 969.9591"
    assert _cell_text(document, 5, 1) == "0.999918"
    assert _cell_text(document, 5, 3) == "0.64"
    assert _cell_text(document, 6, 1) == "14944"
    assert _cell_text(document, 7, 1) == "-55"
    assert _control_text(document, 8, 1, "repeat.t20.residualChart") == "data:image/png;base64,AAA="
    assert _cell_text_outside_controls(document, 8, 1) == ""


def test_missing_matrix_image_removes_template_picture() -> None:
    document = _matrix_document()
    control = document.xpath(
        ".//w:sdt[w:sdtPr/w:tag/@w:val='repeat.t20.residualChart']", namespaces=NS,
    )[0]
    etree.SubElement(control.find(".//" + W + "r"), W + "drawing")

    _fill_matrix_table(document, "T20", [{"solutionName": "C1"}], LINEARITY_LAYOUT)

    assert _control_text(document, 8, 1, "repeat.t20.residualChart") == "-"
    assert not control.xpath(".//w:drawing", namespaces=NS)


def test_linearity_matrix_clones_one_table_per_five_points() -> None:
    document = _matrix_document()
    records = [{"solutionName": f"C{index % 5 + 1}"} for index in range(10)]

    _fill_matrix_table(document, "T20", records, LINEARITY_LAYOUT)

    tables = document.xpath(".//w:tbl", namespaces=NS)
    assert len(tables) == 2
    assert "".join(tables[0].xpath("./w:tr[1]/w:tc[2]//w:t/text()", namespaces=NS)) == "C1"
    assert "".join(tables[1].xpath("./w:tr[1]/w:tc[2]//w:t/text()", namespaces=NS)) == "C1"


def test_horizontal_matrix_expands_configured_rows_and_preserves_fixed_rows() -> None:
    document = _matrix_document(row_count=10)
    records = [{
        "solutionName": f"C{index}", "field2": index * 2, "peakArea": index * 100,
        "regressionEquation": "y = 2x", "correlationCoefficient": 0.99,
    } for index in range(1, 8)]
    layout = {
        "rowFields": [
            {"row": 1, "field": "solutionName"},
            {"row": 2, "field": "field2"},
            {"row": 3, "field": "peakArea"},
        ],
        "scalarCells": [
            {"row": 4, "column": 2, "field": "regressionEquation"},
            {"row": 6, "column": 2, "field": "correlationCoefficient"},
        ],
        "columnPolicy": {
            "mode": "DATA_LENGTH", "minColumns": 5,
            "overflow": "HORIZONTAL", "widthMode": "PROTOTYPE",
        },
    }

    _fill_matrix_table(document, "T20", records, layout)

    tables = document.xpath(".//w:tbl", namespaces=NS)
    assert len(tables) == 1
    assert [_cell_text(document, 0, index) for index in range(1, 8)] == [f"C{index}" for index in range(1, 8)]
    assert [_cell_text(document, 1, index) for index in range(1, 8)] == [str(index * 2) for index in range(1, 8)]
    assert [_cell_text(document, 2, index) for index in range(1, 8)] == [str(index * 100) for index in range(1, 8)]
    assert _cell_text(document, 3, 1) == "y = 2x"
    assert len(document.xpath(".//w:tbl/w:tr[1]/w:tc", namespaces=NS)) == 8
    assert _cell_text(document, 5, 1) == "0.99"


def test_horizontal_matrix_preserves_trailing_grid_after_column() -> None:
    document = _matrix_document(row_count=2)
    table = document.xpath(".//w:tbl", namespaces=NS)[0]
    grid = etree.Element(W + "tblGrid")
    table.insert(0, grid)
    for width in (1952, 6561, 9):
        etree.SubElement(grid, W + "gridCol", {W + "w": str(width)})
    for row in table.xpath("./w:tr", namespaces=NS):
        for cell in row.xpath("./w:tc", namespaces=NS)[2:]:
            row.remove(cell)
        properties = etree.Element(W + "trPr")
        etree.SubElement(properties, W + "gridAfter", {W + "val": "1"})
        row.insert(0, properties)
        for cell, width in zip(row.xpath("./w:tc", namespaces=NS), (1952, 6561)):
            cell_properties = etree.Element(W + "tcPr")
            etree.SubElement(cell_properties, W + "tcW", {W + "w": str(width), W + "type": "dxa"})
            cell.insert(0, cell_properties)
    layout = {
        "rowFields": [{"row": 1, "field": "name"}],
        "columnPolicy": {
            "mode": "DATA_LENGTH", "overflow": "HORIZONTAL",
            "minColumns": 1, "widthMode": "PRESERVE_TOTAL",
        },
    }

    _fill_matrix_table(document, "T20", [{"name": name} for name in ("A", "B", "C")], layout)

    widths = [int(width) for width in table.xpath("./w:tblGrid/w:gridCol/@w:w", namespaces=NS)]
    assert widths == [1952, 2187, 2187, 2187, 9]
    assert sum(widths) == 1952 + 6561 + 9
    for row in table.xpath("./w:tr", namespaces=NS):
        spans = row.xpath("./w:tc/w:tcPr/w:gridSpan/@w:val", namespaces=NS)
        occupied = sum(int(span) for span in spans) + len(row.xpath("./w:tc[not(w:tcPr/w:gridSpan)]", namespaces=NS))
        assert occupied + 1 == len(widths)


def test_horizontal_matrix_replaces_merged_prototype_grid_with_five_equal_columns() -> None:
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    table = etree.SubElement(etree.SubElement(document, W + "body"), W + "tbl")
    grid = etree.SubElement(table, W + "tblGrid")
    for width in (2009, 2394, 1984, 2135):
        etree.SubElement(grid, W + "gridCol", {W + "w": str(width)})
    for cells in (((2009, 1), (6513, 3)), ((2009, 1), (6513, 3)),
                  ((2009, 1), (2394, 1), (1984, 1), (2135, 1))):
        row = etree.SubElement(table, W + "tr")
        for width, span in cells:
            cell = etree.SubElement(row, W + "tc")
            properties = etree.SubElement(cell, W + "tcPr")
            etree.SubElement(properties, W + "tcW", {W + "w": str(width), W + "type": "dxa"})
            etree.SubElement(properties, W + "gridSpan", {W + "val": str(span)})
            etree.SubElement(etree.SubElement(etree.SubElement(cell, W + "p"), W + "r"), W + "t")
    layout = {
        "rowFields": [{"row": 1, "field": "name"}],
        "fixedRowSpans": {"3": [1, 2, 2, 1]},
        "columnPolicy": {"mode": "DATA_LENGTH", "overflow": "HORIZONTAL",
                         "minColumns": 5, "widthMode": "PRESERVE_TOTAL"},
    }

    fill_matrix_table(table, [{"name": f"C{i}"} for i in range(1, 6)], layout)

    widths = [int(value) for value in table.xpath("./w:tblGrid/w:gridCol/@w:w", namespaces=NS)]
    assert len(widths) == 6
    assert widths[0] == 2009
    assert sum(widths) == 8522
    assert max(widths[1:]) - min(widths[1:]) <= 1
    rows = table.xpath("./w:tr", namespaces=NS)
    assert [len(row.xpath("./w:tc", namespaces=NS)) for row in rows] == [6, 2, 4]
    assert rows[1].xpath("./w:tc/w:tcPr/w:gridSpan/@w:val", namespaces=NS) == ["1", "5"]
    assert rows[2].xpath("./w:tc/w:tcPr/w:gridSpan/@w:val", namespaces=NS) == ["1", "2", "2", "1"]
    assert [int(value) for value in rows[2].xpath("./w:tc/w:tcPr/w:tcW/@w:w", namespaces=NS)] == [
        widths[0], widths[1] + widths[2], widths[3] + widths[4], widths[5],
    ]


def test_matrix_image_control_is_embedded_as_drawing() -> None:
    image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    cases = [("", ("1892300", "977900")),
             ("IMAGE_FIT_WIDE", ("4860000", "2610000"))]
    for fill_rule, expected_extent in cases:
        document = _matrix_document(row_count=10)
        _fill_matrix_table(document, "T20", [{"residualChart": image}], LINEARITY_LAYOUT)
        content_types = etree.fromstring(b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        rels = etree.fromstring(b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        parts = {
            "[Content_Types].xml": (ZipInfo("[Content_Types].xml"), etree.tostring(content_types)),
            "word/_rels/document.xml.rels": (ZipInfo("word/_rels/document.xml.rels"), etree.tostring(rels)),
        }
        embed_image_controls(parts, {"word/document.xml": document}, [{
            "dataType": "image", "controlTag": "repeat.t20.residualChart", "fillRule": fill_rule,
        }])
        cell = document.xpath(".//w:tbl/w:tr", namespaces=NS)[8].xpath("./w:tc", namespaces=NS)[1]
        assert cell.xpath(".//w:sdt[w:sdtPr/w:tag/@w:val='repeat.t20.residualChart']//w:drawing", namespaces=NS)
        extent = cell.xpath(".//*[local-name()='extent' and namespace-uri()='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing']")[0]
        assert (extent.get("cx"), extent.get("cy")) == expected_extent
        assert "word/media/" in "".join(parts)
        assert "rId1" in etree.tostring(etree.fromstring(parts["word/_rels/document.xml.rels"][1])).decode()


def test_matrix_image_preserves_template_size_and_centering() -> None:
    document = _matrix_document(row_count=10)
    control = document.xpath(
        ".//w:sdt[w:sdtPr/w:tag/@w:val='repeat.t20.residualChart']", namespaces=NS,
    )[0]
    paragraph = control.find(f"{W}sdtContent/{W}p")
    properties = etree.Element(W + "pPr")
    etree.SubElement(properties, W + "jc", {W + "val": "center"})
    paragraph.insert(0, properties)
    run = paragraph.find(W + "r")
    drawing = etree.SubElement(run, W + "drawing")
    inline = etree.SubElement(
        drawing, "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline",
    )
    etree.SubElement(
        inline, "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent",
        cx="3520800", cy="2246400",
    )
    graphic = etree.SubElement(
        inline, "{http://schemas.openxmlformats.org/drawingml/2006/main}graphic",
    )
    blip = etree.SubElement(
        graphic, "{http://schemas.openxmlformats.org/drawingml/2006/main}blip",
    )
    blip.set(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", "rIdTemplate",
    )

    records = [{"residualChart": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="}]
    _fill_matrix_table(document, "T20", records, LINEARITY_LAYOUT)
    content_types = etree.fromstring(b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    rels = etree.fromstring(b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
    parts = {
        "[Content_Types].xml": (ZipInfo("[Content_Types].xml"), etree.tostring(content_types)),
        "word/_rels/document.xml.rels": (ZipInfo("word/_rels/document.xml.rels"), etree.tostring(rels)),
    }

    embed_image_controls(parts, {"word/document.xml": document}, [{
        "dataType": "image", "controlTag": "repeat.t20.residualChart", "fillRule": "IMAGE_FIT_WIDE",
    }])

    assert control.xpath("string(.//w:pPr/w:jc/@w:val)", namespaces=NS) == "center"
    extent = control.xpath(
        ".//*[local-name()='extent' and namespace-uri()='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing']",
    )[0]
    assert (extent.get("cx"), extent.get("cy")) == ("3520800", "2246400")
    assert control.xpath(
        "string(.//*[local-name()='blip']/@*[local-name()='embed'])",
    ) == "rId1"
    assert not control.xpath(".//w:t", namespaces=NS)
