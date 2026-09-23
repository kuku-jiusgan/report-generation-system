"""整表复制中的嵌套矩阵必须遵循标准编组路径与 Word 控件绑定。"""

import pytest
from lxml import etree

from backend.app.services.docx_repeat_rows import fill_repeat_rows
from backend.app.services.table_layout_rules import TableLayoutRules


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _cell(row: etree._Element, text: str, tag: str = "", grid_span: int = 0) -> None:
    cell = etree.SubElement(row, W + "tc")
    if grid_span:
        properties = etree.SubElement(cell, W + "tcPr")
        etree.SubElement(properties, W + "gridSpan", {W + "val": str(grid_span)})
    owner = cell
    if tag:
        control = etree.SubElement(cell, W + "sdt")
        properties = etree.SubElement(control, W + "sdtPr")
        etree.SubElement(properties, W + "tag", {W + "val": tag})
        owner = etree.SubElement(control, W + "sdtContent")
    paragraph = etree.SubElement(owner, W + "p")
    run = etree.SubElement(paragraph, W + "r")
    etree.SubElement(run, W + "t").text = text


def _document() -> etree._Element:
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    rows = [
        ("溶液名称", "detail.name"),
        ("实际浓度", "detail.concentration"),
        ("峰面积", "detail.area"),
        ("预测峰面积", "detail.predicted"),
        ("回归方程", "summary.regression"),
        ("结论", "group.conclusion"),
    ]
    for index, (label, tag) in enumerate(rows):
        row = etree.SubElement(table, W + "tr")
        if index == 0:
            etree.SubElement(row, W + "bookmarkStart", {
                W + "id": "1", W + "name": "repeat_t99_row",
            })
        _cell(row, label)
        _cell(row, "模板值", tag, 5)
    return document


def _mappings() -> list[dict]:
    base = {
        "enabled": True, "repeatType": "ROW", "tableNo": "T99",
        "groupItemPath": "$.results[*]", "contentBlockKind": "REPEATING_TABLE",
    }
    return [
        {**base, "controlTag": "group.name", "wordLabel": "杂质名称",
         "fieldCode": "result.name", "sourcePath": "$.results[*].field_047"},
        {**base, "controlTag": "detail.name", "wordLabel": "溶液名称",
         "fieldCode": "result.solution", "sourcePath": "$.results[*].injections[*].field_021"},
        {**base, "controlTag": "detail.concentration", "wordLabel": "实际浓度",
         "fieldCode": "result.concentration", "sourcePath": "$.results[*].injections[*].field_022"},
        {**base, "controlTag": "detail.area", "wordLabel": "峰面积",
         "fieldCode": "result.area", "sourcePath": "$.results[*].injections[*].field_023"},
        {**base, "controlTag": "detail.predicted", "wordLabel": "预测峰面积",
         "fieldCode": "result.predicted", "sourcePath": "$.results[*].injections[*].field_027"},
        {**base, "controlTag": "summary.regression", "wordLabel": "回归方程",
         "fieldCode": "result.regression", "sourcePath": "$.results[*].summary.field_024"},
        {**base, "controlTag": "group.conclusion", "wordLabel": "结论",
         "fieldCode": "result.conclusion", "sourcePath": "$.results[*].field_012"},
    ]


def _rule() -> TableLayoutRules:
    return TableLayoutRules([{
        "tableNo": "T99", "mode": "TABLE_REPEAT", "groupKey": "field_047",
        "innerMode": "MATRIX", "enabled": True,
        "matrixLayout": {
            # 模拟历史配置中的旧字段名；运行时应以这些 Word 行内的控件绑定为准。
            "rowFields": [
                {"row": 1, "field": "solutionName"},
                {"row": 2, "field": "field2"},
                {"row": 3, "field": "peakArea"},
            ],
            "columnPolicy": {
                "mode": "DATA_LENGTH", "overflow": "HORIZONTAL",
                "minColumns": 2, "widthMode": "PRESERVE_TOTAL",
            },
        },
    }])


