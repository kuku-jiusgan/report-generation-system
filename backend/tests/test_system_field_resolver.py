from backend.app.services.system_field_resolver import resolve_system_fields


FIELDS = [
    {"fieldCode": "sample.name", "legacyJsonPath": "$.sample.name", "enabled": True},
    {"fieldCode": "report.title", "legacyJsonPath": "$.report.title", "enabled": True},
    {"fieldCode": "result.total", "legacyJsonPath": "$.result.total", "enabled": True},
]


def rule(field: str, source: str, priority: int, config: dict, rule_id: int) -> dict:
    return {
        "id": rule_id, "fieldCode": field, "name": f"rule-{rule_id}",
        "sourceType": source, "priority": priority, "config": config, "enabled": True,
    }


def test_priority_fallback_and_text_composition() -> None:
    payload = {"sample": {"name": "阿司匹林"}}
    report_data: dict = {"source_payloads": {"AI": {}}}
    rules = [
        rule("sample.name", "AI", 10, {}, 1),
        rule("sample.name", "LIMS", 20, {}, 2),
        rule("report.title", "CALCULATED", 30, {
            "dependencies": ["sample.name"], "textTemplate": "{sample.name}分析报告",
        }, 3),
    ]

    resolved = resolve_system_fields(FIELDS, rules, payload, report_data)

    assert resolved["sample"]["name"] == "阿司匹林"
    assert resolved["report"]["title"] == "阿司匹林分析报告"
    assert report_data["field_sources"]["sample.name"]["ruleId"] == 2


def test_formula_uses_resolved_dependency_values() -> None:
    fields = [
        {"fieldCode": "a", "legacyJsonPath": "$.a", "enabled": True},
        {"fieldCode": "b", "legacyJsonPath": "$.b", "enabled": True},
        {"fieldCode": "total", "legacyJsonPath": "$.total", "enabled": True},
    ]
    rules = [
        rule("a", "FIXED", 1, {"value": "2"}, 1),
        rule("b", "FIXED", 1, {"value": "3"}, 2),
        rule("total", "CALCULATED", 1, {
            "dependencies": ["a", "b"], "expression": "{a}+{b}", "precision": 0,
        }, 3),
    ]

    resolved = resolve_system_fields(fields, rules, {}, {})

    assert str(resolved["total"]) == "5"


def test_pdf_rule_reads_original_extracted_value() -> None:
    field = [{"fieldCode": "sample.name", "legacyJsonPath": "$.sample.name", "enabled": True}]
    report_data = {"original_values": {"sample.name": "PDF样品"}}

    resolved = resolve_system_fields(
        field, [rule("sample.name", "PDF", 1, {}, 7)], {}, report_data,
    )

    assert resolved["sample"]["name"] == "PDF样品"
    assert report_data["field_sources"]["sample.name"]["type"] == "PDF"


def test_excel_rule_reads_imported_source_payload() -> None:
    field = [{"fieldCode": "sample.name", "legacyJsonPath": "$.sample.name", "enabled": True}]
    report_data = {"source_payloads": {"EXCEL": {"rows": [{"name": "EXCEL样品"}]}}}

    resolved = resolve_system_fields(
        field, [rule("sample.name", "EXCEL", 1, {"sourcePath": "$.rows[*].name"}, 8)],
        {}, report_data,
    )

    assert resolved["sample"]["name"] == ["EXCEL样品"]
    assert report_data["field_sources"]["sample.name"]["type"] == "EXCEL"


def test_excel_many_fields_keep_record_indexes_aligned() -> None:
    fields = [
        {"fieldCode": "specificity.impurityName", "legacyJsonPath": "$.specificity[*].impurityName", "enabled": True},
        {"fieldCode": "specificity.peakArea", "legacyJsonPath": "$.specificity[*].peakArea", "enabled": True},
    ]
    excel = {"specificity": [
        {"impurityName": "杂质D", "peakArea": 10},
        {"impurityName": "杂质A2", "peakArea": 20},
    ]}
    rules = [
        rule("specificity.impurityName", "EXCEL", 1, {"sourcePath": "$.specificity[*].impurityName"}, 10),
        rule("specificity.peakArea", "EXCEL", 1, {"sourcePath": "$.specificity[*].peakArea"}, 11),
    ]

    resolved = resolve_system_fields(fields, rules, {}, {"source_payloads": {"EXCEL": excel}})

    assert resolved["specificity"] == [
        {"impurityName": "杂质D", "peakArea": 10},
        {"impurityName": "杂质A2", "peakArea": 20},
    ]
