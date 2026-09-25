import json
from pathlib import Path

from docx import Document
from lxml import etree
import pytest

from backend.app.services.docx_segment_table import (
    apply_segment_vertical_merges, fill_segment_heading, fill_segment_table,
    validate_segment_layout,
)
from backend.app.services.docx_table_repeat import _inferred_segment_layout
from backend.app.services.designer_config_repository import DesignerConfigRepositoryMixin
from backend.app.services.docx_table_cells import NS
from backend.app.services.segment_table_install import _cell_control_tag, _install_control_bindings, target_table
from backend.app.services.template_compiler import compile_template
from backend.app.services.mapped_docx_generator import build_mapped_docx


ROOT = Path(__file__).parents[2]
MANIFEST = json.loads((ROOT / "mapping/intermediate-precision-excel.json").read_text())
DRAFT = ROOT / "templates/drafts/report-template-0537c205b253406f97b52d70b9c323b1.docx"


def _table() -> etree._Element:
    root = etree.fromstring(etree.tostring(Document(DRAFT).element.body))
    return next(table for table in root.xpath("./w:tbl", namespaces=NS)
                if "".join(table.xpath("./w:tr[1]/w:tc[1]//w:t/text()", namespaces=NS))
                == MANIFEST["tableHeader"])


def _cells(table: etree._Element) -> list[list[etree._Element]]:
    return [row.xpath("./w:tc", namespaces=NS) for row in table.xpath("./w:tr", namespaces=NS)]


def _cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS))


def _record() -> dict:
    return {
        "impurityName": "杂质X",
        "field_141": "5.0", "field_142": "（44.6，47.5）", "field_143": "（178，190）",
        **{
            f"technician{letter}": {"name": name, "date": date,
             "retentionRsd": retention, "contentRsd": content,
             "contentConfidenceInterval": "（47.5，48.5）",
             "theoreticalPercentInterval": "（190，194）",
             f"injections{letter}": [
                 {"sequence": str(index + 1), "weighing": "13.74", "retentionTime": "4.208",
                  "peakArea": str(1000 + group_index * 6 + index), "concentration": "30.49",
                  "relativeContent": str(group_index * 6 + index)}
                 for index in range(6)]}
            for group_index, (letter, name, date, retention, content) in enumerate((
                ("A", "技术员A", "2026.08.25", "0.1", "2.8"),
                ("B", "技术员B", "2026.08.26", "0.2", "1.1")))
        },
    }


def test_fills_both_technician_segments_without_changing_report_columns() -> None:
    table = _table()
    original_widths = [len(row) for row in _cells(table)]
    record = _record()
    fill_segment_heading(table.getprevious(), record, MANIFEST["tableLayout"])
    fill_segment_table(table, record, MANIFEST["tableLayout"])

    cells = _cells(table)
    assert len(cells) == 21
    assert [len(row) for row in cells] == (
        original_widths[:2] + [original_widths[1]] * 5 + [original_widths[2]]
        + [original_widths[3]] * 6 + original_widths[4:]
    )
    assert _cell_text(cells[1][0]) == "技术员A"
    assert _cell_text(cells[6][0]) == "技术员A"
    assert _cell_text(cells[6][4]) == "1005"
    assert _cell_text(cells[7][5]) == "2.8"
    assert _cell_text(cells[8][0]) == "技术员B"
    assert _cell_text(cells[13][4]) == "1011"
    assert _cell_text(cells[14][5]) == "1.1"
    assert _cell_text(cells[15][2]) == "（47.5，48.5）"
    assert _cell_text(cells[17][1]) == "5.0"
    assert _cell_text(cells[20][1]) == ""
    assert table.getprevious().xpath("string(.)") == "杂质X"


def test_optional_conclusion_fills_when_supplied() -> None:
    table = _table()
    record = {**_record(), "field_144": "经批准的结论"}
    fill_segment_table(table, record, MANIFEST["tableLayout"])
    assert _cell_text(_cells(table)[20][1]) == "经批准的结论"


def test_missing_technician_dates_do_not_block_table_fill() -> None:
    table = _table()
    record = _record()
    record["technicianA"].pop("date")
    record["technicianB"]["date"] = ""
    layout = json.loads(json.dumps(MANIFEST["tableLayout"]))
    for item in [*layout["segments"], *layout["summaryRows"]]:
        item["groupCells"] = {"0": {"fields": ["name", "date"], "separator": "\n"}}

    fill_segment_table(table, record, layout)

    assert _cell_text(_cells(table)[1][0]) == "技术员A"
    assert _cell_text(_cells(table)[8][0]) == "技术员B"


def test_detail_rows_expand_from_actual_record_counts() -> None:
    table = _table()
    record = _record()
    record["technicianA"]["injectionsA"] = record["technicianA"]["injectionsA"][:3]
    record["technicianB"]["injectionsB"] = record["technicianB"]["injectionsB"][:2]

    fill_segment_table(table, record, MANIFEST["tableLayout"])

    rows = _cells(table)
    assert len(rows) == 14
    assert _cell_text(rows[4][0]) == "技术员A"
    assert _cell_text(rows[7][0]) == "技术员B"
    assert _cell_text(rows[10][0]) == "RSD（n=12，%）"


