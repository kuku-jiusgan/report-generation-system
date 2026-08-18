import json
from typing import Any

from ..database_common import now_iso


class ReportRepositoryMixin:
    """Reports, audit changes, versions and immutable generation history."""

    def list_reports(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if owner_id:
                rows = connection.execute(
                    "SELECT * FROM reports WHERE created_by=? ORDER BY updated_at DESC", (owner_id,),
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM reports ORDER BY updated_at DESC").fetchall()
        return [self._decode(row, ("resolved_data",)) for row in rows]

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return self._decode(row, ("resolved_data",))

    def create_report(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO reports(id,title,status,source_document_id,resolved_data,output_name,
                   created_at,updated_at,created_by,updated_by,word_edit_locked,word_edited_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["id"], item["title"], item["status"], item.get("source_document_id"),
                 json.dumps(item["resolved_data"], ensure_ascii=False), item.get("output_name"),
                 item["created_at"], item["updated_at"], item.get("created_by"), item.get("updated_by"),
                 int(item.get("word_edit_locked", False)), item.get("word_edited_at")),
            )
        return self.get_report(item["id"])

    def update_report(self, report_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"title", "status", "source_document_id", "resolved_data", "output_name", "updated_by",
                   "word_edit_locked", "word_edited_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        values["updated_at"] = now_iso()
        if "resolved_data" in values:
            values["resolved_data"] = json.dumps(values["resolved_data"], ensure_ascii=False)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE reports SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                (*values.values(), report_id),
            )
        return self.get_report(report_id)

    def delete_report(self, report_id: str) -> list[str]:
        with self.connect() as connection:
            outputs = [str(row["output_name"]) for row in connection.execute(
                "SELECT output_name FROM report_generation_history WHERE report_id=? AND output_name IS NOT NULL",
                (report_id,),
            ).fetchall()]
            connection.execute("DELETE FROM reports WHERE id=?", (report_id,))
        return outputs

    def migration_applied(self, key: str) -> bool:
        with self.connect() as connection:
            return bool(connection.execute("SELECT 1 FROM app_migrations WHERE key=?", (key,)).fetchone())

    def clear_report_test_data(self) -> None:
        with self.connect() as connection:
            for table in ("report_generation_history", "change_history", "report_versions", "reports", "source_documents"):
                connection.execute(f"DELETE FROM {table}")

    def mark_migration_applied(self, key: str) -> None:
        with self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO app_migrations(key,applied_at) VALUES(?,?)", (key, now_iso()))

    def add_change(self, report_id: str, field_code: str, old_value: str, new_value: str,
                   operator: str = "当前用户", reason: str = "人工编辑") -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO change_history(report_id,field_code,old_value,new_value,operator,reason,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (report_id, field_code, old_value, new_value, operator, reason, now_iso()),
            )

    def list_changes(self, report_id: str, field_code: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM change_history WHERE report_id=?", [report_id]
        if field_code:
            sql += " AND field_code=?"
            params.append(field_code)
        with self.connect() as connection:
            rows = connection.execute(sql + " ORDER BY id DESC", params).fetchall()
        return [dict(row) for row in rows]

    def create_version(self, report_id: str, data: dict[str, Any], note: str = "手工保存") -> dict[str, Any]:
        with self.connect() as connection:
            version_no = connection.execute(
                "SELECT COALESCE(MAX(version_no),0)+1 FROM report_versions WHERE report_id=?", (report_id,),
            ).fetchone()[0]
            cursor = connection.execute(
                "INSERT INTO report_versions(report_id,version_no,note,data,created_at) VALUES(?,?,?,?,?)",
                (report_id, version_no, note, json.dumps(data, ensure_ascii=False), now_iso()),
            )
        return self.get_version(report_id, cursor.lastrowid)

    def get_version(self, report_id: str, version_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM report_versions WHERE report_id=? AND id=?", (report_id, version_id),
            ).fetchone()
        return self._decode(row, ("data",))

    def list_versions(self, report_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM report_versions WHERE report_id=? ORDER BY version_no DESC", (report_id,),
            ).fetchall()
        return [self._decode(row, ("data",)) for row in rows]

    def create_generation(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO report_generation_history(id,report_id,version_id,generated_by,status,
                   output_name,error_message,generated_at,legacy) VALUES(?,?,?,?,?,?,?,?,?)""",
                (item["id"], item["report_id"], item.get("version_id"), item.get("generated_by"), item["status"],
                 item.get("output_name"), item.get("error_message", ""), item.get("generated_at", now_iso()),
                 int(item.get("legacy", False))),
            )
        return self.get_generation(item["id"])

    def update_generation(self, generation_id: str, **changes: Any) -> dict[str, Any] | None:
        values = {key: value for key, value in changes.items() if key in {"status", "output_name", "error_message"}}
        if values:
            with self.connect() as connection:
                connection.execute(
                    f"UPDATE report_generation_history SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                    (*values.values(), generation_id),
                )
        return self.get_generation(generation_id)

    def get_generation(self, generation_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(self._generation_select() + " WHERE g.id=?", (generation_id,)).fetchone()
        return self._decode(row, ("resolved_data",))

    @staticmethod
    def _generation_select() -> str:
        return """SELECT g.*,r.title,r.status AS report_status,r.resolved_data,
                  u.username,u.display_name,v.version_no FROM report_generation_history g
                  JOIN reports r ON r.id=g.report_id LEFT JOIN auth_users u ON u.id=g.generated_by
                  LEFT JOIN report_versions v ON v.id=g.version_id"""

    def is_generation_output(self, output_name: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM report_generation_history WHERE output_name=? LIMIT 1", (output_name,),
            ).fetchone()
        return bool(row)

    @staticmethod
    def _generation_filters(query: str, status: str, user_id: str, date_from: str, date_to: str):
        where, params = [], []
        for value, clause in ((status, "g.status=?"), (user_id, "g.generated_by=?"),
                              (date_from, "g.generated_at>=?"), (date_to, "g.generated_at<=?")):
            if value:
                where.append(clause)
                params.append(value)
        if query:
            where.insert(0, "(r.title LIKE ? OR json_extract(r.resolved_data,'$.report_no') LIKE ?)")
            params[0:0] = [f"%{query}%"] * 2
        return (f"WHERE {' AND '.join(where)}" if where else ""), params

    def list_generations(self, query: str = "", status: str = "", user_id: str = "", date_from: str = "",
                         date_to: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
        clause, params = self._generation_filters(query, status, user_id, date_from, date_to)
        with self.connect() as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM report_generation_history g JOIN reports r ON r.id=g.report_id {clause}", params,
            ).fetchone()[0])
            rows = connection.execute(
                f"{self._generation_select()} {clause} ORDER BY g.generated_at DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {"total": total, "page": page, "pageSize": page_size,
                "items": [self._decode(row, ("resolved_data",)) for row in rows]}
