from typing import Any

VALIDATION_SUMMARY_FIELDS = (
    ("validationSummary.field1", "验证项目", "field1", "string"),
    ("validationSummary.acceptanceCriteria", "接受标准", "acceptanceCriteria", "richText"),
)

LIMIT_CALCULATION_FIELDS = (
    ("limit.impurityName", "【限度计算】杂质名称", "impurityName", "string"),
    ("limit.field2", "【限度计算】AI值（ng/day）", "field2", "decimal"),
    ("limit.field3", "【限度计算】最大日剂量（mg/day）", "field3", "string"),
    ("limit.field4", "【限度计算】杂质限度（ppm）", "field4", "decimal"),
    ("limit.field5", "【限度计算】供试品溶液中API浓度（mg/ml）", "field5", "decimal"),
    ("limit.field6", "【限度计算】杂质限度浓度（ng/ml）", "field6", "decimal"),
)


def ensure_lims_catalog_defaults(database: Any) -> None:
    for field_code, label, json_key, data_type in VALIDATION_SUMMARY_FIELDS:
        if not database.get_lims_field(field_code):
            database.upsert_lims_field({
                "fieldCode": field_code, "label": label, "groupCode": "验证结果汇总",
                "collectionCode": "validationSummary", "dataType": data_type, "cardinality": "MANY",
                "jsonKey": json_key,
                "legacyJsonPath": f"$.validationSummary[*].{json_key}", "enabled": True,
            })
    _ensure_limit_calculation_fields(database)


def _ensure_limit_calculation_fields(database: Any) -> None:
    for field_code, label, json_key, data_type in LIMIT_CALCULATION_FIELDS:
        if not database.get_lims_field(field_code):
            database.upsert_lims_field({
                "fieldCode": field_code, "label": label, "groupCode": "杂质信息 · 限度计算",
                "collectionCode": "limit", "dataType": data_type, "cardinality": "MANY",
                "jsonKey": json_key,
                "legacyJsonPath": f"$.limit[*].{json_key}", "enabled": True,
            })
