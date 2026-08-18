import logging
from typing import Any


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


def _write_relative(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.strip().strip(".").split(".") if part]
    if not parts:
        return
    current = target
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = value


def _field_path(field: dict[str, Any]) -> str:
    configured = str(field.get("fieldPath") or "").strip()
    return configured or str(field.get("fieldCode") or "").rsplit(".", 1)[-1]


def _canonical_record(record: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any]:
    result = dict(record)
    for field in fields:
        path = _field_path(field)
        value = _read_relative(record, path)
        if value is None:
            legacy_key = str(field.get("fieldCode") or "").rsplit(".", 1)[-1]
            value = record.get(legacy_key)
        if value is not None:
            _write_relative(result, path, value)
    return result


def apply_group_contracts(payload: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize grouped payload without discarding source rows or evidence."""
    for group in groups:
        if not group.get("enabled", True):
            continue
        code = str(group.get("groupCode") or "").strip()
        if not code or code not in payload:
            continue
        cardinality = str(group.get("cardinality") or "ONE").upper()
        current = payload.get(code)
        if cardinality == "MANY":
            records = current if isinstance(current, list) else ([current] if isinstance(current, dict) else [])
            payload[code] = [_canonical_record(record, list(group.get("fields") or []))
                             for record in records if isinstance(record, dict)]
            item_key = str(group.get("itemKey") or "").strip()
            if item_key:
                missing = [index for index, record in enumerate(payload[code])
                           if _read_relative(record, item_key) in (None, "")]
                if missing:
                    logger.warning("编组记录缺少 itemKey group=%s itemKey=%s rows=%s", code, item_key, missing)
        elif isinstance(current, list):
            payload[code] = _canonical_record(current[0], list(group.get("fields") or [])) if current else {}
        elif isinstance(current, dict):
            payload[code] = _canonical_record(current, list(group.get("fields") or []))
    return payload
