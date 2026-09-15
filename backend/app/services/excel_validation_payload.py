"""Excel payload compatibility shim.

集合路径必须来自系统标准字段配置；此模块不再执行业务字段猜测或拼装。
"""

from typing import Any


def enrich_excel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """保留旧调用方的兼容入口，但不改变载荷。"""
    return payload
