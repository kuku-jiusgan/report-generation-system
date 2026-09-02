import json
from contextlib import contextmanager
from typing import Any, Iterator

from .database_common import now_iso
from .mysql_connection import mysql_connect
from .repositories.auth import AuthRepositoryMixin
from .repositories.excel_rules import ExcelRuleRepositoryMixin
from .repositories.lims_catalog import LimsCatalogRepositoryMixin
from .repositories.lims_evidence import LimsEvidenceRepositoryMixin
from .repositories.lims_instances import LimsInstanceRepositoryMixin
from .repositories.reports import ReportRepositoryMixin


class Database(
    LimsEvidenceRepositoryMixin,
    LimsInstanceRepositoryMixin,
    LimsCatalogRepositoryMixin,
    ReportRepositoryMixin,
    AuthRepositoryMixin,
    ExcelRuleRepositoryMixin,
):
    """MySQL persistence gateway for report business data."""

    def __init__(self, settings: Any):
        self.settings = settings

    @contextmanager
    def connect(self) -> Iterator[Any]:
        with mysql_connect(self.settings) as connection:
            yield connection

    def initialize(self) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name='app_migrations'"
            ).fetchone()
        if not row or int(row["count"]) != 1:
            raise RuntimeError("MySQL 数据库未完成 schema 初始化")

    @staticmethod
    def _decode(row: Any | None, json_fields: tuple[str, ...]) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for field in json_fields:
            item[field] = json.loads(item[field])
        return item

    def create_source(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO source_documents(id,file_name,stored_name,size,extracted_fields,source_type,payload,warnings,sha256,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (item["id"], item["file_name"], item["stored_name"], item["size"], "[]", item.get("source_type", "PDF"), "{}", "[]", item.get("sha256", ""), item["created_at"]),
            )
        return self.get_source(item["id"])

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM source_documents WHERE id=%s", (source_id,)).fetchone()
        return self._decode(row, ("extracted_fields", "payload", "warnings"))

    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM source_documents ORDER BY created_at DESC").fetchall()
        return [self._decode(row, ("extracted_fields", "payload", "warnings")) for row in rows]

    def update_extracted_fields(self, source_id: str, fields: list[dict[str, Any]]) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("UPDATE source_documents SET extracted_fields=%s WHERE id=%s", (json.dumps(fields, ensure_ascii=False), source_id))
        return self.get_source(source_id)

    def update_source_payload(self, source_id: str, payload: dict[str, Any], warnings: list[str], sha256: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("UPDATE source_documents SET payload=%s,warnings=%s,sha256=%s WHERE id=%s", (json.dumps(payload, ensure_ascii=False), json.dumps(warnings, ensure_ascii=False), sha256, source_id))
        return self.get_source(source_id)
