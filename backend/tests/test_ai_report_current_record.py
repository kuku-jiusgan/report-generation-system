import json
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.app.admin_routes import rule_catalog
from backend.app.services.ai_field_generator import AiGenerationError
from backend.app.services.ai_report_context import report_ai_context


CONFIG = {
    "contextVariables": [
        {"groupCode": "results", "mode": "CURRENT_RECORD", "required": True},
        {"fieldCode": "results.rsd", "mode": "CURRENT_RECORD", "required": True},
    ],
    "promptTemplate": "{{results}}，RSD：{{results.rsd}}",
}
RECORDS = [{"name": "测试甲", "rsd": 1.4}, {"name": "测试乙", "rsd": 0.3}]
GENERATION = {
    "generation_snapshot": {
        "resolved_data": {"source_payloads": {"EXCEL": {"results": RECORDS}}},
        "original_values": {},
    },
}


def test_existing_records_require_selection_without_false_missing_warning():
    result = report_ai_context(GENERATION, CONFIG, "results")
    assert result["missing"] == []
    assert result["records"] == RECORDS
    assert result["currentRecord"] is None
    assert result["requiresCurrentRecord"] is True


@pytest.mark.parametrize("index", [0, 1])
def test_selected_snapshot_record_supplies_group_and_field_context(index):
    result = report_ai_context(GENERATION, CONFIG, "results", index)
    assert result["missing"] == []
    assert result["currentRecord"] == RECORDS[index]
    assert json.loads(result["context"]["results"]) == RECORDS[index]
    assert result["context"]["results.rsd"] == str(RECORDS[index]["rsd"])


def test_invalid_record_selection_is_rejected():
    with pytest.raises(AiGenerationError, match="所选编组记录不存在"):
        report_ai_context(GENERATION, CONFIG, "results", 2)
    with pytest.raises(AiGenerationError, match="所属编组"):
        report_ai_context(GENERATION, CONFIG)


def test_test_generation_receives_same_current_record_as_context_preview(monkeypatch):
    result = report_ai_context(GENERATION, CONFIG, "results", 1)
    received = []

    def generate(code, rule, values, current_record, context_fields=None):
        received.append(current_record)
        return "测试结论"

    monkeypatch.setattr(rule_catalog, "generate_ai_text", generate)
    router = APIRouter()
    rule_catalog.register_rule_catalog_routes(router, SimpleNamespace(
        database=SimpleNamespace(list_lims_fields=lambda include_disabled: [])))
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post("/system-field-rules/ai-preview", json={
            "config": CONFIG, "values": result["values"],
            "currentRecord": result["currentRecord"], "execute": True,
        })
        assert response.status_code == 200
        assert response.json()["context"] == result["context"]
        assert response.json()["output"] == "测试结论"
        assert received == [RECORDS[1]]
