import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.management_api import create_management_router
from backend.app.services.ai_field_generator import AiGenerationError, render_ai_prompt
from backend.app.services.ai_report_context import report_ai_context


CONFIG = {
    "contextVariables": [
        {"groupCode": "results", "required": True},
        {"fieldCode": "results.rsd", "mode": "JOIN_UNIQUE", "suffix": "%", "separator": "、"},
        {"fieldCode": "results.name", "mode": "COUNT_UNIQUE"},
    ],
    "promptTemplate": "{{results}}；RSD：{{results.rsd}}；数量：{{results.name}}",
}
RECORDS = [{"name": "测试甲", "rsd": 1.4}, {"name": "测试乙", "rsd": 0.3}]
FIELDS = [
    {"fieldCode": "results.rsd", "collectionCode": "results",
     "legacyJsonPath": "$.results[*].rsd", "label": "RSD"},
    {"fieldCode": "results.name", "collectionCode": "results",
     "legacyJsonPath": "$.results[*].name", "label": "名称"},
]
EXCEL_RULES = [
    {"fieldCode": field["fieldCode"], "sourceType": "EXCEL", "enabled": True, "config": {}}
    for field in FIELDS
]


def generation(source="EXCEL"):
    return {
        "id": "generation-a",
        "resolved_data": {"original_values": {"results.rsd": [99]}},
        "generation_snapshot": {
            "resolved_data": {"source_payloads": {source: {"results": RECORDS}}},
            "original_values": {"results.rsd": [1.4, 0.3], "results.name": ["测试甲", "测试乙"]},
        },
    }


@pytest.mark.parametrize("source", ["EXCEL", "LIMS"])
def test_report_snapshot_supplies_raw_values_and_ai_formatted_context(source):
    imported = report_ai_context(generation(source), CONFIG)
    assert imported["values"]["results"] == RECORDS
    assert json.loads(imported["context"]["results"]) == RECORDS
    assert imported["context"]["results.rsd"] == "1.4%、0.3%"
    assert imported["context"]["results.name"] == "2"
    assert imported["missing"] == []
    prompt, context = render_ai_prompt(CONFIG, imported["values"])
    assert context == imported["context"]
    assert "数量：2" in prompt


def test_field_code_does_not_fallback_to_group_payload():
    config = {
        "contextVariables": [{"fieldCode": "results", "mode": "ALL", "required": True}],
        "promptTemplate": "试验数据：{{results}}",
    }

    imported = report_ai_context(generation("LIMS"), config)

    assert imported["missing"] == ["results"]
    assert imported["values"]["results"] is None


@pytest.mark.parametrize("source", ["EXCEL", "LIMS"])
def test_extracted_fields_missing_from_original_values_use_catalog_paths(source):
    item = generation(source)
    item["generation_snapshot"]["original_values"] = {}

    imported = report_ai_context(item, CONFIG, context_fields=FIELDS)

    assert imported["missing"] == []
    assert imported["values"]["results.rsd"] == [1.4, 0.3]
    assert imported["context"]["results.rsd"] == "1.4%、0.3%"
    assert imported["context"]["results.name"] == "2"


def test_nested_extracted_field_uses_its_standard_path():
    item = generation()
    item["generation_snapshot"]["original_values"] = {}
    item["generation_snapshot"]["resolved_data"]["source_payloads"]["EXCEL"]["results"] = [
        {"summary": {"rsd": 1.4}}, {"summary": {"rsd": 0.3}},
    ]
    config = {"contextVariables": [{"fieldCode": "results.rsd", "required": True}],
              "promptTemplate": "{{results.rsd}}"}
    fields = [{"fieldCode": "results.rsd", "legacyJsonPath": "$.results[*].summary.rsd"}]

    imported = report_ai_context(item, config, context_fields=fields)

    assert imported["values"]["results.rsd"] == [1.4, 0.3]
    assert imported["missing"] == []


def test_each_generation_uses_its_own_snapshot():
    first, second = generation(), generation()
    second["generation_snapshot"]["original_values"]["results.rsd"] = [2.0]
    assert report_ai_context(first, CONFIG)["context"]["results.rsd"] == "1.4%、0.3%"
    assert report_ai_context(second, CONFIG)["context"]["results.rsd"] == "2.0%"


