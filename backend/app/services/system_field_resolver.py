import logging
import re
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from .calculation_engine import CalculationError, evaluate_formula
from .ai_field_generator import (
    AiGenerationError, context_variables, generate_ai_text, needs_per_record_generation,
    resolve_context_values,
)
from .excel_standard_path import excel_target_path
from .payload_paths import PayloadPathError, read_payload_path, set_payload_path
from .ai_context_inputs import prepare_ai_context
from .system_field_rule_invariant import rules_by_field_source
from .keyed_lookup_calculation import evaluate_keyed_lookup, is_keyed_lookup


logger = logging.getLogger(__name__)
AI_MAX_CONCURRENCY = 200
_BASE_SOURCE_TYPES = {"LIMS", "EXCEL", "PDF"}
_DERIVED_SOURCE_TYPES = {"AI", "CALCULATED", "FIXED", "MANUAL"}
_AI_EXECUTOR = ThreadPoolExecutor(max_workers=AI_MAX_CONCURRENCY,
                                  thread_name_prefix="report-ai")


@dataclass(frozen=True)
class _AiCall:
    field_code: str
    rule: dict[str, Any]
    inputs: dict[str, Any]
    current_record: dict[str, Any] | None
    record_index: int | None = None


@dataclass
class _AiFieldBatch:
    field: dict[str, Any]
    rule: dict[str, Any]
    calls: list[_AiCall]
    record_count: int | None = None


def _write_path(target: dict[str, Any], path: str, value: Any) -> None:
    try:
        set_payload_path(target, path, value)
    except PayloadPathError as error:
        logger.info("系统字段落位失败 path=%s reason=%s", path, error)


def _available(value: Any) -> bool:
    return value not in (None, "", [], {})


def _select_rule(field_code: str, sources: dict[str, dict[str, Any]],
                 field_source_type: str, loaded_source_types: set[str]) -> dict[str, Any] | None:
    enabled = {source: rule for source, rule in sources.items() if rule.get("enabled", True)}
    if not enabled:
        return None
    protocol = enabled.get("PROTOCOL")
    if protocol:
        if len(enabled) != 1:
            raise ValueError(f"系统字段 {field_code} 的方案规则不能与其他来源规则同时启用")
        return protocol
    derived = [rule for source, rule in enabled.items() if source in _DERIVED_SOURCE_TYPES]
    direct = {source: rule for source, rule in enabled.items() if source in _BASE_SOURCE_TYPES}
    unknown = [source for source in enabled
               if source not in _BASE_SOURCE_TYPES | _DERIVED_SOURCE_TYPES]
    if unknown:
        raise ValueError(f"系统字段 {field_code} 存在不支持的来源规则：{', '.join(sorted(unknown))}")
    if len(derived) > 1 or (derived and direct):
        raise ValueError(f"系统字段 {field_code} 的派生规则与数据源规则存在冲突")
    if derived:
        return derived[0]
    if field_source_type:
        selected = direct.get(field_source_type)
        if selected:
            return selected
        raise ValueError(
            f"系统字段 {field_code} 已记录来源 {field_source_type}，但没有对应的启用规则"
        )
    loaded = [rule for source, rule in direct.items() if source in loaded_source_types]
    if len(loaded) == 1:
        return loaded[0]
    if len(loaded) > 1:
        raise ValueError(f"系统字段 {field_code} 的多个数据源均已载入，但未记录字段来源")
    if len(direct) > 1:
        raise ValueError(f"系统字段 {field_code} 有多个数据源规则，但报告未记录字段来源")
    return next(iter(direct.values()), None)


def _field_source_type(report_data: dict[str, Any], field_code: str) -> str:
    sources = report_data.get("field_sources", {})
    if not isinstance(sources, dict):
        raise ValueError("报告字段来源格式无效")
    detail = sources.get(field_code, {})
    if detail and not isinstance(detail, dict):
        raise ValueError(f"系统字段 {field_code} 的来源格式无效")
    return str(detail.get("type") or "").upper()


def _source_payload(report_data: dict[str, Any], source_type: str,
                    fallback: dict[str, Any]) -> dict[str, Any]:
    if source_type not in _BASE_SOURCE_TYPES:
        return fallback
    payloads = report_data.get("source_payloads", {})
    source = payloads.get(source_type) if isinstance(payloads, dict) else None
    return source if isinstance(source, dict) else fallback


