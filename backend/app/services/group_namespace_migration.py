import json
import logging
from typing import Any

from ..database_common import now_iso


MIGRATION_KEY = "20260917_single_group_code_jiancexian"
LEGACY_CODE = "lod"
GROUP_CODE = "jiancexian"
logger = logging.getLogger(__name__)


def migrate_standard_payload(payload: dict[str, Any]) -> bool:
    """把一份标准载荷中的检测限集合迁移到唯一编组编码。"""
    changed = False
    legacy = payload.get(LEGACY_CODE)
    current = payload.get(GROUP_CODE)
    if legacy is not None and current is not None and legacy != current:
        raise ValueError("标准载荷同时存在 lod 和 jiancexian，且内容不一致")
    if LEGACY_CODE in payload:
        if GROUP_CODE not in payload:
            payload[GROUP_CODE] = payload[LEGACY_CODE]
        del payload[LEGACY_CODE]
        changed = True
    for collection, field in (("solutions", "validationCode"),
                              ("validationSummary", "validationItemCode")):
        records = payload.get(collection)
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict) and record.get(field) == LEGACY_CODE:
                record[field] = GROUP_CODE
                changed = True
    return changed


def _migrate_report_data(data: dict[str, Any]) -> bool:
    payloads = data.get("source_payloads")
    if not isinstance(payloads, dict):
        return False
    changed = False
    for source in ("EXCEL", "LIMS", "PDF", "PROTOCOL"):
        payload = payloads.get(source)
        if isinstance(payload, dict) and migrate_standard_payload(payload):
            changed = True
    return changed


def _migrate_json_column(connection: Any, table: str, key: str, column: str,
                         migrate: Any) -> int:
    migrated = 0
    rows = connection.execute(f"SELECT {key},{column} FROM {table}").fetchall()
    for row in rows:
        try:
            value = json.loads(row[column] or "{}")
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"{table}.{column} 包含无效 JSON，无法迁移编组编码") from error
        if not isinstance(value, dict) or not migrate(value):
            continue
        connection.execute(
            f"UPDATE {table} SET {column}=%s WHERE {key}=%s",
            (json.dumps(value, ensure_ascii=False), row[key]),
        )
        migrated += 1
    return migrated


def migrate_persisted_group_namespace(connection: Any) -> None:
    """一次性迁移仍会参与后续生成的持久化标准载荷。"""
    applied = connection.execute(
        "SELECT 1 FROM app_migrations WHERE `key`=%s", (MIGRATION_KEY,),
    ).fetchone()
    if not applied:
        migrated = sum((
            _migrate_json_column(connection, "source_documents", "id", "payload", migrate_standard_payload),
            _migrate_json_column(connection, "reports", "id", "resolved_data", _migrate_report_data),
            _migrate_json_column(connection, "report_versions", "id", "data", _migrate_report_data),
        ))
        connection.execute(
            "INSERT IGNORE INTO app_migrations(`key`,applied_at) VALUES(%s,%s)", (MIGRATION_KEY, now_iso()),
        )
        logger.info("持久化标准载荷编组编码迁移完成 documents=%d", migrated)
