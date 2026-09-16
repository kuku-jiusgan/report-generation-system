from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.app.admin_routes import rule_catalog
from backend.app.services import ai_field_generator, system_field_resolver
from backend.app.services.ai_field_generator import AiGenerationError, render_ai_prompt
from backend.app.services.ai_report_context import report_ai_context


FIELDS = [
    {"fieldCode": "custom.name", "collectionCode": "results", "label": "杂质名称",
     "legacyJsonPath": "$.results[*].name"},
    {"fieldCode": "custom.area", "collectionCode": "results", "label": "峰面积",
     "legacyJsonPath": "$.results[*].injections[*].field_016"},
    {"fieldCode": "custom.rsd", "collectionCode": "results", "label": "峰面积RSD（%）",
     "legacyJsonPath": "$.results[*].summary.field_017"},
    {"fieldCode": "custom.other", "collectionCode": "results", "label": "汇总峰面积",
     "legacyJsonPath": "$.results[*].summary.field_016"},
    {"fieldCode": "custom.conclusion", "collectionCode": "results", "label": "结论",
     "legacyJsonPath": "$.results[*].summary.conclusion"},
]
RECORDS = [{"name": "测试杂质", "injections": [{"field_016": 100}],
            "summary": {"field_017": 1.4, "field_016": 100, "conclusion": "旧结论"}}]
LABELED = [{"name（杂质名称）": "测试杂质", "injections": [{"field_016（峰面积）": 100}],
            "summary": {"field_017（峰面积RSD（%））": 1.4, "field_016（汇总峰面积）": 100}}]


def config(mode):
    return {"contextVariables": [{"groupCode": "results", "mode": mode}],
            "promptTemplate": "试验数据：{{results}}"}


@pytest.mark.parametrize("mode", ["JOIN_UNIQUE", "CURRENT_RECORD"])
def test_snapshot_and_ai_preview_label_fields_after_target_exclusion(mode):
    generation = {"generation_snapshot": {"original_values": {},
        "resolved_data": {"source_payloads": {"EXCEL": {"results": deepcopy(RECORDS)}}}}}
    before = deepcopy(generation)
    imported = report_ai_context(generation, config(mode), "results",
                                 0 if mode == "CURRENT_RECORD" else None, FIELDS[-1], FIELDS)
    expected = LABELED[0] if mode == "CURRENT_RECORD" else LABELED
    assert json.loads(imported["context"]["results"]) == expected
    assert "name" in imported["values"]["results"][0]
    assert generation == before
    repository = SimpleNamespace(database=SimpleNamespace(
        get_lims_field=lambda code: FIELDS[-1], list_lims_fields=lambda include_disabled: FIELDS))
    router = APIRouter()
    rule_catalog.register_rule_catalog_routes(router, repository)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post("/system-field-rules/ai-preview", json={
            "fieldCode": "custom.conclusion", "config": config(mode), "values": imported["values"],
            "currentRecord": imported["currentRecord"],
        })
    assert response.status_code == 200
    assert response.json()["context"] == imported["context"]


@pytest.mark.parametrize("mode", ["JOIN_UNIQUE", "CURRENT_RECORD"])
def test_formal_ai_request_uses_labeled_context_without_changing_data_keys(monkeypatch, mode):
    captured = []
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = b'{"choices":[{"message":{"content":"ok"}}]}'

    def open_request(request, timeout):
        captured.append(json.loads(request.data)["messages"][0]["content"])
        return response

    monkeypatch.setattr(ai_field_generator, "get_settings", lambda: object())
    monkeypatch.setattr(ai_field_generator, "load_ai_service_config", lambda required: {
        "baseUrl": "https://example.test", "apiKey": "test", "model": "test", "timeout": 5})
    monkeypatch.setattr(ai_field_generator.urllib.request, "urlopen", open_request)
    payload = {"results": deepcopy(RECORDS)}
    rule = {"fieldCode": "custom.conclusion", "sourceType": "AI", "config": config(mode)}
    system_field_resolver.resolve_system_fields(FIELDS, [rule], payload, {})
    expected = LABELED[0] if mode == "CURRENT_RECORD" else LABELED
    assert json.loads(captured[0].removeprefix("试验数据：")) == expected
    assert payload["results"][0]["name"] == "测试杂质"
    assert payload["results"][0]["summary"]["conclusion"] == "ok"


def test_field_labels_are_path_specific_and_refresh_from_metadata():
    fields = deepcopy(FIELDS)
    prompt, _ = render_ai_prompt(config("JOIN_UNIQUE"), {"results": RECORDS}, context_fields=fields)
    assert '"field_016（峰面积）"' in prompt
    assert '"field_016（汇总峰面积）"' in prompt
    fields[1]["label"] = "进样峰面积"
    prompt, _ = render_ai_prompt(config("JOIN_UNIQUE"), {"results": RECORDS}, context_fields=fields)
    assert '"field_016（进样峰面积）"' in prompt


def test_scalar_field_formatting_keeps_existing_sentence_behavior():
    prompt, context = render_ai_prompt({
        "contextVariables": [{"fieldCode": "custom.rsd", "suffix": "%"}],
        "promptTemplate": "峰面积RSD为{{custom.rsd}}",
    }, {"custom.rsd": [1.4]}, context_fields=FIELDS)
    assert prompt == "峰面积RSD为1.4%"
    assert context == {"custom.rsd": "1.4%"}


def test_conflicting_or_missing_field_names_fail_explicitly():
    with pytest.raises(AiGenerationError, match="字段名称配置冲突"):
        render_ai_prompt(config("JOIN_UNIQUE"), {"results": RECORDS},
                         context_fields=FIELDS + [{**FIELDS[0], "label": "不同名称"}])
    with pytest.raises(AiGenerationError, match="字段缺少名称"):
        render_ai_prompt(config("JOIN_UNIQUE"), {"results": RECORDS},
                         context_fields=[{**FIELDS[0], "label": ""}])


def test_unrelated_catalog_paths_do_not_affect_selected_context():
    unrelated = [
        {"legacyJsonPath": "$.other.value", "label": "名称甲"},
        {"legacyJsonPath": "$.other.value", "label": "名称乙"},
    ]
    prompt, _ = render_ai_prompt(config("JOIN_UNIQUE"), {"results": RECORDS}, context_fields=FIELDS + unrelated)
    assert '"field_016（峰面积）"' in prompt
