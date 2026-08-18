import json
from collections import Counter
from typing import Any

from ..database import now_iso


class RuntimeVersionRepositoryMixin:
    """Published runtime template lookup and legacy rule-version persistence."""

    def summary(self) -> dict[str, Any]:
        mappings, table_rules = self.list_mappings(), self.list_table_rules()
        return {
            "mappingCount": len(mappings), "enabledMappings": sum(item["enabled"] for item in mappings),
            "tableCount": len(table_rules), "enabledTables": sum(item["enabled"] for item in table_rules),
            "sourceCounts": dict(Counter(item["sourceType"] for item in mappings)),
            "pendingCount": sum(item["sourcePending"] for item in mappings),
            "aiRuleCount": len(self.list_ai_rules()), "publishedVersion": self.latest_published_version(),
        }

    def latest_published_version(self) -> int | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT MAX(version_no) FROM admin_rule_versions WHERE status='PUBLISHED'"
            ).fetchone()
        return row[0] if row and row[0] else None

    def active_runtime_rules(self) -> tuple[dict[str, Any], str | None]:
        with self.database.connect() as connection:
            catalog = connection.execute(
                """SELECT v.snapshot,v.template_file FROM admin_template_versions v
                   JOIN admin_template_workspace w ON w.active_template_id=v.template_id
                   WHERE w.id=1 AND v.status='PUBLISHED' ORDER BY v.version_no DESC LIMIT 1"""
            ).fetchone()
            if catalog:
                return json.loads(catalog["snapshot"]), catalog["template_file"]
            legacy = connection.execute(
                """SELECT snapshot,compiled_template FROM admin_rule_versions
                   WHERE status='PUBLISHED' ORDER BY version_no DESC LIMIT 1"""
            ).fetchone()
        return (json.loads(legacy["snapshot"]), legacy["compiled_template"]) if legacy else (self.snapshot(), None)

    def active_runtime_template(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT t.id AS template_id,t.code AS template_code,t.name AS template_name,v.id AS version_id,
                          v.version_no,v.snapshot,v.template_file FROM admin_template_versions v
                   JOIN admin_templates t ON t.id=v.template_id
                   JOIN admin_template_workspace w ON w.active_template_id=v.template_id
                   WHERE w.id=1 AND v.status='PUBLISHED' ORDER BY v.version_no DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        return {
            "templateId": item["template_id"], "templateCode": item["template_code"],
            "templateName": item["template_name"], "versionId": item["version_id"],
            "versionNo": item["version_no"], "snapshot": json.loads(item["snapshot"]),
            "templateFile": item["template_file"],
        }

    def create_version(
        self, snapshot: dict[str, Any], validation: dict[str, Any], compiled_template: str,
        note: str, publish: bool,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            version_no = connection.execute(
                "SELECT COALESCE(MAX(version_no),0)+1 FROM admin_rule_versions"
            ).fetchone()[0]
            if publish:
                connection.execute("UPDATE admin_rule_versions SET status='ARCHIVED' WHERE status='PUBLISHED'")
            timestamp = now_iso()
            cursor = connection.execute(
                """INSERT INTO admin_rule_versions(version_no,status,note,snapshot,validation_report,compiled_template,
                   created_at,published_at) VALUES(?,?,?,?,?,?,?,?)""",
                (version_no, "PUBLISHED" if publish else "DRAFT", note,
                 json.dumps(snapshot, ensure_ascii=False), json.dumps(validation, ensure_ascii=False),
                 compiled_template, timestamp, timestamp if publish else None),
            )
            row = connection.execute("SELECT * FROM admin_rule_versions WHERE id=?", (cursor.lastrowid,)).fetchone()
        return self._version_to_api(dict(row))

    def list_versions(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_rule_versions ORDER BY version_no DESC"
            ).fetchall()]
        return [self._version_to_api(row) for row in rows]

    @staticmethod
    def _version_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"], "versionNo": row["version_no"], "status": row["status"], "note": row["note"],
            "validationReport": json.loads(row["validation_report"]), "compiledTemplate": row["compiled_template"],
            "createdAt": row["created_at"], "publishedAt": row["published_at"],
        }
