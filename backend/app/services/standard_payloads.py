from typing import Any


_BASE_SOURCE_TYPES = ("EXCEL", "LIMS", "PDF")


def _protocol_groups(report_data: dict[str, Any]) -> set[str]:
    protocol = report_data.get("source_payloads", {}).get("PROTOCOL", {})
    fields = protocol.get("_meta", {}).get("fields", {}) if isinstance(protocol, dict) else {}
    return {
        str(result.get("source", {}).get("sourcePath", "")).removeprefix("$.")
        .split(".")[0].replace("[*]", "")
        for result in fields.values() if isinstance(result, dict)
    }


def _group_source_type(report_data: dict[str, Any], code: str) -> str:
    if code in _protocol_groups(report_data):
        return "PROTOCOL"
    sources = report_data.get("field_sources", {})
    if not isinstance(sources, dict):
        raise ValueError("报告字段来源格式无效")
    selected = {
        str(detail.get("type") or "").upper()
        for field_code, detail in sources.items()
        if isinstance(detail, dict)
        and (str(field_code) == code or str(field_code).startswith(f"{code}."))
        and str(detail.get("type") or "").upper() in _BASE_SOURCE_TYPES + ("PROTOCOL",)
    }
    if len(selected) > 1:
        raise ValueError(f"系统字段编组 {code} 同时使用多个直接来源：{', '.join(sorted(selected))}")
    return next(iter(selected), "")


def active_standard_payload(report_data: dict[str, Any]) -> dict[str, Any]:
    """Return the explicitly selected standard payload."""
    payloads = report_data.get("source_payloads", {})
    if not isinstance(payloads, dict):
        raise ValueError("报告数据源载荷格式无效")
    active_source = str(report_data.get("active_source_type") or "").upper()
    if active_source:
        if active_source not in {"EXCEL", "LIMS", "PDF"}:
            raise ValueError(f"报告当前数据源类型无效：{active_source}")
        active = payloads.get(active_source)
        if not isinstance(active, dict):
            raise ValueError(f"报告缺少当前数据源载荷：{active_source}")
        return active
    candidates = [payloads[name] for name in ("EXCEL", "LIMS", "PDF")
                  if isinstance(payloads.get(name), dict)]
    if len(candidates) > 1:
        raise ValueError("报告存在多个数据源但未记录当前来源，请重新选择报告数据源")
    return candidates[0] if candidates else {}


def standard_group_values(report_data: dict[str, Any], fallback: dict[str, Any] | None,
                          codes: set[str]) -> dict[str, Any]:
    """按字段溯源选择编组载荷，不把不同来源的同名编组合并。"""
    payloads = report_data.get("source_payloads", {})
    if not isinstance(payloads, dict):
        raise ValueError("报告数据源载荷格式无效")
    result: dict[str, Any] = {}
    for code in codes:
        source_type = _group_source_type(report_data, code)
        source = payloads.get(source_type) if source_type else fallback
        if not source_type and source is None:
            raise ValueError(f"系统字段编组 {code} 缺少字段来源绑定")
        if source_type and not isinstance(source, dict):
            raise ValueError(f"系统字段编组 {code} 缺少 {source_type} 来源载荷")
        result[code] = source.get(code) if isinstance(source, dict) else None
    return result


def standard_context_payload(
    report_data: dict[str, Any], active_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造渲染/AI 临时视图；每个编组按字段溯源选择唯一来源。"""
    from copy import deepcopy
    payloads = report_data.get("source_payloads", {})
    if not isinstance(payloads, dict):
        raise ValueError("报告数据源载荷格式无效")
    fallback = active_payload
    if fallback is None:
        legacy_source = str(report_data.get("active_source_type") or "").upper()
        fallback = payloads.get(legacy_source) if legacy_source in _BASE_SOURCE_TYPES else None
    if fallback is None:
        unique_sources = [payloads[name] for name in _BASE_SOURCE_TYPES
                          if isinstance(payloads.get(name), dict)]
        if len(unique_sources) == 1:
            fallback = unique_sources[0]
    source_payloads = [payloads.get(name) for name in _BASE_SOURCE_TYPES + ("PROTOCOL",)]
    codes = {
        str(code) for source in source_payloads if isinstance(source, dict)
        for code in source if code != "_meta"
    }
    view = deepcopy({code: value for code, value in standard_group_values(report_data, fallback, codes).items()
                     if value is not None and code != '_meta'})
    return view
