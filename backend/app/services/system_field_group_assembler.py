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


def _field_locations(record: dict[str, Any], key: str) -> list[tuple[str, Any]]:
    locations: list[tuple[str, Any]] = []
    if key in record:
        locations.append(("", record[key]))
    summary = record.get("summary")
    if isinstance(summary, dict) and key in summary:
        locations.append(("summary", summary[key]))
    injections = record.get("injections")
    if isinstance(injections, list):
        values = [item[key] for item in injections if isinstance(item, dict) and key in item]
        if values:
            locations.append(("injections", values))
    return locations


def _remove_field(record: dict[str, Any], level: str, key: str) -> None:
    if not level:
        record.pop(key, None)
    elif level == "summary" and isinstance(record.get(level), dict):
        record[level].pop(key, None)
    elif level == "injections" and isinstance(record.get(level), list):
        for item in record[level]:
            if isinstance(item, dict):
                item.pop(key, None)


def _move_field(record: dict[str, Any], field: dict[str, Any]) -> None:
    """Move a legacy field when the configured level changed and the move is unambiguous."""
    key = str(field.get("jsonKey") or field.get("fieldCode", "").rsplit(".", 1)[-1])
    target = str(field.get("levelKey") or "")
    locations = _field_locations(record, key)
    if any(level == target for level, _ in locations) or not locations:
        return
    if len(locations) != 1:
        raise ValueError(f"字段 {field.get('fieldCode')} 在旧载荷中存在多个层级，无法自动迁移")
    source, value = locations[0]
    if source == "injections":
        if len(value) != 1:
            raise ValueError(
                f"字段 {field.get('fieldCode')} 有 {len(value)} 条明细，无法迁移到单值层"
            )
        value = value[0]
    if target == "injections":
        details = record.get("injections")
        if details is None:
            details = [{}]
            record["injections"] = details
        if not isinstance(details, list) or len(details) != 1 or not isinstance(details[0], dict):
            count = len(details) if isinstance(details, list) else 0
            raise ValueError(
                f"字段 {field.get('fieldCode')} 的旧单值无法确定应写入 {count} 条明细中的哪一条"
            )
        details[0][key] = value
    elif target == "summary":
        summary = record.setdefault("summary", {})
        if not isinstance(summary, dict):
            raise ValueError("编组的 summary 层必须是对象")
        summary[key] = value
    else:
        record[key] = value
    _remove_field(record, source, key)


def _migrate_record_structure(record: dict[str, Any], fields: list[dict[str, Any]]) -> None:
    for field in fields:
        _move_field(record, field)


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
            for record in records:
                if isinstance(record, dict):
                    _migrate_record_structure(record, list(group.get("fields") or []))
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
                    raise ValueError(
                        f"编组 {group.get('label') or code} 的记录缺少身份字段 {item_key}："
                        f"第 {', '.join(str(index + 1) for index in missing)} 行"
                    )
        elif isinstance(current, list):
            for record in current:
                if isinstance(record, dict):
                    _migrate_record_structure(record, list(group.get("fields") or []))
            normalized = _ordered_like(current[0], template) if current else {}
            if item_path:
                _write_json_path(payload, item_path, normalized)
            else:
                payload[source_key] = normalized
        elif isinstance(current, dict):
            _migrate_record_structure(current, list(group.get("fields") or []))
            normalized = _ordered_like(current, template)
            if item_path:
                _write_json_path(payload, item_path, normalized)
            else:
                payload[source_key] = normalized
    return payload
