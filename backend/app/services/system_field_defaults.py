from ..database import Database


def _field_code(database: Database, legacy: str) -> str:
    with database.connect() as connection:
        table = connection.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='standard_field_code_aliases'"
        ).fetchone()
        row = connection.execute(
            "SELECT new_code FROM standard_field_code_aliases WHERE old_code=%s", (legacy,),
        ).fetchone() if table else None
    return str(row["new_code"]) if row else legacy


def ensure_system_field_defaults(database: Database) -> None:
    field_code = _field_code(database, "narrative.chapter")
    if not database.get_lims_field(field_code):
        database.upsert_lims_field({
            "fieldCode": field_code, "label": "章节", "groupCode": "概述",
            "collectionCode": "narrative", "dataType": "richText", "cardinality": "ONE",
            "jsonKey": "chapter",
            "legacyJsonPath": "$.narrative.chapter", "description": "概述章节内容",
            "outputFormat": "", "defaultValue": "", "validationRegex": "",
            "orderNo": 0, "enabled": True,
        })
    executor_code = _field_code(database, "project.executingOrganization")
    if not database.get_lims_field(executor_code):
        database.upsert_lims_field({
            "fieldCode": executor_code, "label": "执行单位", "groupCode": "项目信息",
            "collectionCode": "project", "dataType": "string", "cardinality": "ONE",
            "jsonKey": "executingOrganization",
            "legacyJsonPath": "$.project.executingOrganization", "description": "方法开发及验证执行单位",
            "outputFormat": "", "defaultValue": "", "validationRegex": "", "orderNo": 20, "enabled": True,
        })
    if not database.list_system_field_rules(executor_code):
        database.save_system_field_rule({
            "fieldCode": executor_code, "name": "默认执行单位", "sourceType": "FIXED", "priority": 100,
            "config": {"value": "山东大学淄博生物医药研究院"}, "transform": "TRIM", "enabled": True,
        })
