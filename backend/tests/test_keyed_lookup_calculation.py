import pytest

from backend.app.services.keyed_lookup_calculation import (
    evaluate_keyed_lookup, validate_keyed_lookup_config,
)
from backend.app.services.system_field_resolver import resolve_system_fields


def _rule(config):
    return {
        "id": 1, "fieldCode": "summary.conclusion", "name": "按项目组装",
        "sourceType": "CALCULATED", "priority": 1, "config": config, "enabled": True,
    }


def test_keyed_lookup_returns_one_conclusion_for_each_summary_item():
    config = {
        "operation": "KEYED_LOOKUP", "matchFieldCode": "summary.item",
        "mappings": [
            {"matchValue": "系统适用性", "sourceFieldCode": "validation.suitability", "aggregation": "FIRST"},
            {"matchValue": "准确度", "sourceFieldCode": "validation.accuracy", "aggregation": "JOIN_UNIQUE", "separator": "\n"},
        ],
    }
    fields = [
        {"fieldCode": "summary.item", "legacyJsonPath": "$.summary[*].item", "collectionCode": "summary", "enabled": True},
        {"fieldCode": "summary.conclusion", "legacyJsonPath": "$.summary[*].conclusion", "collectionCode": "summary", "enabled": True},
        {"fieldCode": "validation.suitability", "legacyJsonPath": "$.suitability", "enabled": True},
        {"fieldCode": "validation.accuracy", "legacyJsonPath": "$.accuracy", "enabled": True},
    ]
    config = validate_keyed_lookup_config(config, "summary.conclusion", fields)
    assert evaluate_keyed_lookup(config, {
        "summary.item": ["系统适用性", "准确度"],
        "validation.suitability": "符合标准规定。",
        "validation.accuracy": ["第一条结论", "第二条结论", "第一条结论"],
    }) == ["符合标准规定。", "第一条结论\n第二条结论"]


def test_keyed_lookup_fails_when_project_has_no_mapping_or_value():
    config = {
        "operation": "KEYED_LOOKUP", "matchFieldCode": "summary.item",
        "mappings": [{"matchValue": "系统适用性", "sourceFieldCode": "validation.suitability", "aggregation": "FIRST"}],
    }
    with pytest.raises(ValueError, match="没有配置结论来源"):
        evaluate_keyed_lookup(config, {"summary.item": ["专属性"], "validation.suitability": "结果"})
    with pytest.raises(ValueError, match="没有结果"):
        evaluate_keyed_lookup(config, {"summary.item": ["系统适用性"], "validation.suitability": []})


def test_resolver_writes_keyed_result_into_nested_summary_view():
    fields = [
        {"fieldCode": "summary.item", "legacyJsonPath": "$.summary[*].item", "collectionCode": "summary", "enabled": True},
        {"fieldCode": "summary.conclusion", "legacyJsonPath": "$.summary[*].injections[*].text", "collectionCode": "summary", "enabled": True},
        {"fieldCode": "validation.suitability", "legacyJsonPath": "$.suitability", "enabled": True},
    ]
    payload = {"summary": [{"item": "系统适用性", "injections": [{}]}], "suitability": "符合标准规定。"}
    resolve_system_fields(fields, [_rule({
        "operation": "KEYED_LOOKUP", "matchFieldCode": "summary.item",
        "mappings": [{"matchValue": "系统适用性", "sourceFieldCode": "validation.suitability", "aggregation": "FIRST"}],
    })], payload, {})
    assert payload["summary"][0]["injections"][0]["text"] == "符合标准规定。"
