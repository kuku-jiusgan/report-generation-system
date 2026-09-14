import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from ..config import get_settings
from .ai_service_config import load_ai_service_config


logger = logging.getLogger(__name__)


class AiGenerationError(RuntimeError):
    pass


def _response_content(result: dict[str, Any]) -> tuple[str, bool]:
    """读取 OpenAI 兼容响应正文，并标记是否只有推理内容。"""
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise AiGenerationError("AI 响应缺少 choices 内容")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise AiGenerationError("AI 响应缺少 message 内容")
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "") for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        )
    return str(content or "").strip(), bool(str(message.get("reasoning_content") or "").strip())


def context_variables(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = config.get("contextVariables")
    if isinstance(configured, list):
        return [item for item in configured if isinstance(item, dict) and item.get("fieldCode")]
    return [
        {"fieldCode": str(code), "required": True, "mode": "JOIN_UNIQUE", "separator": "、", "defaultValue": ""}
        for code in config.get("inputFields", [])
    ]


def _format_context(value: Any, variable: dict[str, Any]) -> str:
    """把一个标准字段的取值按上下文变量的取值方式拼成一段文字。

    FIRST 取第一个有效值，COUNT_UNIQUE 取去重后的个数，JOIN_UNIQUE 去重后拼接；
    suffix 加在每个取值后面（例如百分号），这样"1.4%、0.3%"不用在模板里硬拼。
    """
    values = value if isinstance(value, list) else [value]
    normalized = [str(item).strip() for item in values if item not in (None, "")]
    mode = str(variable.get("mode") or "JOIN_UNIQUE")
    if mode == "FIRST":
        return f"{normalized[0]}{variable.get('suffix') or ''}" if normalized else ""
    unique = list(dict.fromkeys(normalized))
    if mode == "COUNT_UNIQUE":
        return str(len(unique)) if unique else ""
    suffix = str(variable.get("suffix") or "")
    return str(variable.get("separator") or "、").join(f"{item}{suffix}" for item in unique)


def resolve_context_values(config: dict[str, Any],
                           values: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """按上下文变量配置解析出占位符取值，并列出缺失的必填字段。"""
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for variable in context_variables(config):
        code = str(variable["fieldCode"])
        text = _format_context(values.get(code), variable) or str(variable.get("defaultValue") or "")
        if not text and variable.get("required", True):
            missing.append(code)
        resolved[code] = text
    return resolved, missing


def render_ai_prompt(config: dict[str, Any], values: dict[str, Any]) -> tuple[str, dict[str, str]]:
    resolved, missing = resolve_context_values(config, values)
    if missing:
        raise AiGenerationError(f"AI 上下文字段缺失：{', '.join(missing)}")
    prompt = str(config.get("promptTemplate") or "")
    for code, value in sorted(resolved.items(), key=lambda item: len(item[0]), reverse=True):
        prompt = prompt.replace(f"{{{{{code}}}}}", value)
    if "{{" in prompt or "}}" in prompt:
        raise AiGenerationError("AI 提示词存在未解析的变量")
    if not prompt.strip():
        raise AiGenerationError("AI 提示词不能为空")
    return prompt, resolved


def generate_ai_text(field_code: str, rule: dict[str, Any], values: dict[str, Any]) -> str:
    settings = get_settings()
    service = load_ai_service_config(True)
    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    base_url = str(config.get("baseUrl") or service["baseUrl"]).rstrip("/")
    model = str(config.get("model") or service["model"])
    api_key = str(service.get("apiKey") or "")
    if not base_url or not api_key or not model:
        raise AiGenerationError("AI 服务未配置，请设置接口地址、API Key 和模型")
    prompt, _ = render_ai_prompt(config, values)
    max_tokens = int(config.get("maxLength") or service.get("maxTokens") or 800)
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(config.get("temperature", 0.2)),
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if service.get("thinkingEnabled") else "disabled"},
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions", data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=float(service["timeout"])) as response:
            result = json.loads(response.read().decode("utf-8"))
        content, has_reasoning = _response_content(result)
    except AiGenerationError:
        raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise AiGenerationError(f"AI 生成失败：{error}") from error
    if not content:
        if has_reasoning:
            raise AiGenerationError("AI 输出预算已被思考过程耗尽，请增大最大长度或关闭思考模式")
        raise AiGenerationError("AI 服务返回了空内容")
    logger.info("AI字段生成成功 field=%s rule=%s model=%s elapsedMs=%d",
                field_code, rule.get("id"), model, int((time.monotonic() - started) * 1000))
    return content
