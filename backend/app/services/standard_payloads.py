from typing import Any


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


def standard_group_values(report_data: dict[str, Any], active: dict[str, Any], codes: set[str]) -> dict[str, Any]:
    """按方案字段的已解析来源选择编组，不合并不同来源的记录。"""
    protocol = report_data.get('source_payloads', {}).get('PROTOCOL', {})
    protocol_groups = {result['source']['sourcePath'].removeprefix('$.').split('.')[0].replace('[*]', '')
                       for result in protocol.get('_meta', {}).get('fields', {}).values()}
    return {code: protocol.get(code) if code in protocol_groups else active.get(code) for code in codes}


def standard_context_payload(report_data: dict[str, Any]) -> dict[str, Any]:
    """AI 快照的临时视图；缺失的方案字段不会重新读取其他来源的旧值。"""
    from copy import deepcopy
    active = active_standard_payload(report_data)
    protocol = report_data.get('source_payloads', {}).get('PROTOCOL', {})
    codes = set(active) | set(protocol)
    return deepcopy({code: value for code, value in standard_group_values(report_data, active, codes).items()
                     if value is not None and code != '_meta'})
