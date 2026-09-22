from typing import Any

from .calculation_engine import CalculationError


KEYED_LOOKUP = "KEYED_LOOKUP"
AGGREGATIONS = {"FIRST", "JOIN_UNIQUE"}


def is_keyed_lookup(config: dict[str, Any]) -> bool:
    return str(config.get("operation") or "").upper() == KEYED_LOOKUP


def calculated_dependencies(config: dict[str, Any]) -> list[str]:
    if not is_keyed_lookup(config):
        return [str(value) for value in config.get("dependencies", []) if value]
    codes = [str(config.get("matchFieldCode") or "")]
    codes.extend(
        str(item.get("sourceFieldCode") or "")
        for item in config.get("mappings", []) if isinstance(item, dict)
    )
    return list(dict.fromkeys(code for code in codes if code))


def validate_keyed_lookup_config(
    config: dict[str, Any], target_field_code: str, fields: list[dict[str, Any]],
) -> dict[str, Any]:
    known = {str(field["fieldCode"]): field for field in fields}
    match_code = str(config.get("matchFieldCode") or "").strip()
    if match_code not in known:
        raise ValueError("按项目匹配字段不存在")
    target = known.get(target_field_code)
    if target is None:
        raise ValueError("按项目组装的目标字段不存在")
    if not target.get("collectionCode") or target.get("collectionCode") != known[match_code].get("collectionCode"):
        raise ValueError("按项目匹配字段必须与目标字段属于同一编组")

    mappings = config.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("按项目组装至少需要一条映射")
    normalized = []
    seen: set[str] = set()
    for index, item in enumerate(mappings, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条项目映射格式无效")
        match_value = str(item.get("matchValue") or "").strip()
        source_code = str(item.get("sourceFieldCode") or "").strip()
        aggregation = str(item.get("aggregation") or "").upper()
        if not match_value:
            raise ValueError(f"第 {index} 条项目映射的匹配值不能为空")
        if match_value in seen:
            raise ValueError(f"项目匹配值重复：{match_value}")
        if source_code not in known:
            raise ValueError(f"项目 {match_value} 的来源字段不存在：{source_code}")
        if source_code == target_field_code:
            raise ValueError("按项目组装规则不能依赖目标字段自身")
        if aggregation not in AGGREGATIONS:
            raise ValueError(f"项目 {match_value} 的聚合方式必须是 FIRST 或 JOIN_UNIQUE")
        separator = str(item.get("separator") or "\n")
        normalized.append({
            "matchValue": match_value, "sourceFieldCode": source_code,
            "aggregation": aggregation, "separator": separator,
        })
        seen.add(match_value)
    return {**config, "operation": KEYED_LOOKUP, "matchFieldCode": match_code,
            "mappings": normalized}


def _aggregate(value: Any, aggregation: str, separator: str, key: str) -> str:
    values = value if isinstance(value, list) else [value]
    available = [str(item).strip() for item in values if item not in (None, "", [], {})]
    if not available:
        raise CalculationError(f"项目“{key}”的结论来源没有结果")
    if aggregation == "FIRST":
        return available[0]
    unique = list(dict.fromkeys(available))
    return separator.join(unique)


def evaluate_keyed_lookup(config: dict[str, Any], values: dict[str, Any]) -> list[str]:
    match_code = str(config.get("matchFieldCode") or "")
    keys = values.get(match_code)
    if not isinstance(keys, list) or not keys:
        raise CalculationError(f"按项目匹配字段没有可用的汇总行：{match_code}")
    mappings = {str(item["matchValue"]): item for item in config.get("mappings", [])}
    result = []
    for raw_key in keys:
        key = str(raw_key or "").strip()
        item = mappings.get(key)
        if item is None:
            raise CalculationError(f"验证项目“{key}”没有配置结论来源")
        result.append(_aggregate(
            values.get(str(item["sourceFieldCode"])), str(item["aggregation"]),
            str(item.get("separator") or "\n"), key,
        ))
    return result