def test_rejects_missing_segment_source() -> None:
    table = _table()
    record = _record()
    del record["technicianB"]
    with pytest.raises(ValueError, match="来源对象 technicianB 缺失"):
        fill_segment_table(table, record, MANIFEST["tableLayout"])


def test_rejects_duplicate_segment_rows_before_rendering() -> None:
    layout = {**MANIFEST["tableLayout"], "segments": [
        MANIFEST["tableLayout"]["segments"][0],
        {**MANIFEST["tableLayout"]["segments"][1], "row": 2},
    ]}
    with pytest.raises(ValueError, match="不能重复"):
        validate_segment_layout(layout)


def test_rejects_invalid_segment_layout_when_saving_table_rule() -> None:
    with pytest.raises(ValueError, match="非空 segments"):
        DesignerConfigRepositoryMixin._matrix_layout_text({
            "mode": "TABLE_REPEAT", "innerMode": "SEGMENT_REPEAT", "matrixLayout": "{}",
        })


def test_segment_vertical_merge_honors_field_merge_rule() -> None:
    root = etree.fromstring("""<w:tbl xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:tr><w:tc><w:sdt><w:sdtPr><w:tag w:val="name"/></w:sdtPr><w:sdtContent><w:p><w:r><w:t>技术员A</w:t></w:r></w:p></w:sdtContent></w:sdt></w:tc></w:tr>
      <w:tr><w:tc><w:sdt><w:sdtPr><w:tag w:val="name"/></w:sdtPr><w:sdtContent><w:p><w:r><w:t>技术员A</w:t></w:r></w:p></w:sdtContent></w:sdt></w:tc></w:tr>
    </w:tbl>""")
    apply_segment_vertical_merges(root, [{"controlTag": "name", "mergeRule": "VERTICAL_BY_VALUE"}])
    cells = root.xpath("./w:tr/w:tc", namespaces=NS)
    assert cells[0].xpath("./w:tcPr/w:vMerge/@w:val", namespaces=NS) == ["restart"]
    assert cells[1].xpath("./w:tcPr/w:vMerge", namespaces=NS)
    assert "".join(cells[1].xpath(".//w:t/text()", namespaces=NS)) == ""


def test_technician_labels_follow_template_bindings() -> None:
    table = _table()
    cells = _cells(table)
    assert _cell_text(cells[0][0]) == "人员/日期"
    assert "uniqueControls" not in MANIFEST
    for index, label in ((1, "技术员A"), (2, "技术员A"),
                         (3, "技术员B"), (4, "技术员B")):
        assert _cell_text(cells[index][0]) == label
        tags = cells[index][0].xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS)
        expected = {1: "技术员a", 3: "技术员b"}.get(index)
        assert tags == ([f"cc.report.s7_6.中间精密度_加标供试品试验结果表.{expected}"] if expected else [])


def test_control_binding_uses_physical_columns_after_merged_cells() -> None:
    index, _ = target_table(DRAFT, MANIFEST["tableHeader"])
    for binding in MANIFEST["detailControls"]:
        if binding["row"] != 2:
            continue
        tag = _cell_control_tag(DRAFT, index, binding["row"], binding["column"])
        assert tag.endswith({
            "intermediatePrecision.technicianA.sequence": ".技术员a_no",
            "intermediatePrecision.technicianA.weighing": ".技术员a称样量_mg",
            "intermediatePrecision.technicianA.retentionTime": ".技术员a保留时间_min",
            "intermediatePrecision.technicianA.peakArea": ".技术员a峰面积",
            "intermediatePrecision.technicianA.concentration": ".技术员a测得浓度_ng_ml",
        }[binding["fieldCode"]])


def test_row_repeat_can_infer_multiple_detail_regions_from_bindings() -> None:
    table = _table()
    prefix = "cc.report.s7_6.中间精密度_加标供试品试验结果表."

    def mapping(tag: str, path: str) -> dict:
        return {"controlTag": prefix + tag, "sourcePath": "$.intermediatePrecision[*]." + path,
                "repeatType": "ROW"}

    mappings = []
    for letter in ("A", "B"):
        lower = letter.lower()
        array = f"injections{letter}"
        for tag, field in ((f"技术员{lower}_no", "sequence"),
                           (f"技术员{lower}称样量_mg", "weighing"),
                           (f"技术员{lower}保留时间_min", "retentionTime"),
                           (f"技术员{lower}峰面积", "peakArea"),
                           (f"技术员{lower}测得浓度_ng_ml", "concentration"),
                           (f"技术员{lower}相当供试品中含量", "relativeContent")):
            mappings.append(mapping(tag, f"technician{letter}.{array}[*].{field}"))
    mappings.extend([
        mapping("技术员a保留时间rsd_n_6", "technicianA.retentionRsd"),
        mapping("技术员a含量rsd_n_6", "technicianA.contentRsd"),
        mapping("技术员b保留时间rsd_n_6", "technicianB.retentionRsd"),
        mapping("技术员b含量rsd_n_6", "technicianB.contentRsd"),
    ])
    inferred = _inferred_segment_layout(table, mappings, ("intermediatePrecision", ""))
    assert inferred is not None
    assert [(item["row"], item["sourcePath"], item["detailPath"])
            for item in inferred["segments"]] == [
                (2, "technicianA", "injectionsA"),
                (4, "technicianB", "injectionsB"),
            ]
    assert [item["row"] for item in inferred["summaryRows"]] == [3, 5]


