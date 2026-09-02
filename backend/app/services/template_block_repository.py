from typing import Any

from ..database import now_iso


class TemplateBlockRepositoryMixin:
    """Template-version-owned layout references for standard field groups."""

    def ensure_template_block_table(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS admin_template_version_blocks (
                  version_id VARCHAR(64) NOT NULL,
                  standard_group_code VARCHAR(255) NOT NULL,
                  chapter_id INTEGER NOT NULL,
                  title VARCHAR(255) NOT NULL DEFAULT '',
                  kind VARCHAR(64) NOT NULL DEFAULT 'MAPPED_FIELD',
                  table_no VARCHAR(64) NOT NULL DEFAULT '',
                  source_path VARCHAR(1000) NOT NULL DEFAULT '',
                  repeat_key VARCHAR(255) NOT NULL DEFAULT '',
                  prototype_location VARCHAR(255) NOT NULL DEFAULT '',
                  dedup_key VARCHAR(255) NOT NULL DEFAULT '',
                  sort_rule VARCHAR(1000) NOT NULL DEFAULT '',
                  empty_behavior VARCHAR(64) NOT NULL DEFAULT 'KEEP',
                  merge_rule VARCHAR(64) NOT NULL DEFAULT 'NONE',
                  order_no INTEGER NOT NULL DEFAULT 0,
                  enabled INTEGER NOT NULL DEFAULT 1,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY(version_id, standard_group_code),
                  FOREIGN KEY(version_id) REFERENCES admin_template_versions(id) ON DELETE CASCADE
                ) ENGINE=InnoDB"""
            )

    def list_template_blocks(self, version_id: str) -> list[dict[str, Any]]:
        self.ensure_template_block_table()
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_template_version_blocks WHERE version_id=%s ORDER BY order_no,standard_group_code",
                (version_id,),
            ).fetchall()]
        return [{
            "versionId": row["version_id"], "standardGroupCode": row["standard_group_code"],
            "chapterId": row["chapter_id"], "title": row["title"], "kind": row["kind"],
            "tableNo": row["table_no"], "sourcePath": row["source_path"], "repeatKey": row["repeat_key"],
            "prototypeLocation": row["prototype_location"], "dedupKey": row["dedup_key"],
            "sortRule": row["sort_rule"], "emptyBehavior": row["empty_behavior"],
            "mergeRule": row["merge_rule"], "orderNo": row["order_no"],
            "enabled": bool(row["enabled"]), "updatedAt": row["updated_at"],
        } for row in rows]

    def save_template_block(self, version_id: str, item: dict[str, Any]) -> dict[str, Any]:
        self.ensure_template_block_table()
        group_code = str(item.get("standardGroupCode") or "").strip()
        if not group_code:
            raise ValueError("标准编组编码不能为空")
        fields = {
            "chapter_id": int(item["chapterId"]), "title": str(item.get("title") or ""),
            "kind": str(item.get("kind") or "MAPPED_FIELD"), "table_no": str(item.get("tableNo") or ""),
            "source_path": str(item.get("sourcePath") or ""), "repeat_key": str(item.get("repeatKey") or ""),
            "prototype_location": str(item.get("prototypeLocation") or ""), "dedup_key": str(item.get("dedupKey") or ""),
            "sort_rule": str(item.get("sortRule") or ""), "empty_behavior": str(item.get("emptyBehavior") or "KEEP"),
            "merge_rule": str(item.get("mergeRule") or "NONE"), "order_no": int(item.get("orderNo", 0) or 0),
            "enabled": int(bool(item.get("enabled", True))),
        }
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_template_version_blocks
                   (version_id,standard_group_code,chapter_id,title,kind,table_no,source_path,repeat_key,
                    prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,updated_at)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE chapter_id=VALUES(chapter_id),title=VALUES(title),kind=VALUES(kind),
                   table_no=VALUES(table_no),source_path=VALUES(source_path),repeat_key=VALUES(repeat_key),
                   prototype_location=VALUES(prototype_location),dedup_key=VALUES(dedup_key),sort_rule=VALUES(sort_rule),
                   empty_behavior=VALUES(empty_behavior),merge_rule=VALUES(merge_rule),order_no=VALUES(order_no),
                   enabled=VALUES(enabled),updated_at=VALUES(updated_at)""",
                (version_id, group_code, *fields.values(), now_iso()),
            )
        return next(row for row in self.list_template_blocks(version_id) if row["standardGroupCode"] == group_code)
