import json
from typing import Any


def _label_paths(fields: list[dict[str, Any]], root: tuple[str, ...]) -> dict[tuple[str, ...], str]:
    labels = {}
    for field in fields:
        path = str(field.get("legacyJsonPath") or "")
        if not path.startswith("$."):
            continue
        parts = path[2:].split(".")
        canonical = tuple(part.removesuffix("[*]") for part in parts)
        paths = [canonical]
        collection = field.get("collectionCode")
        boundary = next((i for i, part in enumerate(parts) if part.endswith("[*]")), None)
        if collection and boundary is not None:
            paths.append((str(collection), *canonical[boundary + 1:]))
        for key in paths:
            if key[:len(root)] != root:
                continue
            # Older callers may provide a partial field descriptor. An explicitly
            # empty label remains invalid; an omitted label simply has no display
            # alias and keeps the source key unchanged.
            if "label" not in field:
                continue
            label = str(field.get("label") or "").strip()
            if key in labels and labels[key] != label:
                raise ValueError(f"AI 上下文字段名称配置冲突：{'.'.join(key)}")
            labels[key] = label
    return labels


def _labeled_value(value: Any, path: tuple[str, ...], labels: dict[tuple[str, ...], str]) -> Any:
    if isinstance(value, list):
        return [_labeled_value(item, path, labels) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        child_path = (*path, key)
        label = labels.get(child_path)
        if label == "":
            raise ValueError(f"AI 上下文字段缺少名称：{'.'.join(child_path)}")
        display_key = f"{key}（{label}）" if label is not None else key
        if display_key in result:
            raise ValueError(f"AI 上下文字段显示名称冲突：{display_key}")
        result[display_key] = _labeled_value(item, child_path, labels)
    return result


def serialize_ai_context(value: Any, code: str, fields: list[dict[str, Any]] | None) -> str:
    """仅序列化时标注标准字段名称，源数据键和占位符编码保持原样。"""
    if fields is not None:
        path = (code,)
        field = next((item for item in fields if item.get("fieldCode") == code), None)
        if field is not None:
            canonical = str(field.get("legacyJsonPath") or "")
            if not canonical.startswith("$."):
                raise ValueError(f"AI 上下文字段缺少标准路径：{code}")
            path = tuple(part.removesuffix("[*]") for part in canonical[2:].split("."))
        value = _labeled_value(value, path, _label_paths(fields, path))
    return json.dumps(value, ensure_ascii=False, indent=2)
