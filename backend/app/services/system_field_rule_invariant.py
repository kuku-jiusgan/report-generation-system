import logging
from typing import Any

from ..database_common import now_iso


logger = logging.getLogger(__name__)
MIGRATION_KEY = "20260919_single_system_field_rule_v1"
UNIQUE_INDEX = "uq_system_field_rules_field_code"


def rules_by_field(rules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Validate and index the one-rule-per-field contract."""
    indexed: dict[str, dict[str, Any]] = {}
    for rule in rules:
        field_code = str(rule.get("fieldCode") or "")
        if not field_code:
            raise ValueError("提取规则缺少系统字段编码")
        if field_code in indexed:
            raise ValueError(f"系统字段 {field_code} 存在多条提取规则，请先清理规则冲突")
        indexed[field_code] = rule
    return indexed


def ensure_single_system_field_rule_schema(database: Any) -> dict[str, int]:
    """Keep the most recently saved rule and enforce the invariant in MySQL."""
    removed = 0
    with database.connect() as connection:
        duplicates = connection.execute(
            """SELECT field_code FROM system_field_rules
               GROUP BY field_code HAVING COUNT(*) > 1 ORDER BY field_code"""
        ).fetchall()
        for duplicate in duplicates:
            field_code = str(duplicate["field_code"])
            rows = connection.execute(
                """SELECT id FROM system_field_rules WHERE field_code=%s
                   ORDER BY updated_at DESC,id DESC""",
                (field_code,),
            ).fetchall()
            keep_id = int(rows[0]["id"])
            cursor = connection.execute(
                "DELETE FROM system_field_rules WHERE field_code=%s AND id<>%s",
                (field_code, keep_id),
            )
            removed += int(cursor.rowcount)
            logger.info("系统字段重复规则已清理 field=%s keep_rule_id=%d", field_code, keep_id)
        index = connection.execute(
            """SELECT 1 FROM information_schema.statistics
               WHERE table_schema=DATABASE() AND table_name='system_field_rules'
                 AND index_name=%s""",
            (UNIQUE_INDEX,),
        ).fetchone()
        if not index:
            connection.execute(
                f"ALTER TABLE system_field_rules ADD UNIQUE INDEX {UNIQUE_INDEX}(field_code)"
            )
        migration = connection.execute(
            "SELECT 1 FROM app_migrations WHERE `key`=%s", (MIGRATION_KEY,),
        ).fetchone()
        if not migration:
            connection.execute(
                "INSERT INTO app_migrations(`key`,applied_at) VALUES(%s,%s)",
                (MIGRATION_KEY, now_iso()),
            )
    return {"removed": removed}
