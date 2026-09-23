import json
from pathlib import Path
from shutil import copyfile

from docx import Document
from lxml import etree
import pytest

from backend.app.services.docx_segment_table import fill_segment_heading, fill_segment_table
from backend.app.services.docx_table_cells import NS
from backend.app.services.segment_table_install import _unique_tags, target_table
from backend.app.services.template_compiler import compile_template
from backend.app.services.mapped_docx_generator import build_mapped_docx


ROOT = Path(__file__).parents[2]
MANIFEST = json.loads((ROOT / "mapping/intermediate-precision-excel.json").read_text())
DRAFT = ROOT / "templates/drafts/report-template-2d6829aa527b409c9b76a1ab041227ff.docx"


def _table() -> etree._Element:
    root = etree.fromstring(etree.tostring(Document(DRAFT).element.body))
    return next(table for table in root.xpath("./w:tbl", namespaces=NS)
                if "人员/日期" in "".join(table.xpath("./w:tr[1]//w:t/text()", namespaces=NS)))


def _cells(table: etree._Element) -> list[list[etree._Element]]:
    return [row.xpath("./w:tc", namespaces=NS) for row in table.xpath("./w:tr", namespaces=NS)]


def _cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS))


def test_fills_both_technician_segments_without_changing_report_columns() -> None:
    table = _table()
    original_widths = [len(row) for row in _cells(table)]
    record = {
        "impurityName": "杂质X", "field_128": "技术员A\n2026.08.25",
        "field_145": "技术员B\n2026.08.26",
        "injections": [
            {"sequence": str(index % 6 + 1), "weighing": "13.74",
             "retentionTime": "4.208", "peakArea": str(1000 + index),
             "concentration": "30.49", "field_134": str(index)}
            for index in range(12)
        ],
        "aRetentionRsd": "0.1", "aContentRsd": "2.8", "field_137": "0.2",
        "field_138": "1.1", "field_139": "（47.5，48.5）", "field_140": "（190，194）",
        "field_141": "5.0", "field_142": "（44.6，47.5）", "field_143": "（178，190）",
    }
    fill_segment_heading(table.getprevious(), record, MANIFEST["tableLayout"])
    fill_segment_table(table, record, MANIFEST["tableLayout"])

    cells = _cells(table)
    assert len(cells) == 21
    assert [len(row) for row in cells] == (
        original_widths[:2] + [original_widths[1]] * 5 + [original_widths[2]]
        + [original_widths[3]] * 6 + original_widths[4:]
    )
    assert _cell_text(cells[1][0]) == "技术员A2026.08.25"
    assert _cell_text(cells[6][4]) == "1005"
    assert _cell_text(cells[7][5]) == "2.8"
    assert _cell_text(cells[8][0]) == "技术员B2026.08.26"
    assert len(cells[8][0].xpath(".//w:br", namespaces=NS)) == 1
    assert _cell_text(cells[13][4]) == "1011"
    assert _cell_text(cells[14][5]) == "1.1"
    assert _cell_text(cells[15][2]) == "（47.5，48.5）"
    assert _cell_text(cells[17][1]) == "5.0"
    assert _cell_text(cells[20][1]) == ""
    assert "杂质X-中间精密度" in table.getprevious().xpath("string(.)")


def test_optional_conclusion_fills_when_supplied() -> None:
    table = _table()
    record = {"impurityName": "杂质X", "field_128": "人员A", "field_145": "人员B",
              "field_144": "经批准的结论", "aRetentionRsd": "0.1", "aContentRsd": "1.0",
              "field_137": "0.1", "field_138": "1.0", "field_139": "（1，2）",
              "field_140": "（3，4）", "field_141": "0.2", "field_142": "（5，6）",
              "field_143": "（7，8）", "injections": [
                  {"sequence": str(i % 6 + 1), "weighing": "1", "retentionTime": "2",
                   "peakArea": "3", "concentration": "4", "field_134": "5"} for i in range(12)
              ]}
    fill_segment_table(table, record, MANIFEST["tableLayout"])
    assert _cell_text(_cells(table)[20][1]) == "经批准的结论"


