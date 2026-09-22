from typing import Any

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


def ensure_system_field_rule_source_schema(database: Any) -> None:
    """Validate the existing one-rule-per-field/source database schema without modifying it."""
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
            raise RuntimeError("system_field_rules.source_type 必须是 VARCHAR(32)，请检查数据库结构")
        legacy_index = connection.execute(
            """SELECT 1 FROM information_schema.statistics
               WHERE table_schema=DATABASE() AND table_name='system_field_rules'
                 AND index_name=%s""",
            (LEGACY_UNIQUE_INDEX,),
        ).fetchone()
        if legacy_index:
            raise RuntimeError(f"存在旧索引 {LEGACY_UNIQUE_INDEX}，请检查数据库结构")
        index = connection.execute(
            """SELECT 1 FROM information_schema.statistics
               WHERE table_schema=DATABASE() AND table_name='system_field_rules'
                 AND index_name=%s""",
            (UNIQUE_INDEX,),
        ).fetchone()
        if not index:
            raise RuntimeError(f"缺少唯一索引 {UNIQUE_INDEX}，请检查数据库结构")
