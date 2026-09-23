from pathlib import Path
import tempfile

from openpyxl import Workbook
import pytest

from backend.app.services.excel_field_extractor import extract_excel_fields
from backend.app.services.excel_catalog_manifest import prepared_fields, read_manifest
from backend.app.services.excel_rule_engine import ExcelRuleError


def test_repeat_block_concatenates_configured_regions_in_order() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "结果"
    for row, values in enumerate((("A", 1), ("A", 2), ("B", 3), ("B", 4)), 1):
        sheet.cell(row, 1, values[0])
        sheet.cell(row, 2, values[1])
    field = {
        "fieldCode": "result.value", "cardinality": "MANY",
        "legacyJsonPath": "$.result[*].value",
    }
    rule = {
        "id": 1, "fieldCode": field["fieldCode"], "sourceType": "EXCEL",
        "enabled": True,
        "config": {
            "mode": "REPEAT_BLOCK", "sheet": "结果", "repeatCount": 1,
            "rowStart": 1, "rowEnd": 1, "startColumn": 1,
            "valueMode": "CELL", "sourcePath": field["legacyJsonPath"],
            "regions": [
                {"label": "A", "rowStart": 1, "rowEnd": 2, "startColumn": 2},
                {"label": "B", "rowStart": 3, "rowEnd": 4, "startColumn": 2},
            ],
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "regions.xlsx"
        workbook.save(path)

        payload = extract_excel_fields(path, [field], [rule])

    assert [record["value"] for record in payload["result"]] == ["1", "2", "3", "4"]


def test_actual_workbook_extracts_both_technicians_and_cached_statistics() -> None:
    root = Path(__file__).parents[2]
    manifest = read_manifest(root / "mapping/intermediate-precision-excel.json")
    group = manifest["groupCode"]
    fields, rules = [], []
    group_meta = {"groupCode": group, "cardinality": "MANY", "fields": [
        {"fieldCode": spec["code"], "label": spec["code"],
         "jsonKey": spec["code"].rsplit(".", 1)[-1]}
        for spec in manifest["fields"] if spec["code"].startswith("uncategorized.")
    ], "levels": [{"levelKey": "injections", "kind": "ARRAY"}]}
    for index, spec in enumerate(prepared_fields(manifest, group_meta), 1):
        code = spec["fieldCode"]
        path = spec["legacyJsonPath"]
        fields.append({"fieldCode": code, "groupCode": group, "cardinality": "MANY",
                       "legacyJsonPath": path})
        rules.append({"id": index, "fieldCode": code, "sourceType": "EXCEL", "enabled": True,
                      "config": spec["config"]})

    payload = extract_excel_fields(
        root / "文霞-标准计算表-动态-V56-解锁版-XM2026219-03.xlsm", fields, rules,
    )
    records = payload[group]
    assert len(records) == 3
    assert [item["impurityName"] for item in records] == [
        "3-吡啶磺酸甲酯", "3-吡啶磺酸乙酯", "3-吡啶磺酸异丙酯",
    ]
    assert records[0]["field_128"] == "技术员A\n2026.08.25"
    assert records[0]["field_145"] == "技术员B\n2026.08.26"
    assert len(records[0]["injections"]) == 12
    assert records[0]["injections"][0] == {
        "sequence": "1", "weighing": "13.74", "retentionTime": "4.208",
        "peakArea": "1177629", "concentration": "30.49", "field_134": "44.4",
    }
    assert records[0]["injections"][6] == {
        "sequence": "1", "weighing": "13.74", "retentionTime": "4.205",
        "peakArea": "766489", "concentration": "32.59", "field_134": "47.4",
    }
    assert records[0]["aRetentionRsd"] == "0.1"
    assert records[0]["aContentRsd"] == "2.8"
    assert records[0]["field_137"] == "0.1"
    assert records[0]["field_138"] == "1.1"
    assert records[0]["field_139"] == "（47.5，48.5）"
    assert records[0]["field_140"] == "（190，194）"
    assert records[0]["field_141"] == "5.0"
    assert records[0]["field_142"] == "（44.6，47.5）"
    assert records[0]["field_143"] == "（178，190）"
    assert not payload["_meta"]["warnings"]


def test_required_join_source_fails_instead_of_silent_gap(tmp_path: Path) -> None:
    workbook = Workbook()
    workbook.active.title = "人员"
    path = tmp_path / "missing.xlsx"
    workbook.save(path)
    field = {"fieldCode": "group.person", "cardinality": "MANY",
             "legacyJsonPath": "$.group[*].person"}
    rule = {"fieldCode": field["fieldCode"], "sourceType": "EXCEL", "enabled": True,
            "config": {"mode": "REPEAT_BLOCK", "sheet": "人员", "repeatCount": 1,
                       "rowStart": 1, "rowEnd": 1, "required": True,
                       "valueMode": "JOIN_CELLS", "valueSources": [{"sheet": "人员", "row": 1, "column": 1}]}}
    with pytest.raises(ExcelRuleError, match="字段 group.person 提取失败"):
        extract_excel_fields(path, [field], [rule])


def test_join_literal_label_does_not_need_an_excel_label(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "日期"
    sheet["A1"] = "2026.08.25"
    path = tmp_path / "date.xlsx"
    workbook.save(path)
    field = {"fieldCode": "group.person", "cardinality": "MANY",
             "legacyJsonPath": "$.group[*].person"}
    config = {"mode": "REPEAT_BLOCK", "sheet": "日期", "repeatCount": 1,
              "rowStart": 1, "rowEnd": 1, "required": True,
              "valueMode": "JOIN_CELLS", "joinSeparator": "\n",
              "valueSources": [{"literal": "技术员A"}, {"sheet": "日期", "row": 1, "column": 1}]}
    rule = {"fieldCode": field["fieldCode"], "sourceType": "EXCEL", "enabled": True,
            "config": config}

    payload = extract_excel_fields(path, [field], [rule])
    assert payload["group"][0]["person"] == "技术员A\n2026.08.25"

    config["valueSources"][0]["sheet"] = "日期"
    with pytest.raises(ExcelRuleError, match="固定文字来源只能配置非空 literal"):
        extract_excel_fields(path, [field], [rule])
