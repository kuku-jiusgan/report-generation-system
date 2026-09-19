import json
import logging
from typing import Any

from ..database import now_iso
from .lims_direct_rule_defaults import PROFILE_COLLECTIONS, direct_rule_config
from .lims_rule_schema import DIRECT_TYPES


logger = logging.getLogger(__name__)
MIGRATION_KEY = "20260919_lims_direct_field_rules_v1"
DEPRECATED_KEYS = {
    "parser", "parserProfile", "inputField", "unitType", "tableSelector",
    "outputCollection", "outputField", "preserveEvidence",
}


def _clean_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key not in DEPRECATED_KEYS}


def _rule_item(rule: dict[str, Any], config: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    return {
        "fieldCode": rule["fieldCode"], "name": name or rule["name"], "sourceType": "LIMS",
        "priority": rule.get("priority", 100), "config": config,
        "transform": rule.get("transform", "TRIM"), "enabled": rule.get("enabled", True),
    }


def _field_key(field: dict[str, Any]) -> str:
    return str(field.get("jsonKey") or field.get("fieldCode", "").rsplit(".", 1)[-1])


def _converted_config(field: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    current = rule.get("config") if isinstance(rule.get("config"), dict) else {}
    extraction_type = str(current.get("extractionType") or "").upper()
    if extraction_type in DIRECT_TYPES:
        return _clean_config(current)
    profile = str(current.get("parserProfile") or "")
    collection = PROFILE_COLLECTIONS.get(profile, str(field.get("collectionCode") or ""))
    converted = direct_rule_config(collection, _field_key(field))
    if not converted:
        return None
    for key in ("sectionPattern", "headerPattern", "rowPattern", "valuePattern", "replacePattern", "replaceWith"):
        if current.get(key) not in (None, ""):
            converted[key] = current[key]
    return converted


def _migrate_group_rules(database: Any, fields: dict[str, dict[str, Any]]) -> int:
    migrated = 0
    with database.connect() as connection:
        rows = connection.execute("SELECT group_code,source_mappings FROM system_field_groups").fetchall()
    for row in rows:
        mappings = json.loads(row["source_mappings"] or "[]")
        retained = []
        for mapping in mappings:
            if str(mapping.get("sourceType") or "").upper() != "LIMS":
                retained.append(mapping)
                continue
            columns = mapping.get("columnMappings", mapping.get("fieldMappings", mapping.get("columns", [])))
            for column in columns if isinstance(columns, list) else []:
                field_code = str(column.get("fieldCode") or "")
                field = fields.get(field_code)
                column_pattern = str(column.get("columnPattern", column.get("column", "")) or "")
                if not field or not column_pattern:
                    raise ValueError(f"LIMS 编组来源映射无法迁移：{row['group_code']} / {field_code or '未配置字段'}")
                config = {
                    "extractionType": "HTML_TABLE_COLUMN", "recordMode": "ROWS", "headerRows": 1,
                    "sourcePath": column_pattern, "sectionPattern": mapping.get("sectionPattern", ""),
                    "headerPattern": mapping.get("headerPattern", ""), "rowPattern": mapping.get("rowPattern", ""),
                }
                existing = [item for item in database.list_system_field_rules(field_code)
                            if item.get("sourceType") == "LIMS"]
                replaceable = next((item for item in existing if str(item.get("config", {}).get("extractionType") or "").upper()
                                    not in DIRECT_TYPES), None)
                item = replaceable or {
                    "fieldCode": field_code, "name": "LIMS HTML 表格列 → 标准字段", "priority": 100,
                    "transform": "TRIM", "enabled": True,
                }
                database.save_system_field_rule(_rule_item(item, config, "LIMS HTML 表格列 → 标准字段"),
                                                item.get("id"))
                migrated += 1
        if len(retained) != len(mappings):
            with database.connect() as connection:
                connection.execute(
                    "UPDATE system_field_groups SET source_mappings=%s,updated_at=%s WHERE group_code=%s",
                    (json.dumps(retained, ensure_ascii=False), now_iso(), row["group_code"]),
                )
    return migrated


def migrate_lims_direct_rules(database: Any) -> dict[str, int]:
    with database.connect() as connection:
        if connection.execute(
            "SELECT 1 FROM app_migrations WHERE `key`=%s", (MIGRATION_KEY,),
        ).fetchone():
            return {"migrated": 0, "groupMappings": 0, "created": 0, "removed": 0}
    fields = {field["fieldCode"]: field for field in database.list_lims_fields(True)}
    group_count = _migrate_group_rules(database, fields)
    migrated = removed = created = 0
    for field_code, field in fields.items():
        lims_rules = [rule for rule in database.list_system_field_rules(field_code)
                      if rule.get("sourceType") == "LIMS"]
        for rule in lims_rules:
            config = _converted_config(field, rule)
            if config:
                if config != rule.get("config"):
                    database.save_system_field_rule(
                        _rule_item(rule, config, "LIMS 原始数据 → 标准字段"), rule["id"],
                    )
                    migrated += 1
            else:
                database.delete_system_field_rule(rule["id"])
                removed += 1
        remaining = [rule for rule in database.list_system_field_rules(field_code)
                     if rule.get("sourceType") == "LIMS"]
        default = direct_rule_config(str(field.get("collectionCode") or ""), _field_key(field))
        if not remaining and default:
            database.save_system_field_rule({
                "fieldCode": field_code, "name": "LIMS 原始数据 → 标准字段", "sourceType": "LIMS",
                "priority": 100, "config": default, "transform": "TRIM", "enabled": True,
            })
            created += 1
    if migrated or removed or created or group_count:
        logger.info(
            "LIMS 字段规则直连迁移完成 migrated=%d groupMappings=%d created=%d removedLegacy=%d",
            migrated, group_count, created, removed,
        )
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO app_migrations(`key`,applied_at) VALUES(%s,%s)",
            (MIGRATION_KEY, now_iso()),
        )
    return {"migrated": migrated, "groupMappings": group_count, "created": created, "removed": removed}
