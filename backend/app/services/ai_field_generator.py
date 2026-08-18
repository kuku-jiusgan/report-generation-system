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


def context_variables(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = config.get("contextVariables")
    if isinstance(configured, list):
        return [item for item in configured if isinstance(item, dict) and item.get("fieldCode")]
    return [
        {"fieldCode": str(code), "required": True, "mode": "JOIN_UNIQUE", "separator": "、", "defaultValue": ""}
        for code in config.get("inputFields", [])
    ]


def _format_context(value: Any, variable: dict[str, Any]) -> str:
    values = value if isinstance(value, list) else [value]
    normalized = [str(item).strip() for item in values if item not in (None, "")]
    if variable.get("mode", "JOIN_UNIQUE") == "FIRST":
        return normalized[0] if normalized else ""
    unique = list(dict.fromkeys(normalized))
    return str(variable.get("separator") or "、").join(unique)


def render_ai_prompt(config: dict[str, Any], values: dict[str, Any]) -> tuple[str, dict[str, str]]:
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for variable in context_variables(config):
        code = str(variable["fieldCode"])
        value = _format_context(values.get(code), variable) or str(variable.get("defaultValue") or "")
        if not value and variable.get("required", True):
            missing.append(code)
        resolved[code] = value
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
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(config.get("temperature", 0.2)),
        "max_tokens": int(config.get("maxLength", 800)),
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions", data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=float(service["timeout"])) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as error:
        raise AiGenerationError(f"AI 生成失败：{error}") from error
    text = str(content or "").strip()
    if not text:
        raise AiGenerationError("AI 服务返回了空内容")
    logger.info("AI字段生成成功 field=%s rule=%s model=%s elapsedMs=%d",
                field_code, rule.get("id"), model, int((time.monotonic() - started) * 1000))
    return text
