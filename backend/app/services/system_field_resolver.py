import logging
import re
from typing import Any

from .calculation_engine import CalculationError, evaluate_formula
from .ai_field_generator import AiGenerationError, generate_ai_text, resolve_context_values, needs_per_record_generation
from .excel_standard_path import excel_target_path
from .payload_paths import PayloadPathError, set_payload_path


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
    try:
        set_payload_path(target, path, value)
    except PayloadPathError as error:
        logger.info("系统字段落位失败 path=%s reason=%s", path, error)


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
                report_data: dict[str, Any], values: dict[str, Any],
                current_record: dict[str, Any] | None = None) -> Any:
    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    source_type = str(rule.get("sourceType") or "LIMS").upper()
    field_code = field["fieldCode"]
    if source_type == "LIMS":
        source_path = str(config.get("sourcePath") or field.get("legacyJsonPath") or field_code)
        # 标准化 JSON 规则的目标路径由字段所属编组推导；历史规则里可能残留
        # ``$[*]`` 这类旧路径，不能让它覆盖当前编组契约。其他 LIMS 解析器
        # 仍使用各自配置的原始来源路径。
        parser = str(config.get("parser") or "").upper()
        extraction_type = str(config.get("extractionType") or "").upper()
        if parser == "NORMALIZED_JSON" and extraction_type in {"", "NORMALIZED_PATH"}:
            source_path = str(field.get("legacyJsonPath") or field_code)
        # 如果在按记录生成上下文中，从当前记录读取
        if current_record:
            # 提取字段的相对键名（最后一个点之后的部分）
            relative_key = field_code.split(".")[-1] if "." in field_code else field_code
            return current_record.get(relative_key)
        return _read_path(payload, source_path)
    if source_type == "PDF":
        pdf = report_data.get("source_payloads", {}).get("PDF", {})
        value = _read_path(pdf, str(config.get("sourcePath") or field_code))
        if not _available(value):
            value = report_data.get("original_values", {}).get(field_code)
        if not _available(value):
            value = report_data.get(field_code)
        return value
    if source_type == "EXCEL":
        excel = report_data.get("source_payloads", {}).get("EXCEL", {})
        return _read_path(excel, excel_target_path(field, config.get("sourcePath")))
    if source_type == "AI":
        existing = report_data.get("source_payloads", {}).get("AI", {}).get(field_code)
        return existing or generate_ai_text(field_code, rule, values, current_record)
    if source_type == "FIXED":
        return config.get("value")
    if source_type == "MANUAL":
        return report_data.get(field_code)
    if source_type == "CALCULATED":
        dependencies = [str(item) for item in config.get("dependencies", [])]
        template = str(config.get("textTemplate") or "")
        if template:
            # 上下文变量和 AI 规则用同一套取值方式（FIRST / JOIN_UNIQUE / COUNT_UNIQUE
            # 加后缀），成组字段才能拼成"1.4%、0.3%、0.5%"这样的文字。
            if config.get("contextVariables") or config.get("inputFields"):
                resolved, missing = resolve_context_values(config, values, current_record)
                return None if missing else _template_value(template, resolved)
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
    # values 包含两类：字段值（fieldCode）和编组数据（groupCode）
    values = {
        field["fieldCode"]: _read_path(payload, str(field.get("legacyJsonPath") or field["fieldCode"]))
        for field in fields
    }
    # 将编组数据也加入 values，供 AI 和计算规则使用
    # 从字段的 collectionCode（编组）中提取编组数据
    seen_groups: set[str] = set()
    for field in fields:
        collection_code = field.get("collectionCode")
        if collection_code and collection_code not in seen_groups:
            seen_groups.add(collection_code)
            # collectionCode 就是编组的 groupCode
            # 从 legacyJsonPath 中提取编组的根路径（去掉字段部分）
            # 例如 $.samples[*].sampleName -> $.samples
            legacy_path = str(field.get("legacyJsonPath") or "")
            if legacy_path:
                # 移除最后的字段名和 [*]，得到编组路径
                parts = legacy_path.split(".")
                if len(parts) > 1:
                    # 去掉最后一个部分（字段名）
                    group_path_parts = parts[:-1]
                    # 移除 [*] 标记
                    group_path = ".".join(p.replace("[*]", "") for p in group_path_parts)
                    values[collection_code] = _read_path(payload, group_path)
    pending = {field["fieldCode"]: field for field in fields if field.get("enabled", True)}
    failures: dict[str, Exception] = {}
    for _ in range(len(pending) + 1):
        progressed = False
        for field_code, field in list(pending.items()):
            for rule in sorted(by_field.get(field_code, []), key=lambda item: (item.get("priority", 100), item.get("id", 0))):
                try:
                    # 检查是否需要按记录生成
                    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
                    source_type = str(rule.get("sourceType") or "LIMS").upper()

                    if source_type == "AI" and needs_per_record_generation(config):
                        # 按记录生成：遍历编组的每条记录
                        collection_code = field.get("collectionCode")
                        if not collection_code:
                            raise AiGenerationError(f"AI字段 {field_code} 使用 CURRENT_RECORD 模式但不属于任何编组")

                        records = values.get(collection_code)
                        if not isinstance(records, list):
                            raise AiGenerationError(f"编组 {collection_code} 的数据不是数组，无法按记录生成")

                        # 为每条记录生成AI字段值
                        generated_values = []
                        for record in records:
                            if isinstance(record, dict):
                                record_value = generate_ai_text(field_code, rule, values, record)
                                generated_values.append(record_value)
                            else:
                                generated_values.append(None)

                        value = generated_values
                    else:
                        # 常规生成：整个字段一次性生成
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
                    "sourcePath": (
                        excel_target_path(field, (rule.get("config") or {}).get("sourcePath"))
                        if str(rule.get("sourceType") or "").upper() == "EXCEL"
                        else (rule.get("config") or {}).get("sourcePath", "")
                    ),
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