def _loaded_source_types(report_data: dict[str, Any]) -> set[str]:
    payloads = report_data.get("source_payloads", {})
    if not isinstance(payloads, dict):
        raise ValueError("报告数据源载荷格式无效")
    return {source for source in _BASE_SOURCE_TYPES if isinstance(payloads.get(source), dict)}


def _group_values(fields: list[dict[str, Any]], by_field_source: dict[str, dict[str, Any]],
                  report_data: dict[str, Any], fallback: dict[str, Any],
                  group_codes: set[str], *, require_namespaced_source: bool = False) -> dict[str, Any]:
    grouped_sources: dict[str, set[str]] = {code: set() for code in group_codes}
    loaded_source_types = _loaded_source_types(report_data)
    for field in fields:
        group_code = str(field.get("collectionCode") or "")
        if group_code not in grouped_sources:
            continue
        field_code = str(field.get("fieldCode") or "")
        rule = _select_rule(
            field_code, by_field_source.get(field_code, {}),
            _field_source_type(report_data, field_code), loaded_source_types,
        )
        source_type = str((rule or {}).get("sourceType") or "").upper()
        if source_type in _BASE_SOURCE_TYPES | {"PROTOCOL"}:
            grouped_sources[group_code].add(source_type)

    payloads = report_data.get("source_payloads", {})
    values: dict[str, Any] = {}
    for group_code, source_types in grouped_sources.items():
        if len(source_types) > 1:
            raise ValueError(
                f"系统字段编组 {group_code} 同时选择了多个直接来源："
                f"{', '.join(sorted(source_types))}"
            )
        source_type = next(iter(source_types), "")
        source = payloads.get(source_type) if isinstance(payloads, dict) else None
        if source_type and require_namespaced_source and not isinstance(source, dict):
            raise ValueError(f"系统字段编组 {group_code} 缺少已选来源载荷：{source_type}")
        selected_payload = source if isinstance(source, dict) else fallback
        values[group_code] = selected_payload.get(group_code)
    return values


def resolve_group_source_values(
    fields: list[dict[str, Any]], rules: list[dict[str, Any]],
    report_data: dict[str, Any], fallback: dict[str, Any], group_codes: set[str],
) -> dict[str, Any]:
    """按正式生成使用的字段规则，从隔离的来源命名空间读取编组快照。"""
    return _group_values(
        fields, rules_by_field_source(rules), report_data, fallback, group_codes,
        require_namespaced_source=True,
    )


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
                current_record: dict[str, Any] | None = None,
                context_fields: list[dict[str, Any]] | None = None) -> Any:
    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    source_type = str(rule.get("sourceType") or "LIMS").upper()
    field_code = field["fieldCode"]
    if source_type == "LIMS":
        if current_record:
            relative_key = str(field.get("jsonKey") or field_code.rsplit(".", 1)[-1])
            return current_record.get(relative_key)
        return read_payload_path(payload, str(field.get("legacyJsonPath") or field_code))
    if source_type == "PROTOCOL":
        result = report_data.get("source_payloads", {}).get("PROTOCOL", {}).get("_meta", {}).get("fields", {}).get(field_code, {})
        return result.get("value") if result.get("status") == "SUCCESS" else None
    if source_type == "PDF":
        pdf = report_data.get("source_payloads", {}).get("PDF", {})
        value = read_payload_path(pdf, str(config.get("sourcePath") or field_code))
        if not _available(value):
            value = report_data.get("original_values", {}).get(field_code)
        if not _available(value):
            value = report_data.get(field_code)
        return value
    if source_type == "EXCEL":
        excel = report_data.get("source_payloads", {}).get("EXCEL", {})
        return read_payload_path(excel, excel_target_path(field, config.get("sourcePath")))
    if source_type == "FIXED":
        return config.get("value")
    if source_type == "MANUAL":
        return report_data.get(field_code)
    if source_type == "CALCULATED":
        if is_keyed_lookup(config):
            return evaluate_keyed_lookup(config, values)
        dependencies = [str(item) for item in config.get("dependencies", [])]
        template = str(config.get("textTemplate") or "")
        if template:
            # 上下文变量和 AI 规则用同一套取值方式（FIRST / JOIN_UNIQUE / COUNT_UNIQUE
            # 加后缀），成组字段才能拼成"1.4%、0.3%、0.5%"这样的文字。
            if config.get("contextVariables") or config.get("inputFields"):
                resolved, missing = resolve_context_values(
                    config, values, current_record, context_fields,
                )
                return None if missing else _template_value(template, resolved)
            return _template_value(template, values)
        return evaluate_formula(
            str(config.get("expression") or ""), dependencies, values,
            int(config.get("precision", 2)), str(config.get("nullBehavior") or "ERROR"),
        )
    return None


