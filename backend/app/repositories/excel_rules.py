import json
from typing import Any

from ..database_common import now_iso


class ExcelRuleRepositoryMixin:
    def excel_rule_versions(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM excel_rule_versions ORDER BY id DESC").fetchall()
        return [self._excel_version(row) for row in rows]

    def active_excel_rules(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_rule_versions WHERE status='PUBLISHED' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._excel_version(row) if row else None

    def excel_rule_draft(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_rule_versions WHERE status='DRAFT' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._excel_version(row) if row else None

    def save_excel_rule_draft(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM excel_rule_versions WHERE status='DRAFT' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                connection.execute("UPDATE excel_rule_versions SET snapshot=?,validation_report='{}',updated_at=? WHERE id=?",
                                   (json.dumps(snapshot, ensure_ascii=False), timestamp, row["id"]))
                version_id = row["id"]
            else:
                cursor = connection.execute(
                    "INSERT INTO excel_rule_versions(status,snapshot,validation_report,created_at,updated_at) VALUES('DRAFT',?,'{}',?,?)",
                    (json.dumps(snapshot, ensure_ascii=False), timestamp, timestamp))
                version_id = cursor.lastrowid
            saved = connection.execute("SELECT * FROM excel_rule_versions WHERE id=?", (version_id,)).fetchone()
        return self._excel_version(saved)

    def record_excel_rule_validation(self, version_id: int, report: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE excel_rule_versions SET validation_report=?,updated_at=? WHERE id=? AND status='DRAFT'",
                               (json.dumps(report, ensure_ascii=False), now_iso(), version_id))

    def publish_excel_rule_draft(self, version_id: int) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM excel_rule_versions WHERE id=? AND status='DRAFT'", (version_id,)).fetchone()
            if not row:
                raise KeyError(version_id)
            report = json.loads(row["validation_report"] or "{}")
            if not report.get("valid"):
                raise ValueError("Excel 规则发布前必须通过样例试运行")
            connection.execute("UPDATE excel_rule_versions SET status='ARCHIVED' WHERE status='PUBLISHED'")
            connection.execute("UPDATE excel_rule_versions SET status='PUBLISHED',published_at=?,updated_at=? WHERE id=?",
                               (timestamp, timestamp, version_id))
            saved = connection.execute("SELECT * FROM excel_rule_versions WHERE id=?", (version_id,)).fetchone()
        return self._excel_version(saved)

    @staticmethod
    def _excel_version(row: Any) -> dict[str, Any]:
        return {"id": row["id"], "status": row["status"], "snapshot": json.loads(row["snapshot"]),
                "validationReport": json.loads(row["validation_report"] or "{}"),
                "createdAt": row["created_at"], "updatedAt": row["updated_at"], "publishedAt": row["published_at"]}
