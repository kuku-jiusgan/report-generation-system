from copy import deepcopy
from typing import Any


LOD_FIELDS = {
    "name": "field_007",
    "field2": "field_008",
    "field3": "field_009",
    "field4": "field_010",
    "field5": "field_011",
    "field6": "field_012",
    "field7": "field_013",
}
LOQ_FIELDS = {
    "sequence": "field_014",
    "field2": "field_015",
    "peakArea": "field_016",
    "field4": "field_017",
    "field5": "field_018",
    "field6": "field_019",
    "field7": "field_020",
}
VALIDATION_RESULT_KEYS = ("lod", "loq")
LINEARITY_FIELDS = {
    "solutionName": "field_021", "field2": "field_022", "peakArea": "field_023",
    "regressionEquation": "field_024", "correlationCoefficient": "field_025",
    "interceptRatio": "field_026", "predictedPeakArea": "field_027", "residual": "field_028",
}


def _custom_values(payload: dict[str, Any], key: str) -> list[Any]:
    custom = payload.get("custom")
    value = custom.get(key) if isinstance(custom, dict) else None
    return value if isinstance(value, list) else []


def _record_count(payload: dict[str, Any], fields: dict[str, str]) -> int:
    return max((len(_custom_values(payload, key)) for key in fields.values()), default=0)


def _records(payload: dict[str, Any], fields: dict[str, str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    values = {name: _custom_values(payload, key) for name, key in fields.items()}
    for index in range(_record_count(payload, fields)):
        record = {
            name: column[index] if index < len(column) else None
            for name, column in values.items()
        }
        if any(value not in (None, "") for value in record.values()):
            result.append(record)
    return result


def enrich_excel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    if "lod" not in payload:
        lod = _records(payload, LOD_FIELDS)
        if lod:
            payload["lod"] = lod
    if "loq" not in payload:
        loq = _records(payload, LOQ_FIELDS)
        if loq:
            payload["loq"] = loq
    if "linearity" not in payload:
        linearity = _records(payload, LINEARITY_FIELDS)
        if linearity:
            payload["linearity"] = linearity
    return payload


def merge_excel_validation_results(target: dict[str, Any], excel_payload: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(target)
    enriched = enrich_excel_payload(deepcopy(excel_payload))
    for key in VALIDATION_RESULT_KEYS:
        value = enriched.get(key)
        if isinstance(value, list) and value:
            merged[key] = value
    return merged
