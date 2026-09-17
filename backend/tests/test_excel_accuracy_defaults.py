from pathlib import Path
from unittest.mock import Mock, patch

from backend.app.services.excel_field_extractor import extract_excel_fields
from backend.app.services.excel_rule_defaults import (
    ACCURACY_FIELDS, EXCEL_FIELD_PATHS, _rule_config, ensure_excel_field_rules,
)


ROOT = Path(__file__).parents[2]
WORKBOOK = ROOT / "文霞-标准计算表-动态-V56-解锁版-XM2026219-03.xlsm"
GROUP = "accuracyResults"


def _fields_and_rules():
    fields, rules = [], []
    for index, code in enumerate(sorted(ACCURACY_FIELDS), 1):
        path = f"$.{GROUP}[*]." + (
            "injections[*]." if int(code.rsplit("_", 1)[-1]) in
            {61, 62, 64, 67, 68, 69, 70, 71, 72} else
            "summary." if code != "uncategorized.field_060" else ""
        ) + code.rsplit(".", 1)[-1]
        fields.append({"fieldCode": code, "groupCode": GROUP, "cardinality": "MANY",
                       "legacyJsonPath": path})
        rules.append({"id": index, "fieldCode": code, "sourceType": "EXCEL", "enabled": True,
                      "priority": 50, "config": _rule_config(code, path)})
    return fields, rules


def test_accuracy_result_table_comes_from_excel() -> None:
    fields, rules = _fields_and_rules()
    payload = extract_excel_fields(WORKBOOK, fields, rules)
    records = payload[GROUP]

    assert len(records) == 3
    assert [record["field_060"] for record in records] == [
        "3-吡啶磺酸甲酯", "3-吡啶磺酸乙酯", "3-吡啶磺酸异丙酯",
    ]
    assert len(records[0]["injections"]) == 9
    assert records[0]["injections"][0] == {
        "field_061": 1, "field_062": 13.82, "field_064": 1.29,
        "field_067": "LOQ加标", "field_068": 25.8, "field_069": 0,
        "field_070": 30.1, "field_071": 85.7, "field_072": 84,
    }
    assert records[0]["injections"][2]["field_067"] == "LOQ加标"
    assert records[0]["injections"][2]["field_070"] == 30.1
    assert records[0]["injections"][2]["field_072"] == 84
    assert records[0]["injections"][3]["field_067"] == "100%加标"
    assert records[1]["injections"][0]["field_071"] == 95.7
    assert records[0]["summary"] == {
        "field_073": 80, "field_074": 4.8,
        "field_075": "77.1～83", "field_096": None,
    }
    assert not payload["_meta"]["warnings"]


def test_accuracy_rules_replace_prior_sources_without_duplicates() -> None:
    database = Mock()
    database.get_lims_field.side_effect = lambda code: (
        {"fieldCode": code, "groupCode": GROUP, "legacyJsonPath": f"$.{GROUP}[*].{code.rsplit('.', 1)[-1]}"}
        if code in ACCURACY_FIELDS else None
    )
    database.list_system_field_rules.side_effect = lambda code: [{
        "id": 100 + int(code.rsplit("_", 1)[-1]), "fieldCode": code,
        "name": "旧规则", "sourceType": "AI" if code.endswith("096") else "LIMS",
    }]
    with patch("backend.app.services.excel_rule_defaults._ensure_repeated_field_contracts"), patch(
        "backend.app.services.excel_rule_defaults._ensure_quantitation_impurity_name_contract"
    ):
        ensure_excel_field_rules(database)

    assert database.save_system_field_rule.call_count == len(ACCURACY_FIELDS)
    for call in database.save_system_field_rule.call_args_list:
        rule, rule_id = call.args
        assert rule["sourceType"] == "EXCEL"
        assert rule["config"]["sheet"] == "准确度"
        assert rule_id == 100 + int(rule["fieldCode"].rsplit("_", 1)[-1])


def test_accuracy_rules_read_each_block_without_guessing_values() -> None:
    fields, rules = _fields_and_rules()
    newest = ROOT / "data/uploads/138a8e58ed954822aa1c414572ba84eb.xlsm"
    payload = extract_excel_fields(newest, fields, rules)

    assert len(payload[GROUP]) == 3
    assert payload[GROUP][0]["injections"][0]["field_067"] == "LOQ加标"
    assert payload[GROUP][0]["injections"][0]["field_071"] is None
    assert any("准确度!K16" in warning for warning in payload["_meta"]["warnings"])
    assert _rule_config("uncategorized.field_075", EXCEL_FIELD_PATHS["uncategorized.field_075"])["pairColumns"] == [6, 11]