def _row_repeat_rule() -> TableLayoutRules:
    return TableLayoutRules([{
        "tableNo": "T99", "mode": "TABLE_REPEAT", "groupKey": "field_047",
        "innerMode": "ROW_REPEAT", "dataRowStart": 1,
        "preservedRowLabels": ["回归方程"], "enabled": True,
    }])


def _row_repeat_mappings() -> list[dict]:
    mappings = _mappings()
    for mapping in mappings:
        if mapping["controlTag"] == "summary.regression":
            mapping["fillRule"] = "PRESERVE_STYLE;EMPTY_AS_DASH"
    return mappings


def _text(table: etree._Element, row: int, cell: int) -> str:
    target = table.xpath("./w:tr", namespaces=NS)[row].xpath("./w:tc", namespaces=NS)[cell]
    return "".join(target.xpath(".//w:t/text()", namespaces=NS))


def test_table_repeat_matrix_reads_detail_and_summary_levels_from_bindings() -> None:
    document = _document()
    payload = {"results": [
        {
            "field_047": "杂质A", "field_012": "A符合要求",
            "injections": [
                {"field_021": "A-C1", "field_022": 1.5, "field_023": 101, "field_027": 99},
                {"field_021": "A-C2", "field_022": 3.0, "field_023": 202, "field_027": 198},
            ],
            "summary": {"field_024": "y=2x+1"},
        },
        {
            "field_047": "杂质B", "field_012": "B符合要求",
            "injections": [
                {"field_021": "B-C1", "field_022": 2.5, "field_023": 303, "field_027": 300},
                {"field_021": "B-C2", "field_022": 5.0, "field_023": 606, "field_027": 600},
            ],
            "summary": {"field_024": "y=3x+2"},
        },
    ]}
    warnings: list[tuple[str, str, str]] = []

    fill_repeat_rows(document, _mappings(), payload, {}, {}, _rule(),
                     lambda *items: warnings.append(items))

    tables = document.xpath("./w:body/w:tbl", namespaces=NS)
    assert len(tables) == 2
    assert [_text(tables[0], 0, index) for index in (1, 2)] == ["A-C1", "A-C2"]
    assert [_text(tables[0], 1, index) for index in (1, 2)] == ["1.5", "3.0"]
    assert [_text(tables[0], 2, index) for index in (1, 2)] == ["101", "202"]
    assert [_text(tables[0], 3, index) for index in (1, 2)] == ["99", "198"]
    assert _text(tables[0], 4, 1) == "y=2x+1"
    assert _text(tables[0], 5, 1) == "A符合要求"
    assert [_text(tables[1], 0, index) for index in (1, 2)] == ["B-C1", "B-C2"]
    assert _text(tables[1], 4, 1) == "y=3x+2"
    assert warnings == []


def test_table_repeat_matrix_does_not_treat_summary_rows_as_detail_level() -> None:
    document = _document()
    payload = {"results": [{
        "field_047": "杂质A", "field_012": "符合要求",
        "injections": [
            {"field_021": f"C{index}", "field_022": index, "field_023": index * 10}
            for index in range(1, 6)
        ],
        "summary": {"field_024": "y=10x"},
    }]}
    rule = _rule()
    rule.rule("T99")["matrixLayout"]["rowFields"].extend([
        {"row": 4, "field": "injections[*].field_027"},
        {"row": 5, "field": "injections[*].field_028"},
    ])
    warnings: list[tuple[str, str, str]] = []

    fill_repeat_rows(document, _mappings(), payload, {}, {}, rule,
                     lambda *items: warnings.append(items))

    table = document.xpath("./w:body/w:tbl", namespaces=NS)[0]
    assert [_text(table, 0, index) for index in range(1, 6)] == [
        "C1", "C2", "C3", "C4", "C5",
    ]
    assert table.xpath("./w:tr[1]/w:tc/w:tcPr/w:gridSpan/@w:val", namespaces=NS) == [
        "1", "1", "1", "1", "1",
    ]
    assert _text(table, 4, 1) == "y=10x"
    assert warnings == []


