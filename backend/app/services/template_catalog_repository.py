import json
import uuid
from typing import Any

from ..database import now_iso


class TemplateCatalogRepositoryMixin:
    """Template catalog and catalog-version persistence operations."""

    @staticmethod
    def _catalog_version_to_api(row: dict[str, Any]) -> dict[str, Any]:
        validation = json.loads(row.get("validation_report") or "{}")
        return {
            "id": row["id"], "templateId": row["template_id"], "versionNo": row["version_no"],
            "status": row["status"], "note": row["note"], "templateFile": row.get("template_file"),
            "validationReport": validation, "createdAt": row["created_at"], "updatedAt": row["updated_at"],
            "publishedAt": row.get("published_at"),
        }

    def list_templates(self) -> list[dict[str, Any]]:
        active = self.active_workspace()
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT t.*,COUNT(v.id) AS version_count,MAX(v.version_no) AS latest_version,
                   MAX(CASE WHEN v.status='PUBLISHED' THEN v.version_no END) AS published_version
                   FROM admin_templates t LEFT JOIN admin_template_versions v ON v.template_id=t.id
                   GROUP BY t.id ORDER BY t.updated_at DESC"""
            ).fetchall()]
        return [{
            "id": row["id"], "code": row["code"], "name": row["name"],
            "description": row["description"], "status": row["status"],
            "versionCount": row["version_count"], "latestVersion": row["latest_version"],
            "publishedVersion": row["published_version"], "createdAt": row["created_at"],
            "updatedAt": row["updated_at"], "active": bool(active and active["templateId"] == row["id"]),
        } for row in rows]

    def create_template(self, item: dict[str, Any], template_file: str | None = None) -> dict[str, Any]:
        template_id, version_id, timestamp = uuid.uuid4().hex, uuid.uuid4().hex, now_iso()
        # 新模板必须从空的设计工作区开始，不能继承当前活动模板的映射。
        snapshot = {
            "mappings": [], "tableRules": [], "dataSources": [], "aiRules": [],
            "chapters": self.list_template_chapters(),
        }
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO admin_templates(id,code,name,description,status,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (template_id, item["code"], item["name"], item.get("description", ""), "ACTIVE", timestamp, timestamp),
            )
            connection.execute(
                """INSERT INTO admin_template_versions(id,template_id,version_no,status,note,snapshot,template_file,
                   validation_report,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (version_id, template_id, 1, "DRAFT", item.get("note", "初始版本"),
                 json.dumps(snapshot, ensure_ascii=False), template_file, "{}", timestamp, timestamp),
            )
        return next(value for value in self.list_templates() if value["id"] == template_id)

    def update_template(self, template_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"code": "code", "name": "name", "description": "description", "status": "status"}
        values = {column: item[key] for key, column in allowed.items() if key in item}
        if values:
            values["updated_at"] = now_iso()
            with self.database.connect() as connection:
                connection.execute(
                    f"UPDATE admin_templates SET {','.join(f'{key}=%s' for key in values)} WHERE id=%s",
                    (*values.values(), template_id),
                )
        return next((value for value in self.list_templates() if value["id"] == template_id), None)

    def delete_template(self, template_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            template = connection.execute("SELECT id,name FROM admin_templates WHERE id=%s", (template_id,)).fetchone()
            if not template:
                raise ValueError("模板不存在")
            if connection.execute("SELECT COUNT(*) FROM admin_templates").fetchone()[0] <= 1:
                raise ValueError("系统至少需要保留一个报告模板")
            version_ids = [row["id"] for row in connection.execute(
                "SELECT id FROM admin_template_versions WHERE template_id=%s", (template_id,),
            ).fetchall()]
        active = self.active_workspace()
        if active and active["templateId"] == template_id:
            with self.database.connect() as connection:
                fallback = connection.execute(
                    """SELECT t.id AS template_id,v.id AS version_id FROM admin_templates t
                       JOIN admin_template_versions v ON v.template_id=t.id WHERE t.id<>%s
                       ORDER BY t.updated_at DESC,v.version_no DESC LIMIT 1""", (template_id,),
                ).fetchone()
            if not fallback:
                raise ValueError("没有可切换的备用模板版本")
            self.activate_template_version(fallback["template_id"], fallback["version_id"])
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM admin_template_workspace WHERE active_template_id=%s OR active_version_id IN (SELECT id FROM admin_template_versions WHERE template_id=%s)",
                (template_id, template_id),
            )
            connection.execute(
                "DELETE FROM admin_template_versions WHERE template_id=%s", (template_id,)
            )
            connection.execute("DELETE FROM admin_templates WHERE id=%s", (template_id,))
        return {"id": template_id, "name": template["name"], "versionIds": version_ids}

    def list_template_versions(self, template_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_template_versions WHERE template_id=%s ORDER BY version_no DESC", (template_id,),
            ).fetchall()]
        return [self._catalog_version_to_api(row) for row in rows]

    def get_template_version(self, version_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM admin_template_versions WHERE id=%s", (version_id,)).fetchone()
        return self._catalog_version_to_api(dict(row)) if row else None

    def delete_template_version(self, template_id: str, version_id: str) -> dict[str, Any]:
        active = self.active_workspace()
        if active and active["versionId"] == version_id:
            raise ValueError("不能删除当前正在编辑的模板版本，请先切换到其他版本")
        with self.database.connect() as connection:
            version = connection.execute(
                "SELECT id,version_no,status FROM admin_template_versions WHERE id=%s AND template_id=%s",
                (version_id, template_id),
            ).fetchone()
            if not version:
                raise ValueError("模板版本不存在")
            if version["status"] == "PUBLISHED":
                raise ValueError("不能删除当前发布版本")
            version_count = connection.execute(
                "SELECT COUNT(*) FROM admin_template_versions WHERE template_id=%s", (template_id,),
            ).fetchone()[0]
            if version_count <= 1:
                raise ValueError("模板至少需要保留一个版本")
            connection.execute("DELETE FROM admin_template_versions WHERE id=%s", (version_id,))
        return {"id": version_id, "versionNo": version["version_no"]}

    def set_template_version_file(self, version_id: str, template_file: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE admin_template_versions SET template_file=%s,updated_at=%s WHERE id=%s",
                (template_file, now_iso(), version_id),
            )
        return cursor.rowcount > 0

    def create_template_version(
        self, template_id: str, base_version_id: str | None, note: str, template_file: str | None = None,
    ) -> dict[str, Any]:
        if base_version_id:
            with self.database.connect() as connection:
                base = connection.execute(
                    "SELECT snapshot,template_file FROM admin_template_versions WHERE id=%s AND template_id=%s",
                    (base_version_id, template_id),
                ).fetchone()
            if not base:
                raise ValueError("基础版本不存在")
            snapshot, source_file = json.loads(base["snapshot"]), base["template_file"]
        else:
            snapshot, source_file = self.snapshot(), None
        timestamp, version_id = now_iso(), uuid.uuid4().hex
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            version_no = connection.execute(
                "SELECT COALESCE(MAX(version_no),0)+1 FROM admin_template_versions WHERE template_id=%s", (template_id,),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO admin_template_versions(id,template_id,version_no,status,note,snapshot,template_file,
                   validation_report,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (version_id, template_id, version_no, "DRAFT", note or f"版本 {version_no}",
                 json.dumps(snapshot, ensure_ascii=False), template_file or source_file, "{}", timestamp, timestamp),
            )
            connection.execute("UPDATE admin_templates SET updated_at=%s WHERE id=%s", (timestamp, template_id))
        if base_version_id:
            self.ensure_template_block_table()
            with self.database.connect() as connection:
                connection.execute(
                    """INSERT INTO admin_template_version_blocks
                       (version_id,standard_group_code,chapter_id,title,kind,table_no,source_path,repeat_key,
                        prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,updated_at)
                       SELECT %s,standard_group_code,chapter_id,title,kind,table_no,source_path,repeat_key,
                        prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,%s
                       FROM admin_template_version_blocks WHERE version_id=%s""",
                    (version_id, timestamp, base_version_id),
                )
        return next(value for value in self.list_template_versions(template_id) if value["id"] == version_id)

    def activate_template_version(self, template_id: str, version_id: str) -> dict[str, Any]:
        active = self.active_workspace()
        if active and active["versionId"] != version_id:
            self.save_active_workspace()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM admin_template_versions WHERE id=%s AND template_id=%s", (version_id, template_id),
            ).fetchone()
        if not row:
            raise ValueError("模板版本不存在")
        if not active or active["versionId"] != version_id:
            self._restore_snapshot(json.loads(row["snapshot"]))
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO admin_template_workspace(id,active_template_id,active_version_id,updated_at) VALUES(1,%s,%s,%s) ON DUPLICATE KEY UPDATE active_template_id=VALUES(active_template_id),active_version_id=VALUES(active_version_id),updated_at=VALUES(updated_at)",
                (template_id, version_id, now_iso()),
            )
        return self.active_workspace() or {}

    def publish_active_template_version(
        self, snapshot: dict[str, Any], validation: dict[str, Any], compiled_template: str,
    ) -> dict[str, Any]:
        active = self.active_workspace()
        if not active:
            raise ValueError("没有活动模板版本")
        timestamp = now_iso()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE admin_template_versions SET status='ARCHIVED' WHERE template_id=%s AND status='PUBLISHED' AND id<>%s",
                (active["templateId"], active["versionId"]),
            )
            connection.execute(
                """UPDATE admin_template_versions SET status='PUBLISHED',snapshot=%s,validation_report=%s,
                   template_file=%s,updated_at=%s,published_at=%s WHERE id=%s""",
                (json.dumps(snapshot, ensure_ascii=False), json.dumps(validation, ensure_ascii=False),
                 compiled_template, timestamp, timestamp, active["versionId"]),
            )
            connection.execute("UPDATE admin_templates SET updated_at=%s WHERE id=%s", (timestamp, active["templateId"]))
            row = connection.execute("SELECT * FROM admin_template_versions WHERE id=%s", (active["versionId"],)).fetchone()
        return self._catalog_version_to_api(dict(row))
