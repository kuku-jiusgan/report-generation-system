import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.ai_field_generator import AiGenerationError, _response_content, generate_ai_text, render_ai_prompt


def test_response_content_supports_text_parts() -> None:
    content, has_reasoning = _response_content({
        "choices": [{"message": {"content": [
            {"type": "text", "text": "第一段"},
            {"type": "output_text", "text": "第二段"},
        ], "reasoning_content": ""}}],
    })

    assert content == "第一段第二段"
    assert not has_reasoning


def test_response_content_marks_reasoning_only_response() -> None:
    content, has_reasoning = _response_content({
        "choices": [{"message": {"content": "", "reasoning_content": "思考过程"}}],
    })

    assert content == ""
    assert has_reasoning


def test_generate_uses_service_output_settings_when_rule_has_no_override() -> None:
    response = MagicMock()
    response.read.return_value = json.dumps({
        "choices": [{"message": {"content": "生成结果"}}],
    }).encode()
    response.__enter__.return_value = response
    captured: dict[str, object] = {}

    def open_request(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return response

    with patch("backend.app.services.ai_field_generator.get_settings", return_value=object()), \
         patch("backend.app.services.ai_field_generator.load_ai_service_config", return_value={
             "baseUrl": "https://example.test", "apiKey": "key", "model": "model",
             "timeout": 17, "maxTokens": 1600, "thinkingEnabled": True,
         }), \
         patch("backend.app.services.ai_field_generator.urllib.request.urlopen", side_effect=open_request):
        result = generate_ai_text("field", {"config": {"promptTemplate": "测试"}}, {})

    assert result == "生成结果"
    assert captured["timeout"] == 17.0
    assert captured["payload"]["max_tokens"] == 1600
    assert captured["payload"]["thinking"] == {"type": "enabled"}


def test_generate_prefers_rule_max_length_over_service_default() -> None:
    response = MagicMock()
    response.read.return_value = b'{"choices":[{"message":{"content":"ok"}}]}'
    response.__enter__.return_value = response
    captured: dict[str, object] = {}

    def open_request(request, timeout):
        captured["payload"] = json.loads(request.data)
        return response

    with patch("backend.app.services.ai_field_generator.get_settings", return_value=object()), \
         patch("backend.app.services.ai_field_generator.load_ai_service_config", return_value={
             "baseUrl": "https://example.test", "apiKey": "key", "model": "model",
             "timeout": 60, "maxTokens": 1600, "thinkingEnabled": False,
         }), \
         patch("backend.app.services.ai_field_generator.urllib.request.urlopen", side_effect=open_request):
        generate_ai_text("field", {"config": {"promptTemplate": "测试", "maxLength": 240}}, {})

    assert captured["payload"]["max_tokens"] == 240
    assert captured["payload"]["thinking"] == {"type": "disabled"}


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
