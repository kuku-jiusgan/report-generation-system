import json
from typing import Any


def migrate_legacy_lims_rules(connection: Any) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lims_extraction_rules'",
    ).fetchone()
    if not exists:
        return
    for row in connection.execute("SELECT * FROM lims_extraction_rules").fetchall():
        config = json.loads(row["config"] or "{}")
        config.update({
            "extractionType": row["source_type"], "sourceUnitType": row["source_unit_type"],
            "sourcePath": row["source_path"], "sectionPattern": row["section_pattern"],
            "headerPattern": row["header_pattern"], "valuePattern": row["value_pattern"],
        })
        connection.execute(
            """INSERT OR IGNORE INTO system_field_rules
               (field_code,name,source_type,priority,config,transform,enabled,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (row["field_code"], row["name"], "LIMS", row["priority"],
             json.dumps(config, ensure_ascii=False), row["transform"], row["enabled"], row["updated_at"]),
        )
    connection.execute("DROP TABLE lims_extraction_rules")
