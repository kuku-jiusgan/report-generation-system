import logging
from typing import Any

from .system_field_group_levels import structure_preview


logger = logging.getLogger(__name__)


def _read_relative(source: Any, path: str) -> Any:
    current = source
    for part in path.strip().strip(".").split("."):
        if not part:
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _ordered_like(value: Any, template: Any) -> Any:
    """按结构模板的键序重排取值；模板之外的键按键名排在后面。"""
    if isinstance(template, list):
        template = template[0] if template else {}
    if isinstance(value, list):
        return [_ordered_like(item, template) for item in value]
    if not isinstance(value, dict) or not isinstance(template, dict):
        return value
    order = {key: index for index, key in enumerate(template)}
    keys = sorted(value, key=lambda key: (order.get(key, len(order)), key))
    return {key: _ordered_like(value[key], template.get(key)) for key in keys}


def apply_group_contracts(payload: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize grouped payload without discarding source rows or evidence."""
    for group in groups:
        if not group.get("enabled", True):
            continue
        code = str(group.get("groupCode") or "").strip()
        if not code or code not in payload:
            continue
        cardinality = str(group.get("cardinality") or "ONE").upper()
        # 记录的键顺序服从标准字段目录里那份结构：先记录顶层字段，再按层的顺序展开子层。
        # 直接复用目录结构预览的键序，避免这里另推一套排序规则、和目录里显示的对不上。
        template = structure_preview(list(group.get("levels") or []), list(group.get("fields") or []))
        current = payload.get(code)
        if cardinality == "MANY":
            records = current if isinstance(current, list) else ([current] if isinstance(current, dict) else [])
            payload[code] = [_ordered_like(record, template)
                             for record in records if isinstance(record, dict)]
            item_key = str(group.get("itemKey") or "").strip()
            if item_key:
                missing = [index for index, record in enumerate(payload[code])
                           if _read_relative(record, item_key) in (None, "")]
                if missing:
                    logger.warning("编组记录缺少 itemKey group=%s itemKey=%s rows=%s", code, item_key, missing)
        elif isinstance(current, list):
            payload[code] = _ordered_like(current[0], template) if current else {}
        elif isinstance(current, dict):
            payload[code] = _ordered_like(current, template)
    return payload
