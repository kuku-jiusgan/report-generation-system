import logging
from typing import Any

from ..database_common import now_iso


logger = logging.getLogger(__name__)
MIGRATION_KEY = "20260921_system_field_rule_source_v2"
LEGACY_UNIQUE_INDEX = "uq_system_field_rules_field_code"
UNIQUE_INDEX = "uq_system_field_rules_field_source"


def rules_by_field(rules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index rules already restricted to one source."""
    indexed: dict[str, dict[str, Any]] = {}
    for rule in rules:
        field_code = str(rule.get("fieldCode") or "")
        if not field_code:
            raise ValueError("提取规则缺少系统字段编码")
        if field_code in indexed:
            raise ValueError(f"系统字段 {field_code} 在同一来源存在多条提取规则，请先清理规则冲突")
        indexed[field_code] = rule
    return indexed


def rules_by_field_source(
    rules: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Validate and index the one-rule-per-field-and-source contract."""
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    for rule in rules:
        field_code = str(rule.get("fieldCode") or "")
        source_type = str(rule.get("sourceType") or "LIMS").upper()
        if not field_code:
            raise ValueError("提取规则缺少系统字段编码")
        sources = indexed.setdefault(field_code, {})
        if source_type in sources:
            raise ValueError(
                f"系统字段 {field_code} 的 {source_type} 来源存在多条提取规则，请先清理规则冲突"
            )
        sources[source_type] = rule
    return indexed


def ensure_system_field_rule_source_schema(database: Any) -> dict[str, int]:
    """Keep the latest rule per field/source and enforce that key in MySQL."""
    removed = 0
    with database.connect() as connection:
        source_type = connection.execute(
            """SELECT data_type,character_maximum_length FROM information_schema.columns
               WHERE table_schema=DATABASE() AND table_name='system_field_rules'
                 AND column_name='source_type'"""
        ).fetchone()
        if not source_type:
            raise RuntimeError("system_field_rules 缺少 source_type 列")
        if (str(source_type[0]).lower() != "varchar"
                or int(source_type[1] or 0) != 32):
            connection.execute(
                "ALTER TABLE system_field_rules MODIFY source_type VARCHAR(32) NOT NULL"
            )
        legacy_index = connection.execute(
            """SELECT 1 FROM information_schema.statistics
               WHERE table_schema=DATABASE() AND table_name='system_field_rules'
                 AND index_name=%s""",
            (LEGACY_UNIQUE_INDEX,),
        ).fetchone()
        if legacy_index:
            connection.execute(
                f"ALTER TABLE system_field_rules DROP INDEX {LEGACY_UNIQUE_INDEX}"
            )
        duplicates = connection.execute(
            """SELECT field_code,source_type FROM system_field_rules
               GROUP BY field_code,source_type HAVING COUNT(*) > 1
               ORDER BY field_code,source_type"""
        ).fetchall()
        for duplicate in duplicates:
            field_code = str(duplicate["field_code"])
            source_type = str(duplicate["source_type"])
            rows = connection.execute(
                """SELECT id FROM system_field_rules WHERE field_code=%s AND source_type=%s
                   ORDER BY updated_at DESC,id DESC""",
                (field_code, source_type),
            ).fetchall()
            keep_id = int(rows[0]["id"])
            cursor = connection.execute(
                "DELETE FROM system_field_rules WHERE field_code=%s AND source_type=%s AND id<>%s",
                (field_code, source_type, keep_id),
            )
            removed += int(cursor.rowcount)
            logger.info(
                "系统字段同来源重复规则已清理 field=%s source=%s keep_rule_id=%d",
                field_code, source_type, keep_id,
            )
        index = connection.execute(
            """SELECT 1 FROM information_schema.statistics
               WHERE table_schema=DATABASE() AND table_name='system_field_rules'
                 AND index_name=%s""",
            (UNIQUE_INDEX,),
        ).fetchone()
        if not index:
            connection.execute(
                f"ALTER TABLE system_field_rules ADD UNIQUE INDEX {UNIQUE_INDEX}(field_code,source_type)"
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
