from typing import Any

from ..database_common import now_iso


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

VALIDATION_SUMMARY_MAPPINGS = {
    "validationSummary[].field1": "validationSummary.field1",
    "validationSummary[].acceptanceCriteria": "validationSummary.acceptanceCriteria",
}
LIMIT_CALCULATION_MAPPINGS = {
    "limit[].impurityName": "limit.impurityName", "limit[].field2": "limit.field2",
    "limit[].field3": "limit.field3", "limit[].field4": "limit.field4",
    "limit[].field5": "limit.field5", "limit[].field6": "limit.field6",
}

# 一次性遗留映射修正标记：首次启动执行后，管理员对映射/章节/字段类型的修改不再被启动自愈回滚
LEGACY_MAPPING_MIGRATION = "2026_lims_catalog_defaults_legacy_mapping_v1"


def _ensure_lims_rule(database: Any, field_code: str, source_path: str) -> None:
    rules = [rule for rule in database.list_system_field_rules(field_code)
             if rule.get("sourceType") == "LIMS"]
    if not rules:
        database.save_system_field_rule({
            "fieldCode": field_code, "name": "已有标准数据路径", "sourceType": "LIMS",
            "transform": "TRIM", "priority": 100, "enabled": True,
            "config": {"extractionType": "NORMALIZED_PATH", "sourcePath": source_path},
        })


def ensure_lims_catalog_defaults(database: Any) -> None:
    for field_code, label, json_key, data_type in VALIDATION_SUMMARY_FIELDS:
        if not database.get_lims_field(field_code):
            database.upsert_lims_field({
                "fieldCode": field_code, "label": label, "groupCode": "验证结果汇总",
                "collectionCode": "validationSummary", "dataType": data_type, "cardinality": "MANY",
                "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": json_key,
                "legacyJsonPath": f"$.validationSummary[*].{json_key}", "enabled": True,
            })
        _ensure_lims_rule(database, field_code, f"$.validationSummary[*].{json_key}")
    _ensure_limit_calculation_fields(database)
    # 以下三条是首次部署的遗留数据修正；无条件重跑会把管理员改过的映射、章节归属和
    # 字段类型在每次重启时回滚。迁移标记保证只执行一次。
    if not database.migration_applied(LEGACY_MAPPING_MIGRATION):
        with database.connect() as connection:
            mappings = {**VALIDATION_SUMMARY_MAPPINGS, **LIMIT_CALCULATION_MAPPINGS}
            for field_code, standard_field_code in mappings.items():
                connection.execute(
                    """UPDATE admin_mapping_rules SET source_type='LIMS',standard_field_code=%s,
                       calculation_rule='',calculation_expression='',calculation_dependencies='[]',
                       source_pending=0,updated_at=%s WHERE field_code=%s""",
                    (standard_field_code, now_iso(), field_code),
                )
            connection.execute(
                """UPDATE admin_mapping_chapters SET chapter_id=(SELECT id FROM admin_template_chapters
                   WHERE code='3.2' LIMIT 1) WHERE mapping_id IN (SELECT id FROM admin_mapping_rules
                   WHERE field_code LIKE 'limit[]%%')"""
            )
            connection.execute(
                """UPDATE lims_field_catalog SET data_type='string',updated_at=%s
                   WHERE field_code IN ('impurity.field2','impurity.field4') AND data_type='decimal'""",
                (now_iso(),),
            )
        database.mark_migration_applied(LEGACY_MAPPING_MIGRATION)
    # 标签前缀归一化自带 NOT LIKE 守卫，可安全重复执行
    with database.connect() as connection:
        connection.execute(
            """UPDATE lims_field_catalog SET group_code='杂质信息 · 杂质列表',label='【杂质列表】'||label,
               updated_at=%s WHERE collection_code='impurity' AND label NOT LIKE '【杂质列表】%%'""", (now_iso(),)
        )


def _ensure_limit_calculation_fields(database: Any) -> None:
    for field_code, label, json_key, data_type in LIMIT_CALCULATION_FIELDS:
        if not database.get_lims_field(field_code):
            database.upsert_lims_field({
                "fieldCode": field_code, "label": label, "groupCode": "杂质信息 · 限度计算",
                "collectionCode": "limit", "dataType": data_type, "cardinality": "MANY",
                "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": json_key,
                "legacyJsonPath": f"$.limit[*].{json_key}", "enabled": True,
            })
        _ensure_lims_rule(database, field_code, f"$.limit[*].{json_key}")
