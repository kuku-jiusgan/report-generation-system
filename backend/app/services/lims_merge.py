from collections import defaultdict
from typing import Any

from .lims_normalizer import (
    _content_hash, _comparison_content, _hash, _semantic, normalize_instance,
    record_collection_codes,
)


def _identity(item: dict[str, Any], item_key: str) -> str:
    if item_key:
        return _semantic(item.get(item_key))
    return _content_hash(item)


def _group_metadata(groups: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {
        str(group.get("groupCode") or ""): group
        for group in groups or [] if group.get("enabled", True) and group.get("groupCode")
    }


def _payload_collections(payloads: list[dict[str, Any]], kind: type) -> list[str]:
    reserved = {"instances", "unmatched"}
    return list(dict.fromkeys(
        key for payload in payloads for key, value in payload.items()
        if key not in reserved and isinstance(value, kind)
    ))


def _field_labels(collection: str, fields: list[dict[str, Any]] | None) -> dict[str, str]:
    return {
        str(field.get("jsonKey") or field.get("fieldCode", "").rsplit(".", 1)[-1]): str(field.get("label") or "")
        for field in fields or []
        if field.get("collectionCode") == collection and field.get("label")
    }


def _differing_fields(collection: str, choices: list[dict[str, Any]],
                      fields: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    values = [_comparison_content(choice) for choice in choices]
    keys = dict.fromkeys(key for value in values for key in value)
    labels = _field_labels(collection, fields)
    return [
        {"key": key, "label": labels.get(key, key)}
        for key in keys
        if len({_hash(value.get(key)) for value in values}) > 1
    ]


def merge_instances(instances: list[dict[str, Any]], resolutions: dict[str, str] | None = None,
                    fields: list[dict[str, Any]] | None = None,
                    extraction_rules: list[dict[str, Any]] | None = None,
                    groups: list[dict[str, Any]] | None = None,
                    normalized: bool = False) -> dict[str, Any]:
    if not instances:
        raise ValueError("至少选择一个实验记录")
    project_ids = {str(item.get("projectId") or item.get("project", {}).get("id") or "") for item in instances}
    if len(project_ids) != 1:
        raise ValueError("只能合并同一项目下的实验记录")
    normalized_instances = instances if normalized else [
        normalize_instance(item, fields, extraction_rules, groups) for item in instances
    ]
    metadata = _group_metadata(groups)
    many_codes = list(dict.fromkeys([
        *record_collection_codes(groups, fields), *_payload_collections(normalized_instances, list),
    ]))
    one_codes = list(dict.fromkeys([
        *(code for code, group in metadata.items()
          if str(group.get("cardinality") or "ONE").upper() == "ONE"),
        *_payload_collections(normalized_instances, dict),
    ]))
    payload: dict[str, Any] = {"instances": [], "unmatched": []}
    for collection in one_codes:
        payload[collection] = next(
            (source[collection] for source in normalized_instances
             if isinstance(source.get(collection), dict) and source[collection]),
            {},
        )
    conflicts = []
    duplicate_count = 0
    resolutions = resolutions or {}
    for collection in many_codes:
        group = metadata.get(collection, {})
        item_key = str(group.get("itemKey") or "")
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for source in normalized_instances:
            for item in source.get(collection, []):
                if isinstance(item, dict):
                    buckets[_identity(item, item_key)].append(item)
        merged = []
        for identity, candidates in buckets.items():
            unique: dict[str, dict[str, Any]] = {}
            for candidate in candidates:
                unique.setdefault(_content_hash(candidate), candidate)
            duplicate_count += len(candidates) - len(unique)
            choices = list(unique.values())
            if len(choices) == 1 or not item_key:
                merged.extend(choices)
                continue
            conflict_id = _hash({"collection": collection, "identity": identity})
            options = [{"candidateId": _content_hash(item), "value": _comparison_content(item),
                        "evidence": item.get("evidence", {})} for item in choices]
            selected_id = resolutions.get(conflict_id)
            selected = next((item for item in choices if _content_hash(item) == selected_id), None)
            conflicts.append({"id": conflict_id, "collection": collection,
                              "label": str(group.get("label") or collection),
                              "identity": identity,
                              "differingFields": _differing_fields(collection, choices, fields),
                              "options": options, "resolved": bool(selected)})
            if selected:
                merged.append(selected)
        payload[collection] = merged
    for source in normalized_instances:
        payload["instances"].extend(source.get("instances", []))
        payload["unmatched"].extend(source.get("unmatched", []))
    recognized = {name: len(payload.get(name, [])) for name in many_codes if payload.get(name)}
    return {
        "payload": payload,
        "recognizedCounts": recognized,
        "recognizedTotal": sum(recognized.values()),
        "validationSections": list(recognized),
        "duplicateCount": duplicate_count,
        "conflicts": conflicts,
        "unresolvedConflictCount": sum(not item["resolved"] for item in conflicts),
        "unmatched": payload["unmatched"],
        "coverage": {
            "recognizedTables": len({(item.get("evidence", {}).get("instanceId"),
                                      item.get("evidence", {}).get("richTextId"),
                                      item.get("evidence", {}).get("tableIndex"))
                                     for name in many_codes for item in payload.get(name, [])
                                     if item.get("evidence", {}).get("tableIndex")}),
            "unmatchedTables": len(payload["unmatched"]),
        },
    }
