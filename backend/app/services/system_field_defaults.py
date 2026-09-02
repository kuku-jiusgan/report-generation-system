from ..database import Database

# 一次性遗留数据清理标记：首次启动执行后，管理员对这些字段/规则的修改不再被启动自愈回滚
LEGACY_CLEANUP_MIGRATION = "2026_system_field_defaults_legacy_cleanup_v1"


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
    with database.connect() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS system_field_chapters (
               field_code TEXT NOT NULL, chapter_id INTEGER NOT NULL, order_no INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY(field_code,chapter_id),
               FOREIGN KEY(field_code) REFERENCES lims_field_catalog(field_code)
                   ON UPDATE CASCADE ON DELETE CASCADE,
               FOREIGN KEY(chapter_id) REFERENCES admin_template_chapters(id) ON DELETE CASCADE)"""
        )
    field_code = _field_code(database, "narrative.chapter")
    if not database.get_lims_field(field_code):
        database.upsert_lims_field({
            "fieldCode": field_code, "label": "章节", "groupCode": "概述",
            "collectionCode": "narrative", "dataType": "richText", "cardinality": "ONE",
            "dbTable": "system_generated_fields", "dbColumn": "value_json", "jsonKey": "chapter",
            "legacyJsonPath": "$.narrative.chapter", "description": "由 AI 生成的概述章节内容",
            "outputFormat": "", "defaultValue": "", "validationRegex": "",
            "orderNo": 0, "enabled": True,
        })
    executor_code = _field_code(database, "project.executingOrganization")
    if not database.get_lims_field(executor_code):
        database.upsert_lims_field({
            "fieldCode": executor_code, "label": "执行单位", "groupCode": "项目信息",
            "collectionCode": "project", "dataType": "string", "cardinality": "ONE",
            "dbTable": "system_generated_fields", "dbColumn": "value_json", "jsonKey": "executingOrganization",
            "legacyJsonPath": "$.project.executingOrganization", "description": "方法开发及验证执行单位",
            "outputFormat": "", "defaultValue": "", "validationRegex": "", "orderNo": 20, "enabled": True,
        })
    if not database.list_system_field_rules(executor_code):
        database.save_system_field_rule({
            "fieldCode": executor_code, "name": "默认执行单位", "sourceType": "FIXED", "priority": 100,
            "config": {"value": "山东大学淄博生物医药研究院"}, "transform": "TRIM", "enabled": True,
        })
    ai_rules = [rule for rule in database.list_system_field_rules(field_code) if rule.get("sourceType") == "AI"]
    project_code = _field_code(database, "project.name")
    client_code = _field_code(database, "samples.clientName")
    validation_code = _field_code(database, "validationSummary.field1")
    ai_config = {
        "contextVariables": [
            {"fieldCode": project_code, "required": True, "mode": "FIRST", "separator": "、", "defaultValue": ""},
            {"fieldCode": client_code, "required": True, "mode": "FIRST", "separator": "、", "defaultValue": ""},
            {"fieldCode": executor_code, "required": True, "mode": "FIRST", "separator": "、", "defaultValue": ""},
            {"fieldCode": validation_code, "required": True, "mode": "JOIN_UNIQUE", "separator": "、", "defaultValue": ""},
        ],
        "promptTemplate": (
            "请仅根据以下事实生成一个正式、简洁的中文概述段落，不得补充未提供的信息：\n"
            f"方法名称：{{{{{project_code}}}}}\n委托单位：{{{{{client_code}}}}}\n"
            f"开发及验证单位：{{{{{executor_code}}}}}\n"
            f"验证内容：{{{{{validation_code}}}}}\n"
            "句式要求：说明该方法由委托单位委托执行单位开发并进行方法学验证，随后列出验证内容。"
        ),
        "outputType": "richText", "model": "", "maxLength": 800,
        "requireCitations": True, "requiresApproval": True,
    }
    # 以下清理只属于首次部署的遗留数据修正：无条件重跑会把管理员对映射、目录和规则的
    # 修改在每次重启时回滚。用迁移标记保证只执行一次，之后的启动只保留"缺失才播种"。
    legacy_cleanup_done = database.migration_applied(LEGACY_CLEANUP_MIGRATION)
    if not ai_rules:
        database.save_system_field_rule({
            "fieldCode": field_code, "name": "AI 生成概述章节", "sourceType": "AI", "priority": 10,
            "config": ai_config,
            "transform": "TRIM", "enabled": True,
        })
    elif not legacy_cleanup_done and not ai_rules[0].get("config", {}).get("contextVariables"):
        database.save_system_field_rule({**ai_rules[0], "config": ai_config}, ai_rules[0]["id"])
    if not legacy_cleanup_done:
        with database.connect() as connection:
            connection.execute(
                "UPDATE admin_mapping_rules SET standard_field_code=%s,source_type='SYSTEM' WHERE field_code='narrative.purpose'",
                ("uncategorized.field_001",),
            )
            connection.execute("UPDATE lims_field_catalog SET data_type='string' WHERE field_code=%s",
                               (_field_code(database, "samples.clientName"),))
            connection.execute(
                "DELETE FROM system_field_rules WHERE field_code=%s AND source_type<>'FIXED'", (executor_code,),
            )
            connection.execute(
                "DELETE FROM system_field_rules WHERE field_code=%s AND source_type<>'AI'", (field_code,),
            )
            chapter = connection.execute("SELECT id FROM admin_template_chapters WHERE code='1'").fetchone()
            if chapter:
                connection.execute(
                    """INSERT IGNORE INTO system_field_chapters(field_code,chapter_id,order_no)
                       VALUES(%s,%s,%s)""", (field_code, chapter["id"], 0),
                )
        database.mark_migration_applied(LEGACY_CLEANUP_MIGRATION)
