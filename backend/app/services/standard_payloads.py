from typing import Any


def active_standard_payload(report_data: dict[str, Any]) -> dict[str, Any]:
    """报告生成和快照测试共用同一份标准载荷取值顺序。"""
    payloads = report_data.get("source_payloads", {})
    if not isinstance(payloads, dict):
        raise ValueError("报告数据源载荷格式无效")
    return next((payloads[name] for name in ("EXCEL", "LIMS", "PDF")
                 if isinstance(payloads.get(name), dict)), {})


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
