from ..database import Database


def _field_code(database: Database, legacy: str) -> str:
    with database.connect() as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standard_field_code_aliases'"
        ).fetchone()
        row = connection.execute(
            "SELECT new_code FROM standard_field_code_aliases WHERE old_code=?", (legacy,),
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
    if not ai_rules:
        database.save_system_field_rule({
            "fieldCode": field_code, "name": "AI 生成概述章节", "sourceType": "AI", "priority": 10,
            "config": ai_config,
            "transform": "TRIM", "enabled": True,
        })
    elif not ai_rules[0].get("config", {}).get("contextVariables"):
        database.save_system_field_rule({**ai_rules[0], "config": ai_config}, ai_rules[0]["id"])
    with database.connect() as connection:
        connection.execute(
            "UPDATE admin_mapping_rules SET standard_field_code=?,source_type='SYSTEM' WHERE field_code='narrative.purpose'",
            ("uncategorized.field_001",),
        )
        connection.execute("UPDATE lims_field_catalog SET data_type='string' WHERE field_code=?",
                           (_field_code(database, "samples.clientName"),))
        connection.execute(
            "DELETE FROM system_field_rules WHERE field_code=? AND source_type<>'FIXED'", (executor_code,),
        )
        connection.execute(
            "DELETE FROM system_field_rules WHERE field_code=? AND source_type<>'AI'", (field_code,),
        )
        chapter = connection.execute("SELECT id FROM admin_template_chapters WHERE code='1'").fetchone()
        if chapter:
            connection.execute(
                """INSERT OR IGNORE INTO system_field_chapters(field_code,chapter_id,order_no)
                   VALUES(?,?,?)""", (field_code, chapter["id"], 0),
            )
