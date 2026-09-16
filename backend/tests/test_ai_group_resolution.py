import json

import pytest

from backend.app.services import system_field_resolver
from backend.app.services.ai_field_generator import AiGenerationError, render_ai_prompt


GROUP = "systemSuitability"
CONFIG = {
    "contextVariables": [{"groupCode": GROUP, "required": True}],
    "promptTemplate": "试验数据：{{systemSuitability}}",
}
RECORDS = [{
    "impurityName": "测试杂质",
    "injections": [{"peakArea": 100}, {"peakArea": 102}],
    "summary": {"peakAreaRsd": 1.4},
}]


def make_rule(code, source, config):
    return {"fieldCode": code, "sourceType": source, "config": config, "enabled": True}


def capture_prompts(monkeypatch):
    contexts = []

    def generate(code, rule, values, current_record=None, context_fields=None):
        _, context = render_ai_prompt(rule["config"], values, current_record)
        contexts.append(json.loads(context[GROUP]))
        return "测试结论"

    monkeypatch.setattr(system_field_resolver, "generate_ai_text", generate)
    return contexts


@pytest.mark.parametrize("member_path", [
    "$.systemSuitability[*].injections[*].peakArea",
    "$.systemSuitability[*].summary.peakAreaRsd",
])
def test_ai_receives_entire_group_for_nested_first_member(monkeypatch, member_path):
    contexts = capture_prompts(monkeypatch)
    fields = [
        {"fieldCode": "member", "collectionCode": GROUP, "legacyJsonPath": member_path},
        {"fieldCode": "conclusion", "legacyJsonPath": "$.custom.conclusion"},
    ]
    payload = {GROUP: RECORDS}
    system_field_resolver.resolve_system_fields(
        fields, [make_rule("conclusion", "AI", CONFIG)], payload, {},
    )
    assert contexts == [RECORDS]
    assert payload["custom"]["conclusion"] == "测试结论"


def test_ai_retries_with_group_created_by_extraction(monkeypatch):
    contexts = capture_prompts(monkeypatch)
    fields = [
        {"fieldCode": "conclusion", "legacyJsonPath": "$.custom.conclusion"},
        {"fieldCode": "member", "collectionCode": GROUP,
         "legacyJsonPath": "$.systemSuitability[*].impurityName"},
    ]
    rules = [
        make_rule("conclusion", "AI", CONFIG),
        make_rule("member", "EXCEL", {}),
    ]
    payload = {}
    report_data = {"source_payloads": {"EXCEL": {GROUP: RECORDS}}}
    system_field_resolver.resolve_system_fields(fields, rules, payload, report_data)
    assert len(contexts) == 1
    assert contexts[0] == [{"impurityName": "测试杂质"}]
    assert contexts[0] == payload[GROUP]
    assert payload["custom"]["conclusion"] == "测试结论"
    assert not report_data.get("warnings")


def test_context_group_does_not_require_member_in_resolved_fields(monkeypatch):
    contexts = capture_prompts(monkeypatch)
    system_field_resolver.resolve_system_fields(
        [{"fieldCode": "conclusion", "legacyJsonPath": "$.custom.conclusion"}],
        [make_rule("conclusion", "AI", CONFIG)], {GROUP: RECORDS}, {},
    )
    assert contexts == [RECORDS]


def test_missing_required_group_stops_prompt_generation():
    with pytest.raises(AiGenerationError, match="AI 上下文字段缺失：systemSuitability"):
        render_ai_prompt(CONFIG, {})
