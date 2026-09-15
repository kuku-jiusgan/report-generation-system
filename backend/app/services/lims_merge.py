from collections import defaultdict
from typing import Any

from .lims_normalizer import (
    COLLECTION_LABELS, COLLECTION_ORDER, _add_solution_views, _content_hash,
    _comparison_content, _hash, _semantic, normalize_instance, sort_validation_summary,
)


def _identity(collection: str, item: dict[str, Any]) -> str:
    if collection == "validationSummary":
        return _semantic(item.get("validationItemCode") or item.get("field1"))
    keys = {
        "samples": ("sampleName", "batchNo"),
        "referenceStandards": ("name", "batchNo"),
        "instruments": ("assetNo", "instrumentName", "model"),
        "columns": ("serialNo", "name"),
        "reagents": ("name", "batchNo", "stockNo"),
        "impurity": ("impurityName",), "limit": ("impurityName",),
        "solutions": ("validationCode", "name"),
        "methodParameters": ("field1", "field2"),
    }.get(collection)
    if not keys:
        return _hash({key: value for key, value in item.items() if key != "evidence"})
    return "|".join(_semantic(item.get(key)) for key in keys)


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
    payload: dict[str, Any] = {
        "project": normalized_instances[0]["project"], "document": normalized_instances[0]["document"],
        "approval": [], "instances": [], "unmatched": [],
    }
    conflicts = []
    duplicate_count = 0
    resolutions = resolutions or {}
    for collection in ["approval", *COLLECTION_ORDER]:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for source in normalized_instances:
            for item in source.get(collection, []):
                buckets[_identity(collection, item)].append(item)
        merged = []
        for identity, candidates in buckets.items():
            unique: dict[str, dict[str, Any]] = {}
            for candidate in candidates:
                unique.setdefault(_content_hash(candidate), candidate)
            duplicate_count += len(candidates) - len(unique)
            choices = list(unique.values())
            if len(choices) == 1 or collection not in {
                "samples", "referenceStandards", "instruments", "columns", "reagents",
                "impurity", "limit", "validationSummary", "solutions", "methodParameters",
            }:
                merged.extend(choices)
                continue
            conflict_id = _hash({"collection": collection, "identity": identity})
            options = [{"candidateId": _content_hash(item), "value": _comparison_content(item),
                        "evidence": item.get("evidence", {})} for item in choices]
            selected_id = resolutions.get(conflict_id)
            selected = next((item for item in choices if _content_hash(item) == selected_id), None)
            conflicts.append({"id": conflict_id, "collection": collection,
                              "label": COLLECTION_LABELS.get(collection, collection),
                              "identity": identity, "options": options, "resolved": bool(selected)})
            if selected:
                merged.append(selected)
        payload[collection] = merged
    payload["validationSummary"] = sort_validation_summary(payload.get("validationSummary", []))
    payload["lodConclusion"] = next((item.get("conclusion", "") for item in payload.get("lod", [])
                                     if item.get("conclusion")), "")
    for source in normalized_instances:
        payload["instances"].extend(source["instances"])
        payload["unmatched"].extend(source["unmatched"])
    _add_solution_views(payload)
    recognized = {name: len(payload.get(name, [])) for name in COLLECTION_ORDER if payload.get(name)}
    validation_names = [name for name in (
        "systemSuitability", "specificity", "lod", "loq", "linearity", "repeatability",
        "intermediatePrecision", "accuracy", "solutionStability", "robustnessResult", "sampleResults",
    ) if payload.get(name)]
    return {
        "payload": payload,
        "recognizedCounts": recognized,
        "recognizedTotal": sum(recognized.values()),
        "validationSections": validation_names,
        "duplicateCount": duplicate_count,
        "conflicts": conflicts,
        "unresolvedConflictCount": sum(not item["resolved"] for item in conflicts),
        "unmatched": payload["unmatched"],
        "coverage": {
            "recognizedTables": len({(item.get("evidence", {}).get("instanceId"),
                                      item.get("evidence", {}).get("richTextId"),
                                      item.get("evidence", {}).get("tableIndex"))
                                     for name in COLLECTION_ORDER for item in payload.get(name, [])
                                     if item.get("evidence", {}).get("tableIndex")}),
            "unmatchedTables": len(payload["unmatched"]),
        },
    }
