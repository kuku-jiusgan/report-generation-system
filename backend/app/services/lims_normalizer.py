import hashlib
import json
import re
from typing import Any

from lxml import html

from .lims_configured_extractor import apply_configured_extraction, configured_table_keys
from .lims_table_utils import table_grid
def record_collection_codes(groups: list[dict[str, Any]] | None = None,
                            fields: list[dict[str, Any]] | None = None) -> list[str]:
    configured = [
        str(group.get("groupCode") or "").strip()
        for group in groups or []
        if group.get("enabled", True) and str(group.get("cardinality") or "ONE").upper() == "MANY"
    ]
    configured.extend(
        str(field.get("collectionCode") or "").strip()
        for field in fields or []
        if field.get("enabled", True) and str(field.get("cardinality") or "ONE").upper() == "MANY"
    )
    return list(dict.fromkeys(code for code in configured if code))


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _semantic(value: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", _clean(value)).replace("（", "(").replace("）", ")")


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _business_content(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in {"evidence", "sourceRecordId"}}


def _content_hash(item: dict[str, Any]) -> str:
    return _hash(_business_content(item))


def _comparison_content(item: dict[str, Any]) -> dict[str, Any]:
    return _business_content(item)


def _unmatched_tables(instance: dict[str, Any], claimed: set[tuple[str, int]]) -> list[dict[str, Any]]:
    unmatched = []
    for rich_index, rich_text in enumerate(instance.get("richTexts", [])):
        try:
            root = html.fragment_fromstring(rich_text.get("html") or "", create_parent="div")
        except (TypeError, ValueError):
            continue
        rich_key = str(rich_text.get("id") or f"index:{rich_index}")
        for table_index, table in enumerate(root.xpath(".//table"), start=1):
            if (rich_key, table_index) in claimed:
                continue
            rows = table_grid(table)
            unmatched.append({
                "instanceId": instance.get("instanceId"), "instanceTitle": instance.get("title", ""),
                "sectionPath": rich_text.get("sectionPath", []), "richTextId": rich_text.get("id"),
                "tableIndex": table_index, "headers": rows[0] if rows else [], "rows": rows,
                "plainText": rich_text.get("plainText", ""), "evidence": rich_text.get("evidence", {}),
            })
    return unmatched


def normalize_instance(instance: dict[str, Any], fields: list[dict[str, Any]] | None = None,
                       extraction_rules: list[dict[str, Any]] | None = None,
                       groups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rules = extraction_rules or []
    result: dict[str, Any] = {
        "instances": [{
            "instanceId": instance.get("instanceId"), "title": instance.get("title", ""),
            "projectId": instance.get("projectId"), "version": instance.get("version"),
        }],
    }
    if fields and rules:
        apply_configured_extraction(instance, result, fields, rules)
    claimed = configured_table_keys(instance, rules)
    result["unmatched"] = _unmatched_tables(instance, claimed)
    return result


def merge_instances(instances: list[dict[str, Any]], resolutions: dict[str, str] | None = None,
                    fields: list[dict[str, Any]] | None = None,
                    extraction_rules: list[dict[str, Any]] | None = None,
                    groups: list[dict[str, Any]] | None = None,
                    normalized: bool = False) -> dict[str, Any]:
    from .lims_merge import merge_instances as _merge_instances

    return _merge_instances(instances, resolutions, fields, extraction_rules, groups, normalized)
