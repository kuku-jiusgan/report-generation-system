import json
import logging
import re
from typing import Any


RELATIVE_FILE_PATTERN = re.compile(r"(?<![A-Za-z0-9])/files/")
logger = logging.getLogger(__name__)


def absolute_lims_file_urls(value: Any, base_url: str) -> Any:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return value
    if isinstance(value, dict):
        return {key: absolute_lims_file_urls(item, base) for key, item in value.items()}
    if isinstance(value, list):
        return [absolute_lims_file_urls(item, base) for item in value]
    if isinstance(value, tuple):
        return tuple(absolute_lims_file_urls(item, base) for item in value)
    if isinstance(value, str):
        return RELATIVE_FILE_PATTERN.sub(f"{base}/files/", value)
    return value


def migrate_stored_lims_file_urls(database: Any, base_url: str) -> None:
    from .lims_normalizer import COLLECTION_ORDER, normalize_instance

    fields = database.list_lims_fields()
    rules = database.list_lims_parser_rules()
    with database.connect() as connection:
        experiments = connection.execute(
            "SELECT import_id,instance_id,raw_payload FROM lims_experiments WHERE raw_payload LIKE '%/files/%'"
        ).fetchall()
    for row in experiments:
        raw = absolute_lims_file_urls(json.loads(row["raw_payload"]), base_url)
        database.replace_lims_instance(
            row["import_id"], raw, normalize_instance(raw, fields, rules), COLLECTION_ORDER,
        )
    migrated_json = _migrate_report_json(database, "reports", "resolved_data", base_url)
    migrated_versions = _migrate_report_json(database, "report_versions", "data", base_url)
    if experiments or migrated_json or migrated_versions:
        logger.info(
            "LIMS文件链接迁移完成：实验记录=%s，报告=%s，历史版本=%s",
            len(experiments), migrated_json, migrated_versions,
        )


def _migrate_report_json(database: Any, table: str, column: str, base_url: str) -> int:
    with database.connect() as connection:
        rows = connection.execute(
            f"SELECT id,{column} FROM {table} WHERE {column} LIKE '%/files/%'"
        ).fetchall()
        for row in rows:
            payload = absolute_lims_file_urls(json.loads(row[column]), base_url)
            connection.execute(
                f"UPDATE {table} SET {column}=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), row["id"]),
            )
    return len(rows)
