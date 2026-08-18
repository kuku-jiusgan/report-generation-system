import logging
import re
from typing import Any

from .calculation_engine import CalculationError, evaluate_formula
from .ai_field_generator import AiGenerationError, generate_ai_text
from .excel_validation_payload import enrich_excel_payload


logger = logging.getLogger(__name__)


def _read_path(source: Any, path: str) -> Any:
    values = [source]
    for raw in path.strip().removeprefix("$").lstrip(".").split("."):
        if not raw:
            continue
        many = raw.endswith("[*]")
        key = raw[:-3] if many else raw
        next_values: list[Any] = []
        for value in values:
            current = value.get(key) if isinstance(value, dict) else None
            if many and isinstance(current, list):
                next_values.extend(current)
            elif current is not None:
                next_values.append(current)
        values = next_values
    return values if "[*]" in path else (values[0] if values else None)


def _write_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part.replace("[*]", "") for part in path.strip().removeprefix("$").lstrip(".").split(".") if part]
    if not parts:
        return
    if "[*]" in path:
        if len(parts) != 2 or not isinstance(value, list):
            return
        collection = target.setdefault(parts[0], [])
        if not isinstance(collection, list):
            collection = []
            target[parts[0]] = collection
        while len(collection) < len(value):
            collection.append({})
        for index, item_value in enumerate(value):
            if isinstance(collection[index], dict) and _available(item_value):
                collection[index][parts[1]] = item_value
        return
    current = target
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _available(value: Any) -> bool:
    return value not in (None, "", [], {})


def _template_value(template: str, values: dict[str, Any]) -> str | None:
    missing = False

    def replace(match: re.Match[str]) -> str:
        nonlocal missing
        value = values.get(match.group(1).strip())
        if not _available(value):
            missing = True
            return ""
        return str(value)

    result = re.sub(r"\{([^{}]+)\}", replace, template)
    return None if missing else result


def _rule_value(rule: dict[str, Any], field: dict[str, Any], payload: dict[str, Any],
                report_data: dict[str, Any], values: dict[str, Any]) -> Any:
    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    source_type = str(rule.get("sourceType") or "LIMS").upper()
    field_code = field["fieldCode"]
    if source_type == "LIMS":
        return _read_path(payload, str(config.get("sourcePath") or field.get("legacyJsonPath") or field_code))
    if source_type == "PDF":
        pdf = report_data.get("source_payloads", {}).get("PDF", {})
        return (_read_path(pdf, str(config.get("sourcePath") or field_code))
                or report_data.get("original_values", {}).get(field_code)
                or report_data.get(field_code))
    if source_type == "EXCEL":
        excel = report_data.get("source_payloads", {}).get("EXCEL", {})
        if isinstance(excel, dict):
            enrich_excel_payload(excel)
        return _read_path(excel, str(config.get("sourcePath") or field_code))
    if source_type == "AI":
        existing = report_data.get("source_payloads", {}).get("AI", {}).get(field_code)
        return existing or generate_ai_text(field_code, rule, values)
    if source_type == "FIXED":
        return config.get("value")
    if source_type == "MANUAL":
        return report_data.get(field_code)
    if source_type == "CALCULATED":
        dependencies = [str(item) for item in config.get("dependencies", [])]
        template = str(config.get("textTemplate") or "")
        if template:
            return _template_value(template, values)
        return evaluate_formula(
            str(config.get("expression") or ""), dependencies, values,
            int(config.get("precision", 2)), str(config.get("nullBehavior") or "ERROR"),
        )
    return None


def resolve_system_fields(fields: list[dict[str, Any]], rules: list[dict[str, Any]],
                          payload: dict[str, Any], report_data: dict[str, Any]) -> dict[str, Any]:
    by_field: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        if rule.get("enabled", True):
            by_field.setdefault(str(rule.get("fieldCode") or ""), []).append(rule)
    values = {
        field["fieldCode"]: _read_path(payload, str(field.get("legacyJsonPath") or field["fieldCode"]))
        for field in fields
    }
    pending = {field["fieldCode"]: field for field in fields if field.get("enabled", True)}
    failures: dict[str, Exception] = {}
    for _ in range(len(pending) + 1):
        progressed = False
        for field_code, field in list(pending.items()):
            for rule in sorted(by_field.get(field_code, []), key=lambda item: (item.get("priority", 100), item.get("id", 0))):
                try:
                    value = _rule_value(rule, field, payload, report_data, values)
                except (CalculationError, AiGenerationError) as error:
                    failures[field_code] = error
                    logger.info("系统字段规则等待依赖 field=%s rule=%s reason=%s", field_code, rule.get("name"), error)
                    continue
                if not _available(value):
                    continue
                values[field_code] = value
                _write_path(payload, str(field.get("legacyJsonPath") or field_code), value)
                report_data.setdefault("original_values", {})[field_code] = value
                report_data.setdefault("field_sources", {})[field_code] = {
                    "type": rule.get("sourceType", "LIMS"), "ruleId": rule.get("id"),
                    "ruleName": rule.get("name", ""),
                    "sourcePath": (rule.get("config") or {}).get("sourcePath", ""),
                }
                del pending[field_code]
                progressed = True
                break
        if not progressed:
            break
    if pending:
        logger.info("系统字段未产生结果 fields=%s", ",".join(sorted(pending)))
        missing_ai = [str(failures[code]) for code in pending
                      if isinstance(failures.get(code), AiGenerationError)
                      and str(failures[code]).startswith("AI 上下文字段缺失：")]
        warnings = report_data.setdefault("warnings", [])
        for message in missing_ai:
            logger.warning("AI字段上下文缺失 message=%s", message)
            if message not in warnings:
                warnings.append(message)
        # AI enrichment is optional during document bootstrap. A report must
        # still produce an editable DOCX when the AI service, prompt, or
        # context is unavailable; retain the diagnostic as a warning instead
        # of turning ONLYOFFICE initialization into a 500 response.
        for code in pending:
            failure = failures.get(code)
            if isinstance(failure, AiGenerationError):
                message = f"AI 字段 {code} 未生成：{failure}"
                logger.warning(message)
                if message not in warnings:
                    warnings.append(message)
    return payload
