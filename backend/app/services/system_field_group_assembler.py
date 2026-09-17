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


def _read_json_path(source: Any, path: str) -> Any:
    current = source
    for part in str(path or "").removeprefix("$").lstrip(".").split("."):
        if part:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
    return current


def _write_json_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in str(path or "").removeprefix("$").lstrip(".").split(".") if part]
    if not parts:
        raise ValueError("编组集合路径不能为空")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ValueError(f"编组集合路径冲突：{path}")
        current = child
    current[parts[-1]] = value


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
        source_key = code
        item_path = f"$.{code}" if code else ""
        if source_key not in payload:
            # 不同来源分别保存载荷；当前来源没有该编组时保持缺省，不能据此推断 Excel/LIMS 的来源。
            continue
        cardinality = str(group.get("cardinality") or "ONE").upper()
        # 记录的键顺序服从标准字段目录里那份结构：先记录顶层字段，再按层的顺序展开子层。
        # 直接复用目录结构预览的键序，避免这里另推一套排序规则、和目录里显示的对不上。
        template = structure_preview(list(group.get("levels") or []), list(group.get("fields") or []))
        current = payload.get(source_key)
        if cardinality == "MANY":
            if not isinstance(current, list):
                raise ValueError(f"编组 {group.get('label') or code} 的数据列表必须是多行列表：{source_key}")
            records = current
            normalized = [_ordered_like(record, template) for record in records if isinstance(record, dict)]
            if item_path:
                existing = _read_json_path(payload, item_path)
                if existing is not None and existing is not current and not isinstance(existing, list):
                    raise ValueError(f"编组 {code} 的集合路径不是数组：{item_path}")
                _write_json_path(payload, item_path, normalized)
            else:
                payload[source_key] = normalized
            current_records = normalized
            item_key = str(group.get("itemKey") or "").strip()
            if item_key:
                missing = [index for index, record in enumerate(current_records)
                           if _read_relative(record, item_key) in (None, "")]
                if missing:
                    logger.warning("编组记录缺少 itemKey group=%s itemKey=%s rows=%s", code, item_key, missing)
        elif isinstance(current, list):
            normalized = _ordered_like(current[0], template) if current else {}
            if item_path:
                _write_json_path(payload, item_path, normalized)
            else:
                payload[source_key] = normalized
        elif isinstance(current, dict):
            normalized = _ordered_like(current, template)
            if item_path:
                _write_json_path(payload, item_path, normalized)
            else:
                payload[source_key] = normalized
    return payload
