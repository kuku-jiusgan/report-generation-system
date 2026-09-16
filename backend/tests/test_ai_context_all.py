import json

import pytest

from backend.app.services.ai_field_generator import (
    AiGenerationError, needs_per_record_generation, render_ai_prompt,
)


RECORDS = [
    {"name": "测试甲", "injections": [{"area": 100}, {"area": 102}]},
    {"name": "测试乙", "injections": [{"area": 200}]},
]


@pytest.mark.parametrize("mode", ["ALL", None, "", "FIRST", "JOIN_UNIQUE", "COUNT_UNIQUE"])
def test_group_all_preserves_every_record_and_nested_value(mode):
    config = {"contextVariables": [{"groupCode": "results", "mode": mode}],
              "promptTemplate": "{{results}}"}
    prompt, context = render_ai_prompt(config, {"results": RECORDS})
    assert json.loads(prompt) == RECORDS
    assert json.loads(context["results"]) == RECORDS
    assert not needs_per_record_generation(config)


def test_current_record_remains_distinct_from_all_information():
    config = {"contextVariables": [{"groupCode": "results", "mode": "CURRENT_RECORD"}],
              "promptTemplate": "{{results}}"}
    prompt, _ = render_ai_prompt(config, {"results": RECORDS}, RECORDS[1])
    assert json.loads(prompt) == RECORDS[1]
    assert needs_per_record_generation(config)


@pytest.mark.parametrize("value", [["测试甲", "测试甲", "测试乙"], RECORDS, {"injections": [100, 100, 102]}])
def test_single_field_all_preserves_complete_value(value):
    config = {"contextVariables": [{"fieldCode": "results.value", "mode": "ALL", "suffix": "%"}],
              "promptTemplate": "{{results.value}}"}
    prompt, context = render_ai_prompt(config, {"results.value": value, "unrelated": "不能传入"})
    assert json.loads(prompt) == value
    assert json.loads(context["results.value"]) == value
    assert not needs_per_record_generation(config)


@pytest.mark.parametrize("value", [0, False, "测试甲"])
def test_single_field_all_preserves_scalar(value):
    prompt, _ = render_ai_prompt({"contextVariables": [{"fieldCode": "value", "mode": "ALL"}],
                                 "promptTemplate": "{{value}}"}, {"value": value})
    assert prompt == str(value)


@pytest.mark.parametrize("value", [None, "", [], {}])
def test_single_field_all_missing_required_value(value):
    with pytest.raises(AiGenerationError, match="AI 上下文字段缺失"):
        render_ai_prompt({"contextVariables": [{"fieldCode": "value", "mode": "ALL"}],
                          "promptTemplate": "{{value}}"}, {"value": value})
