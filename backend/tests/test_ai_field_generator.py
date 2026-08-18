import pytest

from backend.app.services.ai_field_generator import AiGenerationError, render_ai_prompt


def test_render_prompt_formats_list_context_and_defaults() -> None:
    prompt, values = render_ai_prompt({
        "contextVariables": [
            {"fieldCode": "project.name", "required": True, "mode": "FIRST"},
            {"fieldCode": "validation.items", "required": True, "mode": "JOIN_UNIQUE", "separator": "、"},
        ],
        "promptTemplate": "方法：{{project.name}}；项目：{{validation.items}}",
    }, {"project.name": "方法A", "validation.items": ["系统适用性", "系统适用性", "准确度"]})

    assert values["validation.items"] == "系统适用性、准确度"
    assert prompt == "方法：方法A；项目：系统适用性、准确度"


def test_render_prompt_rejects_missing_required_context() -> None:
    with pytest.raises(AiGenerationError, match="上下文字段缺失"):
        render_ai_prompt({
            "contextVariables": [{"fieldCode": "project.name", "required": True}],
            "promptTemplate": "{{project.name}}",
        }, {})


def test_render_prompt_rejects_unresolved_placeholder() -> None:
    with pytest.raises(AiGenerationError, match="未解析"):
        render_ai_prompt({
            "contextVariables": [{"fieldCode": "project.name", "required": False}],
            "promptTemplate": "{{project.name}} {{missing.field}}",
        }, {})
