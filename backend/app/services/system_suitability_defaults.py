import json

from ..database import Database, now_iso


MIGRATION = "2026_system_suitability_matrix_v5"


def ensure_system_suitability_defaults(database: Database) -> None:
    fields = (
        ("systemSuitability.impurityName", "杂质名称", "impurityName", "string", "MANY", "$.systemSuitability[*].impurityName"),
        ("systemSuitability.solutionName", "系统适用性溶液", "solutionName", "string", "MANY", "$.systemSuitability[*].solutionName"),
        ("systemSuitability.sequence", "进样序号", "sequence", "integer", "MANY", "$.systemSuitability[*].sequence"),
        ("systemSuitability.retentionTime", "保留时间（min）", "retentionTime", "decimal", "MANY", "$.systemSuitability[*].retentionTime"),
        ("systemSuitability.peakArea", "峰面积", "peakArea", "decimal", "MANY", "$.systemSuitability[*].peakArea"),
        ("systemSuitability.retentionTimeRsd", "保留时间 RSD", "retentionTimeRsd", "decimal", "MANY", "$.systemSuitability[*].retentionTimeRsd"),
        ("systemSuitability.peakAreaRsd", "峰面积 RSD", "peakAreaRsd", "decimal", "MANY", "$.systemSuitability[*].peakAreaRsd"),
    )
    for code, label, key, data_type, cardinality, path in fields:
        database.upsert_lims_field({
            "fieldCode": code, "label": label, "groupCode": "系统适用性结果",
            "collectionCode": "systemSuitability", "dataType": data_type, "cardinality": cardinality,
            "dbTable": "system_generated_fields", "dbColumn": "value_json", "jsonKey": key,
            "legacyJsonPath": path, "enabled": True,
        })
    database.upsert_lims_field({
        "fieldCode": "systemSuitability.conclusion", "label": "结论", "groupCode": "系统适用性汇总",
        "collectionCode": "systemSuitability", "dataType": "richText", "cardinality": "ONE",
        "dbTable": "system_generated_fields", "dbColumn": "value_json", "jsonKey": "conclusion",
        "legacyJsonPath": "$.systemSuitabilityConclusion", "enabled": True,
    })
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO system_field_groups(group_code,label,description,cardinality,item_path,item_key,order_no,enabled,updated_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE label=VALUES(label),cardinality=VALUES(cardinality),item_path=VALUES(item_path),updated_at=VALUES(updated_at)",
            ("systemSuitabilitySummary", "系统适用性汇总", "7.1 表格汇总字段", "ONE", "$.systemSuitabilitySummary", "", 1, 1, now_iso()),
        )
        connection.execute(
            "INSERT IGNORE INTO system_field_group_fields(group_code,field_code,field_path,order_no,required) VALUES(%s,%s,%s,%s,%s)",
            ("systemSuitability", "systemSuitability.impurityName", "impurityName", 0, 1),
        )
        for order_no, code in enumerate(("systemSuitability.solutionName", "systemSuitability.sequence", "systemSuitability.retentionTime", "systemSuitability.peakArea", "systemSuitability.retentionTimeRsd", "systemSuitability.peakAreaRsd"), 1):
            connection.execute(
                "INSERT IGNORE INTO system_field_group_fields(group_code,field_code,field_path,order_no,required) VALUES(%s,%s,%s,%s,%s)",
                ("systemSuitability", code, code.rsplit(".", 1)[-1], order_no, 0),
            )
        connection.execute(
            "INSERT IGNORE INTO system_field_group_fields(group_code,field_code,field_path,order_no,required) VALUES(%s,%s,%s,%s,%s)",
            ("systemSuitabilitySummary", "systemSuitability.conclusion", "conclusion", 0, 0),
        )
        chapter = connection.execute("SELECT id FROM admin_template_chapters WHERE code='7.1' LIMIT 1").fetchone()
        if chapter:
            for code in ("systemSuitability", "systemSuitabilitySummary"):
                connection.execute(
                    "INSERT IGNORE INTO system_field_group_chapters(group_code,chapter_id,order_no) VALUES(%s,%s,%s)",
                    (code, chapter["id"], 0 if code == "systemSuitability" else 1),
                )
    if not database.migration_applied(MIGRATION):
        layout = {
            "headerRows": 2,
            "columnGroups": [{
                "headerField": "impurityName",
                "columns": [
                    {"label": "保留时间（min）", "field": "retentionTime", "decimalPlaces": 3},
                    {"label": "峰面积", "field": "peakArea"},
                ],
            }],
            "dataRows": {"start": 3, "end": 8, "labelField": "solutionName", "sortField": "sequence"},
            "summaryRows": [{
                "row": 9, "label": "RSD（n=6，%）",
                "fields": ["retentionTimeRsd", "peakAreaRsd"],
            }],
            "conclusionRow": {"row": 10, "label": "结论", "field": "conclusion", "peakAreaRsdSuffix": "%", "template": "{recordCount}针系统适用性溶液中，{impurityNames}保留时间RSD均为{retentionTimeRsds}%，小于2.0%；峰面积RSD分别为{peakAreaRsds}，小于20.0%；符合标准规定。"},
        }
        connection = database.connect()
        with connection as cursor:
            cursor.execute(
                "DELETE FROM system_field_group_fields WHERE group_code='systemSuitability' "
                "AND field_code IN ('uncategorized.field_003','uncategorized.field_043','uncategorized.field_005','uncategorized.field_006')"
            )
            for order_no, code in enumerate((
                "systemSuitability.impurityName", "systemSuitability.solutionName",
                "systemSuitability.sequence", "systemSuitability.retentionTime",
                "systemSuitability.peakArea", "systemSuitability.retentionTimeRsd",
                "systemSuitability.peakAreaRsd",
            )):
                cursor.execute(
                    "UPDATE system_field_group_fields SET field_path=%s,order_no=%s "
                    "WHERE group_code='systemSuitability' AND field_code=%s",
                    (code.rsplit(".", 1)[-1], order_no, code),
                )
            cursor.execute(
                "UPDATE admin_table_rules SET mode='MATRIX',header_rows=%s,data_row_start=%s,data_row_end=%s,footer_rows=%s,matrix_layout=%s,updated_at=%s WHERE table_no='T13'",
                (2, 3, 8, 2, json.dumps(layout, ensure_ascii=False), now_iso()),
            )
            for code, path in {
                "systemSuitability.sequence": "$.systemSuitability[*].sequence",
                "systemSuitability.retentionTime": "$.systemSuitability[*].retentionTime",
                "systemSuitability.peakArea": "$.systemSuitability[*].peakArea",
            }.items():
                cursor.execute(
                    "UPDATE admin_mapping_rules SET repeat_type=%s,source_type=%s,source_path=%s,updated_at=%s "
                    "WHERE table_no=%s AND standard_field_code=%s",
                    ("ROW", "EXCEL", path, now_iso(), "T13", code),
                )
        database.mark_migration_applied(MIGRATION)