def test_table_repeat_rows_use_only_prototype_bindings_as_detail_level() -> None:
    document = _document()
    payload = {"results": [
        {
            "field_047": "杂质A",
            "injections": [{"field_021": "A-C1"}, {"field_021": "A-C2"}],
            "summary": {"field_024": "y=2x+1"},
        },
        {
            "field_047": "杂质B",
            "injections": [{"field_021": "B-C1"}, {"field_021": "B-C2"}],
            "summary": {"field_024": None},
        },
    ]}
    warnings: list[tuple[str, str, str]] = []

    fill_repeat_rows(document, _row_repeat_mappings(), payload, {}, {}, _row_repeat_rule(),
                     lambda *items: warnings.append(items))

    tables = document.xpath("./w:body/w:tbl", namespaces=NS)
    assert len(tables) == 2
    assert [_text(tables[0], index, 1) for index in (0, 1)] == ["A-C1", "A-C2"]
    assert _text(tables[0], 2, 1) == "y=2x+1"
    assert [_text(tables[1], index, 1) for index in (0, 1)] == ["B-C1", "B-C2"]
    assert _text(tables[1], 2, 1) == "-"
    assert warnings == []


@pytest.mark.parametrize("mode", ["MATRIX", "ROW_REPEAT"])
def test_missing_repeated_image_clears_template_picture(mode: str) -> None:
    document = _document()
    control = document.xpath(
        ".//w:sdt[w:sdtPr/w:tag/@w:val='summary.regression']", namespaces=NS,
    )[0]
    etree.SubElement(control.find(".//" + W + "r"), W + "drawing")
    mappings = _mappings()
    chart = next(item for item in mappings if item["controlTag"] == "summary.regression")
    chart.update({"sourcePath": "$.results[*].summary.field_084", "dataType": "image",
                  "fillRule": "PRESERVE_STYLE;EMPTY_AS_DASH"})
    rule = _rule() if mode == "MATRIX" else _row_repeat_rule()
    payload = {"results": [
        {"field_047": "A", "injections": [{"field_021": "A-1"}],
         "summary": {"field_084": "data:image/png;base64,aGVsbG8="}},
        {"field_047": "B", "injections": [{"field_021": "B-1"}], "summary": {}},
    ]}
    warnings: list[tuple[str, str, str]] = []

    fill_repeat_rows(document, mappings, payload, {}, {}, rule,
                     lambda *items: warnings.append(items))

    tables = document.xpath("./w:body/w:tbl", namespaces=NS)
    assert len(tables) == 2
    assert tables[0].xpath(".//w:sdt[w:sdtPr/w:tag/@w:val='summary.regression']//w:drawing", namespaces=NS)
    assert not tables[1].xpath(".//w:sdt[w:sdtPr/w:tag/@w:val='summary.regression']//w:drawing", namespaces=NS)
    assert tables[1].xpath(
        ".//w:sdt[w:sdtPr/w:tag/@w:val='summary.regression']//w:t/text()", namespaces=NS,
    ) == ["-"]
    assert warnings == []


def test_table_repeat_data_row_overrides_stale_bookmark_in_summary_row() -> None:
    document = _document()
    rows = document.xpath(".//w:tbl/w:tr", namespaces=NS)
    bookmark = rows[0].find(W + "bookmarkStart")
    rows[0].remove(bookmark)
    rows[-1].insert(0, bookmark)
    payload = {"results": [{
        "field_047": "杂质A",
        "injections": [{"field_021": f"A-C{index}"} for index in range(1, 7)],
        "summary": {"field_024": "y=2x+1"},
    }]}
    warnings: list[tuple[str, str, str]] = []

    fill_repeat_rows(document, _row_repeat_mappings(), payload, {}, {}, _row_repeat_rule(),
                     lambda *items: warnings.append(items))

    table = document.xpath("./w:body/w:tbl", namespaces=NS)[0]
    assert [_text(table, index, 1) for index in range(6)] == [
        "A-C1", "A-C2", "A-C3", "A-C4", "A-C5", "A-C6",
    ]
    assert warnings == []
