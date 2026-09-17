import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.admin_routes.rule_catalog import _validate_system_rule
from backend.app.services import ai_field_generator
from backend.app.services.ai_field_generator import AiGenerationError, _response_content, generate_ai_text, render_ai_prompt
from backend.app.services.ai_multimodal import build_message_content


PNG_DATA_URL = "data:image/png;base64,iVBORw0KGgo="
JPEG_DATA_URL = "data:image/jpeg;base64,/9j/2Q=="


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


def test_build_message_content_keeps_text_requests_unchanged() -> None:
    assert build_message_content("仅包含文本") == "仅包含文本"


def test_build_message_content_extracts_images_and_deduplicates_them() -> None:
    content = build_message_content(
        f'{{"残差图":"{PNG_DATA_URL}","回归曲线图":"{JPEG_DATA_URL}",'
        f'"重复残差图":"{PNG_DATA_URL}"}}'
    )

    assert isinstance(content, list)
    assert content[0] == {
        "type": "text",
        "text": '{"残差图":"[图片 1，已作为视觉输入附加]",'
                '"回归曲线图":"[图片 2，已作为视觉输入附加]",'
                '"重复残差图":"[图片 1，已作为视觉输入附加]"}',
    }
    assert content[1] == {"type": "image_url", "image_url": {"url": PNG_DATA_URL}}
    assert content[2] == {"type": "image_url", "image_url": {"url": JPEG_DATA_URL}}


def test_build_message_content_rejects_invalid_image_data_url() -> None:
    with pytest.raises(ValueError, match="格式错误"):
        build_message_content("图片：data:image/png;base64,不是Base64")


def test_generate_sends_images_as_multimodal_content() -> None:
    response = MagicMock()
    response.read.return_value = b'{"choices":[{"message":{"content":"ok"}}]}'
    response.__enter__.return_value = response
    captured: dict[str, object] = {}

    def open_request(request, timeout):
        captured["payload"] = json.loads(request.data)
        return response

    config = {
        "contextVariables": [{"fieldCode": "chart", "mode": "ALL"}],
        "promptTemplate": "请分析：{{chart}}",
    }
    with patch("backend.app.services.ai_field_generator.get_settings", return_value=object()), \
         patch("backend.app.services.ai_field_generator.load_ai_service_config", return_value={
             "baseUrl": "https://example.test", "apiKey": "key", "model": "vision-model",
             "timeout": 60, "maxTokens": 800, "thinkingEnabled": False,
         }), \
         patch("backend.app.services.ai_field_generator.urllib.request.urlopen", side_effect=open_request):
        generate_ai_text("field", {"config": config}, {"chart": PNG_DATA_URL})

    content = captured["payload"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "请分析：[图片 1，已作为视觉输入附加]"}
    assert content[1] == {"type": "image_url", "image_url": {"url": PNG_DATA_URL}}


def test_generate_rejects_request_over_provider_limit(monkeypatch) -> None:
    monkeypatch.setattr(ai_field_generator, "MAX_AI_REQUEST_BYTES", 100)
    monkeypatch.setattr(ai_field_generator, "get_settings", lambda: object())
    monkeypatch.setattr(ai_field_generator, "load_ai_service_config", lambda required: {
        "baseUrl": "https://example.test", "apiKey": "key", "model": "vision-model",
        "timeout": 60, "maxTokens": 800, "thinkingEnabled": False,
    })

    with pytest.raises(AiGenerationError, match="超过 48 MiB"):
        generate_ai_text("field", {"config": {"promptTemplate": "足够长的请求正文"}}, {})


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


def test_validate_ai_rule_keeps_rule_fields_when_context_is_configured() -> None:
    repository = MagicMock()
    repository.database.get_lims_field.return_value = {"fieldCode": "narrative.summary"}
    repository.database.list_lims_fields.return_value = [
        {"fieldCode": "narrative.summary"},
        {"fieldCode": "project.name"},
    ]
    rule = {
        "fieldCode": "narrative.summary",
        "name": "AI 生成摘要",
        "sourceType": "AI",
        "priority": 20,
        "enabled": True,
        "config": {
            "contextVariables": [{"fieldCode": "project.name", "required": False}],
            "promptTemplate": "项目：{{project.name}}",
        },
    }

    with patch("backend.app.admin_routes.rule_catalog.list_system_field_groups", return_value=[]):
        validated = _validate_system_rule(repository, rule)

    assert validated["name"] == "AI 生成摘要"
    assert validated["fieldCode"] == "narrative.summary"
    assert validated["priority"] == 20