def test_rejects_incomplete_segment_coverage() -> None:
    table = _table()
    with pytest.raises(ValueError, match="未完整覆盖"):
        fill_segment_table(table, {"injections": [{}] * 13}, MANIFEST["tableLayout"])


def test_unique_control_tag_changes_no_visible_report_text(tmp_path: Path) -> None:
    destination = tmp_path / "draft.docx"
    copyfile(DRAFT, destination)
    before = Document(destination).tables[23]
    original = [[cell.text for cell in row.cells] for row in before.rows]
    index, _ = target_table(destination, MANIFEST["tableHeader"])
    _unique_tags(destination, index, MANIFEST["uniqueControls"])
    after = Document(destination).tables[23]
    assert [[cell.text for cell in row.cells] for row in after.rows] == original
    tags = after.rows[2].cells[0]._tc.xpath(".//w:sdtPr/w:tag/@w:val")
    assert tags == [MANIFEST["uniqueControls"][0]["tag"]]
    _unique_tags(destination, index, MANIFEST["uniqueControls"])


def test_compiled_draft_repeats_full_report_table_per_impurity(tmp_path: Path) -> None:
    index, tags = target_table(DRAFT, MANIFEST["tableHeader"])
    tag = MANIFEST["uniqueControls"][0]["tag"]
    assert tag in tags
    group = MANIFEST["groupCode"]
    mapping = {"locationId": f"word.content_control.{tag}", "fieldCode": "person.summary",
               "standardFieldCode": "uncategorized.field_128", "wordLabel": "人员",
               "tableNo": MANIFEST["tableNo"], "repeatType": "ROW", "controlTag": tag,
               "sourcePath": f"$.{group}[*].field_128", "groupItemPath": f"$.{group}[*]"}
    layout = {"tableNo": MANIFEST["tableNo"], "mode": "TABLE_REPEAT",
              "innerMode": "SEGMENT_REPEAT", "physicalTableIndex": index,
              "dataRowStart": 2, "groupKey": "impurityName",
              "matrixLayout": MANIFEST["tableLayout"]}
    compiled, output = tmp_path / "compiled.docx", tmp_path / "rendered.docx"
    report = compile_template(DRAFT, compiled, [mapping], [layout])
    assert not report["errors"]
    record = {"field_128": "技术员A\n2026.08.25", "field_145": "技术员B\n2026.08.26",
              "aRetentionRsd": "0.1", "aContentRsd": "2.8", "field_137": "0.2",
              "field_138": "1.1", "field_139": "（47.5，48.5）", "field_140": "（190，194）",
              "field_141": "5.0", "field_142": "（44.6，47.5）", "field_143": "（178，190）",
              "injections": [{"sequence": str(i % 6 + 1), "weighing": "13.74",
                              "retentionTime": "4.208", "peakArea": "1000",
                              "concentration": "30.49", "field_134": "44.4"} for i in range(12)]}
    payload = {group: [{**record, "impurityName": name} for name in ("杂质X", "杂质Y")]}
    report_data = {"source_payloads": {"EXCEL": payload}, "warnings": []}
    build_mapped_docx(compiled, output, [mapping], payload, report_data, [layout])
    root = etree.fromstring(etree.tostring(Document(output).element.body))
    tables = [table for table in root.xpath("./w:tbl", namespaces=NS)
              if "人员/日期" in "".join(table.xpath("./w:tr[1]//w:t/text()", namespaces=NS))]
    assert [len(_cells(table)) for table in tables] == [21, 21]
    assert [_cell_text(_cells(table)[8][0]) for table in tables] == ["技术员B2026.08.26"] * 2
    assert "杂质X" in tables[0].getprevious().xpath("string(.)")
    assert "杂质Y" in tables[1].getprevious().xpath("string(.)")
    assert len([warning for warning in report_data["warnings"] if "结论缺少来源" in warning]) == 2
