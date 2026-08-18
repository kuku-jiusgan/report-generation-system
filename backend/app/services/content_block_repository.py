from collections import defaultdict
from typing import Any

from ..database import now_iso


class ContentBlockRepositoryMixin:
    """Persistence operations for designer content blocks and their field order."""

    @staticmethod
    def _content_block_to_api(row: dict[str, Any], mapping_ids: list[int] | None = None) -> dict[str, Any]:
        return {
            "id": row["id"], "chapterId": row["chapter_id"], "title": row["title"],
            "kind": row["kind"], "tableNo": row["table_no"], "orderNo": row["order_no"],
            "sourcePath": row.get("source_path", ""), "repeatKey": row.get("repeat_key", ""),
            "prototypeLocation": row.get("prototype_location", ""), "dedupKey": row.get("dedup_key", ""),
            "sortRule": row.get("sort_rule", ""), "emptyBehavior": row.get("empty_behavior", "KEEP"),
            "mergeRule": row.get("merge_rule", "NONE"), "enabled": bool(row["enabled"]),
            "mappingIds": mapping_ids or [], "updatedAt": row["updated_at"],
        }

    def list_content_blocks(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_content_blocks ORDER BY chapter_id,order_no,id"
            ).fetchall()]
            mapping_rows = connection.execute(
                "SELECT block_id,mapping_id FROM admin_mapping_blocks ORDER BY block_id,order_no,mapping_id"
            ).fetchall()
        mapping_ids: dict[int, list[int]] = defaultdict(list)
        for item in mapping_rows:
            mapping_ids[int(item["block_id"])].append(int(item["mapping_id"]))
        return [self._content_block_to_api(row, mapping_ids.get(int(row["id"]), [])) for row in rows]

    def reorder_content_blocks(self, chapter_id: int, block_ids: list[int]) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            existing = [int(row["id"]) for row in connection.execute(
                "SELECT id FROM admin_content_blocks WHERE chapter_id=? ORDER BY order_no,id", (chapter_id,),
            ).fetchall()]
            if len(block_ids) != len(existing) or set(block_ids) != set(existing):
                raise ValueError("内容块顺序与当前章节不一致，请刷新后重试")
            connection.executemany(
                "UPDATE admin_content_blocks SET order_no=?,updated_at=? WHERE id=?",
                [(order_no, now_iso(), block_id) for order_no, block_id in enumerate(block_ids)],
            )
        return [item for item in self.list_content_blocks() if item["chapterId"] == chapter_id]

    def reorder_block_mappings(self, block_id: int, mapping_ids: list[int]) -> list[int]:
        with self.database.connect() as connection:
            existing = [int(row["mapping_id"]) for row in connection.execute(
                "SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=? ORDER BY order_no,mapping_id", (block_id,),
            ).fetchall()]
            if len(mapping_ids) != len(existing) or set(mapping_ids) != set(existing):
                raise ValueError("字段顺序与当前内容块不一致，请刷新后重试")
            connection.executemany(
                "UPDATE admin_mapping_blocks SET order_no=? WHERE mapping_id=? AND block_id=?",
                [(order_no, mapping_id, block_id) for order_no, mapping_id in enumerate(mapping_ids)],
            )
        return mapping_ids

    def create_content_block(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.database.connect() as connection:
            order_no = item.get("orderNo")
            if order_no is None:
                order_no = connection.execute(
                    "SELECT COALESCE(MAX(order_no),-1)+1 FROM admin_content_blocks WHERE chapter_id=?",
                    (item["chapterId"],),
                ).fetchone()[0]
            cursor = connection.execute(
                """INSERT INTO admin_content_blocks(chapter_id,title,kind,table_no,source_path,repeat_key,
                   prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["chapterId"], item["title"], item.get("kind", "MAPPED_FIELD"), item.get("tableNo", ""),
                 item.get("sourcePath", ""), item.get("repeatKey", ""), item.get("prototypeLocation", ""),
                 item.get("dedupKey", ""), item.get("sortRule", ""), item.get("emptyBehavior", "KEEP"),
                 item.get("mergeRule", "NONE"), order_no, int(item.get("enabled", True)), now_iso()),
            )
        return next(value for value in self.list_content_blocks() if value["id"] == cursor.lastrowid)

    def update_content_block(self, block_id: int, item: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "chapterId": "chapter_id", "title": "title", "kind": "kind", "tableNo": "table_no",
            "sourcePath": "source_path", "repeatKey": "repeat_key", "prototypeLocation": "prototype_location",
            "dedupKey": "dedup_key", "sortRule": "sort_rule", "emptyBehavior": "empty_behavior",
            "mergeRule": "merge_rule", "orderNo": "order_no", "enabled": "enabled",
        }
        values = {column: int(item[key]) if key == "enabled" else item[key]
                  for key, column in allowed.items() if key in item}
        values["updated_at"] = now_iso()
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE admin_content_blocks SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                (*values.values(), block_id),
            )
            row = connection.execute("SELECT kind FROM admin_content_blocks WHERE id=?", (block_id,)).fetchone()
            if not row:
                return None
            kind = item.get("kind") or row[0]
            if kind in {"REPEATING_TABLE", "MATRIX"}:
                connection.execute(
                    """UPDATE admin_mapping_rules SET table_no=?,repeat_type='ROW',repeat_key=?,updated_at=?
                       WHERE id IN (SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=?)""",
                    (item.get("tableNo", ""), item.get("repeatKey", ""), now_iso(), block_id),
                )
            elif "kind" in item:
                connection.execute(
                    """UPDATE admin_mapping_rules SET repeat_type='NONE',repeat_key='',updated_at=?
                       WHERE id IN (SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=?)""",
                    (now_iso(), block_id),
                )
        return next((value for value in self.list_content_blocks() if value["id"] == block_id), None)

    def delete_content_block(self, block_id: int, delete_mappings: bool = True) -> bool:
        with self.database.connect() as connection:
            row = connection.execute("SELECT id FROM admin_content_blocks WHERE id=?", (block_id,)).fetchone()
            if not row:
                return False
            if delete_mappings:
                connection.execute(
                    "DELETE FROM admin_mapping_rules WHERE id IN (SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=?)",
                    (block_id,),
                )
            connection.execute("DELETE FROM admin_content_blocks WHERE id=?", (block_id,))
        return True