def _require_ai_dependencies(config: dict[str, Any], values: dict[str, Any],
                             current_record: dict[str, Any] | None,
                             context_fields: list[dict[str, Any]]) -> None:
    _, missing = resolve_context_values(config, values, current_record, context_fields)
    if missing:
        raise AiGenerationError(f"AI 上下文字段缺失：{', '.join(missing)}")


def _prepare_ai_batch(field: dict[str, Any], rule: dict[str, Any],
                      values: dict[str, Any],
                      context_fields: list[dict[str, Any]]) -> _AiFieldBatch:
    config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    field_code = field["fieldCode"]
    if not needs_per_record_generation(config):
        inputs, record = prepare_ai_context(config, values, None, field)
        _require_ai_dependencies(config, inputs, record, context_fields)
        return _AiFieldBatch(field, rule, [_AiCall(field_code, rule, inputs, record)])

    collection_code = field.get("collectionCode")
    if not collection_code:
        raise AiGenerationError(f"AI字段 {field_code} 使用 CURRENT_RECORD 模式但不属于任何编组")
    records = values.get(collection_code)
    if not isinstance(records, list):
        raise AiGenerationError(f"编组 {collection_code} 的数据不是数组，无法按记录生成")
    calls = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        inputs, ai_record = prepare_ai_context(config, values, record, field)
        _require_ai_dependencies(config, inputs, ai_record, context_fields)
        calls.append(_AiCall(field_code, rule, inputs, ai_record, index))
    return _AiFieldBatch(field, rule, calls, len(records))


def _run_ai_batches(batches: list[_AiFieldBatch], context_fields: list[dict[str, Any]]) \
        -> tuple[dict[str, Any], dict[str, Exception]]:
    calls = [call for batch in batches for call in batch.calls]
    results: dict[str, Any] = {}
    per_record = {
        batch.field["fieldCode"]: [None] * batch.record_count
        for batch in batches if batch.record_count is not None
    }
    if not calls:
        return per_record, {}
    logger.info("开始并发生成AI字段 fields=%d requests=%d concurrency=%d",
                len(batches), len(calls), min(AI_MAX_CONCURRENCY, len(calls)))
    failures: dict[str, Exception] = {}
    futures: dict[Future[str], _AiCall] = {
        _AI_EXECUTOR.submit(generate_ai_text, call.field_code, call.rule, call.inputs,
                            call.current_record, context_fields): call
        for call in calls
    }
    for future in as_completed(futures):
        call = futures[future]
        try:
            value = future.result()
        except AiGenerationError as error:
            failures.setdefault(call.field_code, error)
            continue
        if call.record_index is None:
            results[call.field_code] = value
        else:
            per_record[call.field_code][call.record_index] = value
    for field_code, values in per_record.items():
        if field_code not in failures:
            results[field_code] = values
    logger.info("AI字段并发生成完成 fields=%d succeeded=%d failed=%d",
                len(batches), len(results), len(failures))
    return results, failures


def _store_resolved_value(field_code: str, field: dict[str, Any], rule: dict[str, Any],
                          value: Any, payload: dict[str, Any], report_data: dict[str, Any],
                          values: dict[str, Any]) -> None:
    source_type = str(rule.get("sourceType") or "LIMS").upper()
    values[field_code] = value
    if source_type == "AI":
        # AI 结果不属于当前 Excel/LIMS/PDF 载荷；独立保存，避免切换基础数据源后丢失。
        report_data.setdefault("source_payloads", {}).setdefault("AI", {})[field_code] = value
    if source_type != "PROTOCOL":
        _write_path(payload, str(field.get("legacyJsonPath") or field_code), value)
    report_data.setdefault("original_values", {})[field_code] = value
    if source_type == "PROTOCOL":
        return
    report_data.setdefault("field_sources", {})[field_code] = {
        "type": rule.get("sourceType", "LIMS"), "ruleId": rule.get("id"),
        "ruleName": rule.get("name", ""),
        "sourcePath": (
            excel_target_path(field, (rule.get("config") or {}).get("sourcePath"))
            if source_type == "EXCEL" else (rule.get("config") or {}).get("sourcePath", "")
        ),
    }


