"""横向分组：向下填充的基础上按分组字段向右扩列。

编组数组的每个元素就是一个分组，`summary` 是每组一个值的层，`injections` 是明细层；
一个分组占哪几列、每一列填哪个字段，都从 Word 文档和已有的控件绑定推导。
"""

import tempfile
import zipfile
from pathlib import Path

from lxml import etree

from backend.app.services.mapped_docx_generator import build_mapped_docx


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _cell(row: etree._Element, text: str, width: int, span: int = 1, tag: str = "") -> None:
    cell = etree.SubElement(row, W + "tc")
    properties = etree.SubElement(cell, W + "tcPr")
    etree.SubElement(properties, W + "tcW").set(W + "w", str(width))
    if span > 1:
        etree.SubElement(properties, W + "gridSpan").set(W + "val", str(span))
    owner = cell
    if tag:
        sdt = etree.SubElement(cell, W + "sdt")
        sdt_properties = etree.SubElement(sdt, W + "sdtPr")
        etree.SubElement(sdt_properties, W + "tag").set(W + "val", tag)
        owner = etree.SubElement(sdt, W + "sdtContent")
    node = etree.SubElement(etree.SubElement(etree.SubElement(owner, W + "p"), W + "r"), W + "t")
    node.text = text


def _prototype(path: Path) -> None:
    """复刻 7.1-2 的原型：单个杂质 + 2 个子列，第 3 行是原型数据行。"""
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    grid = etree.SubElement(table, W + "tblGrid")
    for width in (1987, 2982, 3543):
        etree.SubElement(grid, W + "gridCol").set(W + "w", str(width))

    row = etree.SubElement(table, W + "tr")
    _cell(row, "名称", 1987)
    _cell(row, "杂质甲", 6525, span=2, tag="cc.impurity")

    row = etree.SubElement(table, W + "tr")
    _cell(row, "", 1987)
    _cell(row, "保留时间（min）", 2982)
    _cell(row, "峰面积", 3543)

    row = etree.SubElement(table, W + "tr")
    _cell(row, "溶液1", 1987, tag="cc.solution")
    _cell(row, "4.210", 2982, tag="cc.retentionTime")
    _cell(row, "1593245", 3543, tag="cc.peakArea")

    row = etree.SubElement(table, W + "tr")
    _cell(row, "RSD（n=6，%）", 1987)
    _cell(row, "0.1", 2982, tag="cc.retentionTimeRsd")
    _cell(row, "1.4", 3543, tag="cc.peakAreaRsd")

    row = etree.SubElement(table, W + "tr")
    _cell(row, "结论", 1987)
    _cell(row, "模板里的旧结论", 6525, span=2, tag="cc.conclusion")

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True))


# 字段路径由编组层级推导：分组主体不带前缀，summary 是对象层，injections 是数组层
BINDINGS = [
    ("cc.impurity", "impurityName", "impurityName"),
    ("cc.solution", "solutionName", "injections[*].solutionName"),
    ("cc.retentionTime", "retentionTime", "injections[*].retentionTime"),
    ("cc.peakArea", "peakArea", "injections[*].peakArea"),
    ("cc.retentionTimeRsd", "retentionTimeRsd", "summary.retentionTimeRsd"),
    ("cc.peakAreaRsd", "peakAreaRsd", "summary.peakAreaRsd"),
]


def _mappings() -> list[dict]:
    rows = [{
        "enabled": True, "repeatType": "ROW", "tableNo": "T1", "sourceType": "LIMS",
        "controlTag": tag, "fieldCode": f"suitability.{field}", "wordLabel": field,
        "sourcePath": f"$.suitability[*].{path}", "blockSourcePath": "$.suitability[*]",
        "contentBlockKind": "REPEATING_TABLE",
        # 取值格式来自标准字段目录，分组扩列不影响它
        **({"standardFieldDataType": "decimal", "standardFieldOutputFormat": "3"}
           if field == "retentionTime" else {}),
    } for tag, field, path in BINDINGS]
    # 结论属于别的编组：不是本表的循环字段，本表不该碰它
    rows.append({"enabled": True, "repeatType": "NONE", "controlTag": "cc.conclusion",
                 "fieldCode": "summary.conclusion", "wordLabel": "结论", "sourcePath": "$.conclusion"})
    return rows


def _records(impurities: list[str], injections: int = 6) -> list[dict]:
    rsd = {"杂质甲": ("0.1", "1.4"), "杂质乙": ("0.1", "0.3"), "杂质丙": ("0.1", "0.5")}
    return [{
        "impurityName": name,
        "summary": {"retentionTimeRsd": rsd[name][0], "peakAreaRsd": rsd[name][1]},
        "injections": [{
            "solutionName": f"溶液{index}", "sequence": index,
            "retentionTime": 4.2 + index / 1000, "peakArea": 1500000 + index,
        } for index in range(1, injections + 1)],
    } for name in impurities]


def _rule(group_field: str = "impurityName", width: str = "EQUAL") -> list[dict]:
    layout = f'{{"groupField": "{group_field}", "groupColumnWidth": "{width}"}}' if group_field else ""
    return [{"tableNo": "T1", "mode": "ROW_REPEAT", "enabled": True, "physicalTableIndex": 1,
             "dataRowStart": 3, "dataRowEnd": 3, "matrixLayout": layout}]


