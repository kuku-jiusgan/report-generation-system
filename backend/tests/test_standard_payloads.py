import pytest

from backend.app.services.standard_payloads import standard_context_payload


def _field(code: str, collection: str, path: str) -> dict:
    return {
        "fieldCode": code,
        "collectionCode": collection,
        "legacyJsonPath": path,
        "enabled": True,
    }


def _rule(rule_id: int, code: str, source_type: str) -> dict:
    return {
        "id": rule_id,
        "fieldCode": code,
        "name": f"{source_type} 来源",
        "sourceType": source_type,
        "config": {},
        "enabled": True,
    }


def test_context_uses_collection_code_for_uncategorized_excel_field() -> None:
    code = "uncategorized.field_046"
    collection = "dingliangxianjieguo"
    excel_rows = [{"field_046": "杂质甲", "injections": [{"field_014": 1}]}]
    data = {
        "source_payloads": {
            "EXCEL": {collection: excel_rows},
            "LIMS": {collection: []},
        },
        "field_sources": {code: {"type": "EXCEL"}},
    }

    payload = standard_context_payload(
        data,
        data["source_payloads"]["LIMS"],
        fields=[_field(code, collection, f"$.{collection}[*].field_046")],
        rules=[_rule(1, code, "EXCEL")],
    )

    assert payload[collection] == excel_rows


def test_context_does_not_require_unloaded_catalog_groups() -> None:
    excel_code = "uncategorized.field_046"
    lims_code = "instruments.name"
    data = {
        "source_payloads": {
            "EXCEL": {"dingliangxianjieguo": [{"field_046": "杂质甲"}]},
        },
        "field_sources": {excel_code: {"type": "EXCEL"}},
    }
    fields = [
        _field(excel_code, "dingliangxianjieguo", "$.dingliangxianjieguo[*].field_046"),
        _field(lims_code, "instruments", "$.instruments[*].name"),
    ]
    rules = [_rule(1, excel_code, "EXCEL"), _rule(2, lims_code, "LIMS")]

    payload = standard_context_payload(data, fields=fields, rules=rules)

    assert payload == {"dingliangxianjieguo": [{"field_046": "杂质甲"}]}


def test_context_rejects_multiple_direct_sources_in_one_collection() -> None:
    collection = "results"
    excel_code = "uncategorized.field_001"
    lims_code = "uncategorized.field_002"
    data = {
        "source_payloads": {
            "EXCEL": {collection: [{"field_001": "Excel"}]},
            "LIMS": {collection: [{"field_002": "LIMS"}]},
        },
        "field_sources": {
            excel_code: {"type": "EXCEL"},
            lims_code: {"type": "LIMS"},
        },
    }
    fields = [
        _field(excel_code, collection, f"$.{collection}[*].field_001"),
        _field(lims_code, collection, f"$.{collection}[*].field_002"),
    ]
    rules = [_rule(1, excel_code, "EXCEL"), _rule(2, lims_code, "LIMS")]

    with pytest.raises(ValueError, match="同时选择了多个直接来源"):
        standard_context_payload(data, fields=fields, rules=rules)