def resolve_system_fields(fields: list[dict[str, Any]], rules: list[dict[str, Any]],
                          payload: dict[str, Any], report_data: dict[str, Any]) -> dict[str, Any]:
    by_field_source = rules_by_field_source(rules)
    loaded_source_types = _loaded_source_types(report_data)
    # values 包含两类：字段值（fieldCode）和编组数据（groupCode）
    values = {
        field["fieldCode"]: read_payload_path(
            payload, str(field.get("legacyJsonPath") or field["fieldCode"])
        )
        for field in fields
    }
    protocol = report_data.get("source_payloads", {}).get("PROTOCOL", {})
    protocol_fields = protocol.get("_meta", {}).get("fields", {})
    for code, result in protocol_fields.items():
        values[code] = result.get("value") if result.get("status") == "SUCCESS" else None
    # 标准载荷以编组编码为命名空间，不能从任意成员的层级路径反推编组。
    group_codes = {str(field["collectionCode"]) for field in fields if field.get("collectionCode")}
    group_codes.update(
        str(variable["groupCode"])
        for rule in rules if rule.get("enabled", True)
        for variable in context_variables(rule.get("config") or {}) if variable.get("groupCode")
    )
    pending = {field["fieldCode"]: field for field in fields if field.get("enabled", True)}
    failures: dict[str, Exception] = {}
    failed_ai_rules: set[tuple[str, Any]] = set()
    while pending:
        progressed = False
        ai_batches: list[_AiFieldBatch] = []
        for field_code, field in list(pending.items()):
            rule = _select_rule(
                field_code, by_field_source.get(field_code, {}),
                _field_source_type(report_data, field_code), loaded_source_types,
            )
            if rule and rule.get("enabled", True):
                config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
                source_type = str(rule.get("sourceType") or "LIMS").upper()
                rule_key = (field_code, rule.get("id", id(rule)))
                if source_type == "AI" and rule_key in failed_ai_rules:
                    continue
                try:
                    # 前序规则可能刚写入或替换编组数据；每次按字段级来源读取编组。
                    values.update(_group_values(
                        fields, by_field_source, report_data, payload, group_codes,
                    ))
                    if source_type == "AI":
                        ai_payload = report_data.setdefault("source_payloads", {}).setdefault("AI", {})
                        existing = ai_payload.get(field_code)
                        if _available(existing):
                            value = existing
                        else:
                            ai_batches.append(_prepare_ai_batch(field, rule, values, fields))
                            continue
                    else:
                        rule_payload = _source_payload(report_data, source_type, payload)
                        value = _rule_value(
                            rule, field, rule_payload, report_data, values,
                            context_fields=fields,
                        )
                except (CalculationError, AiGenerationError) as error:
                    failures[field_code] = error
                    logger.info("系统字段规则等待依赖 field=%s rule=%s reason=%s", field_code, rule.get("name"), error)
                    continue
                if not _available(value):
                    continue
                target_payload = _source_payload(report_data, source_type, payload)
                _store_resolved_value(
                    field_code, field, rule, value, target_payload, report_data, values,
                )
                del pending[field_code]
                progressed = True

        # 先让本轮所有本地规则落位，使 AI 读取到这一轮能产生的完整上下文。
        if progressed:
            continue
        if not ai_batches:
            break
        ai_results, ai_failures = _run_ai_batches(ai_batches, fields)
        failed_this_round = False
        for batch in ai_batches:
            field_code = batch.field["fieldCode"]
            failure = ai_failures.get(field_code)
            if failure is not None:
                failures[field_code] = failure
                failed_ai_rules.add((field_code, batch.rule.get("id", id(batch.rule))))
                logger.info("AI字段并发生成失败 field=%s rule=%s reason=%s",
                            field_code, batch.rule.get("name"), failure)
                failed_this_round = True
                continue
            value = ai_results.get(field_code)
            if not _available(value):
                continue
            _store_resolved_value(field_code, batch.field, batch.rule, value,
                                  payload, report_data, values)
            del pending[field_code]
            progressed = True
        if not progressed and not failed_this_round:
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
        keyed_failures = [f"{code}：{failures[code]}" for code in pending
                          if isinstance(failures.get(code), CalculationError)
                          and is_keyed_lookup((by_field_source.get(code, {}).get("CALCULATED") or {}).get("config") or {})]
        if keyed_failures:
            raise ValueError("按项目组装验证结论失败：" + "；".join(keyed_failures))
    return payload