def test_missing_values_are_reported_without_reading_current_report():
    item = generation()
    item["generation_snapshot"]["original_values"] = {}
    imported = report_ai_context(item, CONFIG)
    assert imported["values"]["results.rsd"] is None
    assert set(imported["missing"]) == {"results.rsd", "results.name"}


def test_missing_catalog_path_still_reports_required_field():
    item = generation()
    item["generation_snapshot"]["original_values"] = {}
    item["generation_snapshot"]["resolved_data"]["source_payloads"]["EXCEL"] = {}

    imported = report_ai_context(item, CONFIG, context_fields=FIELDS)

    assert set(imported["missing"]) == {"results", "results.rsd", "results.name"}


def test_does_not_merge_different_source_namespaces():
    item = generation()
    resolved_data = item["generation_snapshot"]["resolved_data"]
    resolved_data["source_payloads"] = {
        "EXCEL": {}, "LIMS": {"results": RECORDS},
    }
    resolved_data["active_source_type"] = "EXCEL"
    assert "results" in report_ai_context(item, CONFIG)["missing"]


def test_history_context_uses_group_member_rules_instead_of_active_report_source():
    item = generation()
    resolved_data = item["generation_snapshot"]["resolved_data"]
    resolved_data["source_payloads"]["LIMS"] = {"results": []}
    resolved_data["active_source_type"] = "LIMS"

    imported = report_ai_context(
        item, CONFIG, context_fields=FIELDS, context_rules=EXCEL_RULES,
    )

    assert imported["values"]["results"] == RECORDS
    assert imported["missing"] == []


def test_history_context_rejects_group_with_conflicting_direct_sources():
    item = generation()
    resolved_data = item["generation_snapshot"]["resolved_data"]
    resolved_data["source_payloads"]["LIMS"] = {
        "results": RECORDS,
    }
    resolved_data["active_source_type"] = "EXCEL"
    rules = [
        EXCEL_RULES[0],
        {"fieldCode": FIELDS[1]["fieldCode"], "sourceType": "LIMS", "enabled": True, "config": {}},
    ]

    with pytest.raises(AiGenerationError, match="同时选择了多个直接来源"):
        report_ai_context(item, CONFIG, context_fields=FIELDS, context_rules=rules)


def test_history_context_rejects_missing_selected_source_payload():
    item = generation("LIMS")
    item["generation_snapshot"]["resolved_data"]["active_source_type"] = "LIMS"

    with pytest.raises(AiGenerationError, match="缺少已选来源载荷：EXCEL"):
        report_ai_context(item, CONFIG, context_fields=FIELDS, context_rules=EXCEL_RULES)


@pytest.mark.parametrize("snapshot", [None, {}, {"resolved_data": {}}])
def test_legacy_snapshot_is_rejected(snapshot):
    item = generation()
    item["generation_snapshot"] = snapshot
    with pytest.raises(AiGenerationError, match="快照"):
        report_ai_context(item, CONFIG)


def test_context_api_returns_values_and_reports_invalid_records(tmp_path):
    class Database:
        def list_lims_fields(self, include_disabled=False):
            return []

        def list_system_field_rules(self):
            return []

        def get_generation(self, identifier):
            return {"ok": generation(), "legacy": {"id": "legacy"}}.get(identifier)

    class Auth:
        def require(self, permission):
            def actor():
                return {"permissions": [permission]}
            return actor

    app = FastAPI()
    app.include_router(create_management_router(Database(), Settings(data_dir=tmp_path), Auth()))
    with TestClient(app) as client:
        response = client.post("/api/v1/admin/report-history/ok/ai-context", json={"config": CONFIG})
        assert response.status_code == 200
        assert response.json()["context"]["results.name"] == "2"
        assert client.post("/api/v1/admin/report-history/absent/ai-context", json={"config": CONFIG}).status_code == 404
        assert client.post("/api/v1/admin/report-history/legacy/ai-context", json={"config": CONFIG}).status_code == 422