def _generate(directory: str, impurities: list[str], group_field: str = "impurityName",
              width: str = "EQUAL", injections: int = 6) -> tuple[etree._Element, dict]:
    template, output = Path(directory) / "t.docx", Path(directory) / "out.docx"
    _prototype(template)
    report: dict = {}
    build_mapped_docx(template, output, _mappings(), {"suitability": _records(impurities, injections)},
                      report, _rule(group_field, width))
    root = etree.fromstring(zipfile.ZipFile(output).read("word/document.xml"))
    return root.xpath(".//w:tbl", namespaces=NS)[0], report


def _grid(table: etree._Element) -> list[int]:
    return [int(column.get(W + "w")) for column in table.find(W + "tblGrid")]


def _text(table: etree._Element, row: int, cell: int) -> str:
    cells = table.xpath("./w:tr", namespaces=NS)[row].xpath("./w:tc", namespaces=NS)
    return "".join(cells[cell].xpath(".//w:t/text()", namespaces=NS))


def _row_usage(row: etree._Element) -> int:
    after = int(row.xpath("string(./w:trPr/w:gridAfter/@w:val)", namespaces=NS) or 0)
    return after + sum(int(cell.xpath("string(./w:tcPr/w:gridSpan/@w:val)", namespaces=NS) or 1)
                       for cell in row.xpath("./w:tc", namespaces=NS))


def test_group_span_and_field_mapping_come_from_the_document() -> None:
    """分组宽度取绑定格的合并跨度，子列填哪个字段取控件绑定，版式里都没配。"""
    with tempfile.TemporaryDirectory() as directory:
        table, report = _generate(directory, ["杂质甲", "杂质乙", "杂质丙"])

        assert [_text(table, 0, index) for index in (1, 2, 3)] == ["杂质甲", "杂质乙", "杂质丙"]
        assert _text(table, 1, 1) == "保留时间（min）" and _text(table, 1, 2) == "峰面积"
        assert _text(table, 1, 5) == "保留时间（min）", "子列标题随整块复制，不用声明"
        assert _text(table, 2, 0) == "溶液1"
        assert _text(table, 2, 1) == "4.201" and _text(table, 2, 2) == "1500001"
        assert _text(table, 7, 0) == "溶液6"
        assert report.get("warnings", []) == []


def test_rows_expand_downward_by_records_within_each_group() -> None:
    with tempfile.TemporaryDirectory() as directory:
        table, _ = _generate(directory, ["杂质甲", "杂质乙"], injections=4)

        assert len(table.xpath("./w:tr", namespaces=NS)) == 2 + 4 + 2
        assert [_text(table, index, 0) for index in range(2, 6)] == ["溶液1", "溶液2", "溶液3", "溶液4"]


def test_non_prototype_rows_get_one_value_per_group() -> None:
    """RSD 行不是原型行，但含本编组控件：每个分组填一个组内唯一值。"""
    with tempfile.TemporaryDirectory() as directory:
        table, _ = _generate(directory, ["杂质甲", "杂质乙", "杂质丙"])

        assert _text(table, 8, 0) == "RSD（n=6，%）", "首列固定文字保留 Word 原文"
        assert [_text(table, 8, index) for index in (2, 4, 6)] == ["1.4", "0.3", "0.5"]


def test_row_without_this_group_controls_is_left_alone() -> None:
    """结论属于别的编组：内容不动，只把合并跨度撑到新的表格宽度。"""
    with tempfile.TemporaryDirectory() as directory:
        table, _ = _generate(directory, ["杂质甲", "杂质乙", "杂质丙"])
        rows = table.xpath("./w:tr", namespaces=NS)

        assert _text(table, 9, 1) == "模板里的旧结论"
        assert _row_usage(rows[-1]) == len(_grid(table))


def test_table_width_is_preserved_for_one_two_and_three_groups() -> None:
    for count in (1, 2, 3):
        with tempfile.TemporaryDirectory() as directory:
            table, _ = _generate(directory, ["杂质甲", "杂质乙", "杂质丙"][:count])
            grid = _grid(table)

            assert len(grid) == 1 + count * 2
            assert abs(sum(grid) - 8512) <= count
            assert len(set(grid[1:])) == 1, "等宽时各子列宽度一致"
            for row in table.xpath("./w:tr", namespaces=NS):
                assert _row_usage(row) == len(grid)


def test_prototype_width_ratio_is_kept_when_not_equal() -> None:
    with tempfile.TemporaryDirectory() as directory:
        table, _ = _generate(directory, ["杂质甲", "杂质乙", "杂质丙"], width="PROTOTYPE")

        assert _grid(table)[1:3] == [994, 1181]


def test_without_a_group_field_it_is_plain_row_repeat() -> None:
    with tempfile.TemporaryDirectory() as directory:
        table, _ = _generate(directory, ["杂质甲"], group_field="")

        assert len(_grid(table)) == 3, "不分组就不扩列"
        assert _text(table, 2, 0) == "溶液1"


def test_unbound_group_field_is_reported_instead_of_guessed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        table, report = _generate(directory, ["杂质甲", "杂质乙"], group_field="solutionCode")

        assert any("solutionCode" in item for item in report["warnings"])
        assert len(_grid(table)) == 3, "配置不成立时保留 Word 原样"