def test_unique_summary_control_does_not_create_duplicate_system_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict] = []

    class DatabaseStub:
        @staticmethod
        def get_lims_field(_field: str) -> dict:
            return {"fieldCode": "uncategorized.field_128"}

    class RepositoryStub:
        database = DatabaseStub()

        @staticmethod
        def list_mappings() -> list[dict]:
            return []

        @staticmethod
        def create_mapping(item: dict) -> None:
            created.append(item)

    monkeypatch.setattr(
        "backend.app.services.segment_table_install._cell_control_tag",
        lambda *_args: "cc.summary-technician-a",
    )
    manifest = {
        "tableNo": "T26",
        "fields": [{"code": "uncategorized.field_128"}],
        "detailControls": [],
        "uniqueControls": [{
            "row": 3, "column": 1, "tag": "cc.summary-technician-a",
            "fieldCode": "uncategorized.field_128",
        }],
    }

    _install_control_bindings(RepositoryStub(), manifest, DRAFT, 24, "7.6")

    assert created == []


def test_compiled_draft_repeats_full_report_table_per_impurity(tmp_path: Path) -> None:
    index, tags = target_table(DRAFT, MANIFEST["tableHeader"])
    group = MANIFEST["groupCode"]
    tag = "cc.report.s7_6.中间精密度_加标供试品试验结果表.技术员a_no"
    assert tag in tags
    mappings = [{"locationId": f"word.content_control.{tag}", "fieldCode": "injection.sequence",
                 "standardFieldCode": "intermediatePrecision.technicianA.sequence", "wordLabel": "No.",
                 "tableNo": MANIFEST["tableNo"], "repeatType": "ROW", "controlTag": tag,
                 "sourcePath": f"$.{group}[*].technicianA.injectionsA[*].sequence",
                 "groupItemPath": f"$.{group}[*]"}]
    for letter in ("A", "B"):
        name_tag = f"cc.report.s7_6.中间精密度_加标供试品试验结果表.技术员{letter.lower()}"
        mappings.append({"locationId": f"word.content_control.{name_tag}",
                         "fieldCode": f"technician{letter}.name",
                         "standardFieldCode": f"intermediatePrecision.technician{letter}.name",
                         "wordLabel": f"技术员{letter}",
                         "tableNo": MANIFEST["tableNo"], "repeatType": "ROW", "controlTag": name_tag,
                         "sourcePath": f"$.{group}[*].technician{letter}.name",
                         "groupItemPath": f"$.{group}[*]"})
    layout = {"tableNo": MANIFEST["tableNo"], "mode": "TABLE_REPEAT",
              "innerMode": "SEGMENT_REPEAT", "physicalTableIndex": index,
              "dataRowStart": 2, "groupKey": "impurityName",
              "matrixLayout": MANIFEST["tableLayout"]}
    compiled, output = tmp_path / "compiled.docx", tmp_path / "rendered.docx"
    report = compile_template(DRAFT, compiled, mappings, [layout])
    assert not report["errors"]
    record = _record()
    record["technicianA"].update(name="操作员甲", date="")
    record["technicianB"].update(name="操作员乙", date="")
    payload = {group: [{**record, "impurityName": name} for name in ("杂质X", "杂质Y")]}
    report_data = {"source_payloads": {"EXCEL": payload}, "warnings": []}
    build_mapped_docx(compiled, output, mappings, payload, report_data, [layout])
    root = etree.fromstring(etree.tostring(Document(output).element.body))
    tables = [table for table in root.xpath("./w:tbl", namespaces=NS)
              if "".join(table.xpath("./w:tr[1]/w:tc[1]//w:t/text()", namespaces=NS))
              == MANIFEST["tableHeader"]]
    assert [len(_cells(table)) for table in tables] == [21, 21]
    assert [_cell_text(_cells(table)[1][0]) for table in tables] == ["操作员甲"] * 2
    assert [_cell_text(_cells(table)[7][5]) for table in tables] == ["2.8"] * 2
    assert [_cell_text(_cells(table)[8][0]) for table in tables] == ["操作员乙"] * 2
    assert [_cell_text(_cells(table)[14][5]) for table in tables] == ["1.1"] * 2
    assert "杂质X" in tables[0].getprevious().xpath("string(.)")
    assert "杂质Y" in tables[1].getprevious().xpath("string(.)")
    assert len([warning for warning in report_data["warnings"] if "结论缺少来源" in warning]) == 2
