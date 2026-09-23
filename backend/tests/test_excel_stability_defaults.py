from pathlib import Path

from backend.app.services.excel_field_extractor import extract_excel_fields
from backend.app.services.excel_rule_defaults import (
    EXCEL_FIELD_PATHS,
    EXCEL_WORKBOOK_LOCATIONS,
    STABILITY_DETAIL_COLUMNS,
    STABILITY_FIELDS,
    _rule_config,
)


ROOT = Path(__file__).parents[2]
WORKBOOK = ROOT / "文霞-标准计算表-动态-V56-解锁版-XM2026219-03.xlsm"
GROUP = "custom_1788404594530"


def _fields_and_rules():
    fields, rules = [], []
    for index, code in enumerate(sorted(STABILITY_FIELDS), 1):
        path = EXCEL_FIELD_PATHS[code]
        fields.append({
            "fieldCode": code,
            "groupCode": GROUP,
            "cardinality": "MANY",
            "legacyJsonPath": path,
        })
        rules.append({
            "id": index,
            "fieldCode": code,
            "sourceType": "EXCEL",
            "priority": 50,
            "enabled": True,
            "config": _rule_config(code, path),
        })
    return fields, rules


def test_solution_stability_result_table_comes_from_excel() -> None:
    fields, rules = _fields_and_rules()

    payload = extract_excel_fields(WORKBOOK, fields, rules)

    records = payload[GROUP]
    assert [record["field_076"] for record in records] == [
        "3-吡啶磺酸甲酯", "3-吡啶磺酸乙酯", "3-吡啶磺酸异丙酯",
    ]
    assert len(records[0]["injections"]) == 6
    assert records[0]["injections"][0] == {
        "field_077": "0h", "field_078": "40.42", "field_079": "-",
        "field_080": "37.27", "field_081": "-",
    }
    assert records[0]["injections"][1] == {
        "field_077": "4.0h", "field_078": "38.52", "field_079": "0.95",
        "field_080": "35.72", "field_081": "0.96",
    }
    assert records[1]["injections"][0]["field_078"] == "37.82"
    assert records[2]["injections"][4]["field_081"] == "0.99"
    assert not payload["_meta"]["warnings"]


def test_solution_stability_rules_follow_nine_row_blocks() -> None:
    name_config = _rule_config(
        "uncategorized.field_076", EXCEL_FIELD_PATHS["uncategorized.field_076"]
    )
    assert (name_config["rowStart"], name_config["rowEnd"], name_config["startColumn"]) == (2, 2, 1)
    assert name_config["rowStep"] == 9

    for code, column in STABILITY_DETAIL_COLUMNS.items():
        config = _rule_config(code, EXCEL_FIELD_PATHS[code])
        assert config["sheet"] == "溶液稳定性"
        assert (config["rowStart"], config["rowEnd"]) == (4, 9)
        assert config["startColumn"] == column
        assert config["rowStep"] == 9
        assert config["repeatCountSource"] == {"sheet": "首页", "row": 8, "column": 2}
        assert config["workbookLocation"] == EXCEL_WORKBOOK_LOCATIONS[code]
