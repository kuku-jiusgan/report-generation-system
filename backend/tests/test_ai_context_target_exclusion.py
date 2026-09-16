from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from backend.app.admin_routes import rule_catalog
from backend.app.services import system_field_resolver
from backend.app.services.ai_context_inputs import prepare_ai_context
from backend.app.services.ai_field_generator import AiGenerationError, render_ai_prompt
from backend.app.services.ai_report_context import report_ai_context


FIELD = {"fieldCode": "results.conclusion", "collectionCode": "results",
         "legacyJsonPath": "$.results[*].summary.conclusion"}
RECORDS = [
    {"name": "测试甲", "summary": {"rsd": 1.4, "conclusion": "旧结论甲"},
     "injections": [{"area": 100, "conclusion": "进样备注"}]},
    {"name": "测试乙", "summary": {"rsd": 0.3, "conclusion": "旧结论乙"}},
]
CLEAN = deepcopy(RECORDS)
for record in CLEAN:
    del record["summary"]["conclusion"]


def config(mode):
    return {"contextVariables": [{"groupCode": "results", "mode": mode, "required": True}],
            "promptTemplate": "试验数据：{{results}}"}


def test_exclusion_is_path_specific_and_does_not_mutate_inputs():
    values = {"results": deepcopy(RECORDS), FIELD["fieldCode"]: "旧结论",
              "other": {"summary": {"conclusion": "其他编组结论"}}}
    before = deepcopy(values)
    inputs, current = prepare_ai_context(config("CURRENT_RECORD"), values, RECORDS[0], FIELD)
    assert inputs["results"] == CLEAN
    assert current == CLEAN[0]
    assert FIELD["fieldCode"] not in inputs
    assert inputs["other"] == values["other"]
    assert values == before
    assert RECORDS[0]["summary"]["conclusion"] == "旧结论甲"


def test_target_in_nested_array_uses_full_standard_path():
    field = {**FIELD, "legacyJsonPath": "$.results[*].injections[*].conclusion"}
    inputs, current = prepare_ai_context(config("CURRENT_RECORD"), {"results": RECORDS}, RECORDS[0], field)
    assert "conclusion" not in inputs["results"][0]["injections"][0]
    assert "conclusion" not in current["injections"][0]
    assert current["summary"]["conclusion"] == "旧结论甲"


@pytest.mark.parametrize("group", ["narrative", "Objective"])
def test_formal_generation_allows_target_group_without_source_data(monkeypatch, group):
    field = {"fieldCode": f"{group}.text", "collectionCode": group,
             "legacyJsonPath": f"$.{group}.text"}
    rule = {"fieldCode": field["fieldCode"], "sourceType": "AI",
            "config": {"promptTemplate": "根据输入事实生成段落"}}
    captured = []

    def generate(code, rule, values, current_record=None, context_fields=None):
        captured.append(values)
        return "新段落"

    monkeypatch.setattr(system_field_resolver, "generate_ai_text", generate)
    payload, data = {}, {}
    system_field_resolver.resolve_system_fields([field], [rule], payload, data)
    assert len(captured) == 1
    assert payload[group] == {"text": "新段落"}
    assert not data.get("warnings")


def test_target_exclusion_still_rejects_malformed_parent():
    with pytest.raises(AiGenerationError, match="父级必须是对象"):
        prepare_ai_context(config("JOIN_UNIQUE"), {"results": [{"summary": "错误结构"}]}, None, FIELD)


@pytest.mark.parametrize("mode", ["JOIN_UNIQUE", "CURRENT_RECORD"])
def test_formal_generation_receives_sanitized_context_and_writes_only_new_output(monkeypatch, mode):
    payload = {"results": deepcopy(RECORDS)}
    captured = []

    def generate(code, rule, values, current_record=None, context_fields=None):
        _, context = render_ai_prompt(rule["config"], values, current_record)
        captured.append(json.loads(context["results"]))
        return "新结论"

    monkeypatch.setattr(system_field_resolver, "generate_ai_text", generate)
    rules = [{"fieldCode": FIELD["fieldCode"], "sourceType": "AI", "config": config(mode)}]
    system_field_resolver.resolve_system_fields([FIELD], rules, payload, {})
    assert captured == (CLEAN if mode == "CURRENT_RECORD" else [CLEAN])
    assert payload["results"][0]["summary"]["conclusion"] == "新结论"
    if mode == "CURRENT_RECORD":
        assert payload["results"][1]["summary"]["conclusion"] == "新结论"
    assert payload["results"][0]["injections"] == RECORDS[0]["injections"]


@pytest.mark.parametrize("mode", ["JOIN_UNIQUE", "CURRENT_RECORD"])
def test_snapshot_import_and_test_generation_share_exclusion(monkeypatch, mode):
    generation = {"generation_snapshot": {
        "resolved_data": {"source_payloads": {"EXCEL": {"results": deepcopy(RECORDS)}}},
        "original_values": {FIELD["fieldCode"]: ["旧结论甲", "旧结论乙"]},
    }}
    before = deepcopy(generation)
    imported = report_ai_context(generation, config(mode), "results",
                                 0 if mode == "CURRENT_RECORD" else None, FIELD)
    assert json.loads(imported["context"]["results"]) == (CLEAN[0] if mode == "CURRENT_RECORD" else CLEAN)
    if mode == "CURRENT_RECORD":
        assert imported["records"] == CLEAN
    assert generation == before
    captured = []

    def generate(code, rule, values, current_record, context_fields=None):
        _, context = render_ai_prompt(rule["config"], values, current_record)
        captured.append(context)
        return "测试结论"

    monkeypatch.setattr(rule_catalog, "generate_ai_text", generate)
    repository = SimpleNamespace(database=SimpleNamespace(
        get_lims_field=lambda code: FIELD, list_lims_fields=lambda include_disabled: []))
    router = APIRouter()
    rule_catalog.register_rule_catalog_routes(router, repository)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        # 即使请求携带未清理的旧数据，执行入口也必须重新排除目标字段。
        response = client.post("/system-field-rules/ai-preview", json={
            "fieldCode": FIELD["fieldCode"], "config": config(mode), "execute": True,
            "values": {"results": RECORDS},
            "currentRecord": RECORDS[0] if mode == "CURRENT_RECORD" else None,
        })
    assert response.status_code == 200
    assert response.json()["context"] == imported["context"]
    assert captured == [imported["context"]]


@pytest.mark.parametrize("rule_config", [
    {"contextVariables": [{"fieldCode": FIELD["fieldCode"], "defaultValue": "默认结论"}]},
    {"inputFields": [FIELD["fieldCode"]]},
])
def test_explicit_self_reference_is_rejected(rule_config):
    with pytest.raises(AiGenerationError, match="不能引用正在生成的字段自身"):
        prepare_ai_context(rule_config, {}, None, FIELD)


def test_invalid_target_metadata_is_rejected():
    with pytest.raises(AiGenerationError, match="有效的标准数据路径"):
        prepare_ai_context(config("JOIN_UNIQUE"), {}, None, {"fieldCode": "target"})
