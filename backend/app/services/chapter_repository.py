from collections import defaultdict
from typing import Any

from ..database import now_iso
from .report_fields import report_binding_code
from .system_field_groups import ensure_system_field_groups, list_system_field_groups


def _chapter_tree(chapters: list[dict[str, Any]], fields: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    nodes = {
        item["id"]: {**item, "fields": fields.get(item["id"], []), "children": []}
        for item in chapters
    }
    roots: list[dict[str, Any]] = []
    for node in nodes.values():
        parent_id = node.get("parentId")
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)
    for node in nodes.values():
        node["children"].sort(key=lambda item: (item.get("orderNo", 0), item["id"]))
    roots.sort(key=lambda item: (item.get("orderNo", 0), item["id"]))
    return roots


class ChapterRepositoryMixin:
    """Template chapter persistence and chapter-based field catalogs."""

    @staticmethod
    def _chapter_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"], "parentId": row["parent_id"], "code": row["code"], "title": row["title"],
            "pageHint": row["page_hint"], "orderNo": row["order_no"], "enabled": bool(row["enabled"]),
            "updatedAt": row["updated_at"],
        }

    def list_template_chapters(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_template_chapters ORDER BY order_no,id"
            ).fetchall()]
        return [self._chapter_to_api(row) for row in rows]

    def report_source_catalog(self) -> dict[str, Any]:
        fields: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for mapping in self.list_mappings():
            chapter_id = mapping.get("chapterId")
            if not chapter_id or not mapping.get("enabled", True):
                continue
            fields[int(chapter_id)].append({
                "id": mapping["id"], "wordLabel": mapping["wordLabel"],
                "fieldCode": mapping["fieldCode"], "bindingCode": report_binding_code(mapping["fieldCode"]),
                "sourceType": mapping["sourceType"], "sourcePath": mapping.get("sourcePath", ""),
                "repeatType": mapping.get("repeatType", "NONE"), "tableNo": mapping.get("tableNo", ""),
                "controlTag": mapping.get("controlTag", ""), "orderNo": mapping["id"],
            })
        chapters = [item for item in self.list_template_chapters() if item.get("enabled", True)]
        return {"chapters": _chapter_tree(chapters, fields)}

    def standard_field_catalog(self, include_disabled: bool = True) -> dict[str, Any]:
        ensure_system_field_groups(self.database)
        fields = self.database.list_lims_fields(include_disabled)
        fields_by_code = {item["fieldCode"]: item for item in fields}
        chapter_fields, mapped_codes = self._standard_fields_by_chapter(fields_by_code)
        with self.database.connect() as connection:
            grouped_codes = connection.execute(
                """SELECT DISTINCT gf.field_code FROM system_field_group_fields gf
                   JOIN system_field_group_chapters gc ON gc.group_code=gf.group_code"""
            ).fetchall()
        mapped_codes.update(str(row["field_code"]) for row in grouped_codes)
        return {
            "chapters": _chapter_tree(self.list_template_chapters(), chapter_fields),
            "groups": list_system_field_groups(self.database),
            "fields": fields,
            "unmappedFields": [item for item in fields if item["fieldCode"] not in mapped_codes],
            "total": len(fields),
        }

    def _standard_fields_by_chapter(
        self, fields_by_code: dict[str, dict[str, Any]],
    ) -> tuple[dict[int, list[dict[str, Any]]], set[str]]:
        with self.database.connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS system_field_chapters (
                   field_code TEXT NOT NULL,chapter_id INTEGER NOT NULL,order_no INTEGER NOT NULL DEFAULT 0,
                   PRIMARY KEY(field_code,chapter_id),
                   FOREIGN KEY(field_code) REFERENCES lims_field_catalog(field_code)
                       ON UPDATE CASCADE ON DELETE CASCADE,
                   FOREIGN KEY(chapter_id) REFERENCES admin_template_chapters(id) ON DELETE CASCADE)"""
            )
            links = connection.execute(
                """SELECT DISTINCT mc.chapter_id,m.standard_field_code FROM admin_mapping_chapters mc
                   JOIN admin_mapping_rules m ON m.id=mc.mapping_id
                   WHERE COALESCE(m.standard_field_code,'')<>''
                   UNION SELECT chapter_id,field_code FROM system_field_chapters
                   ORDER BY chapter_id"""
            ).fetchall()
        codes: dict[int, set[str]] = defaultdict(set)
        mapped: set[str] = set()
        for link in links:
            code = str(link["standard_field_code"])
            if code in fields_by_code:
                codes[int(link["chapter_id"])].add(code)
                mapped.add(code)
        result = {
            chapter_id: sorted(
                (fields_by_code[code] for code in chapter_codes),
                key=lambda item: (item.get("orderNo", 0), item.get("id", 0)),
            )
            for chapter_id, chapter_codes in codes.items()
        }
        return result, mapped

    def create_template_chapter(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO admin_template_chapters(parent_id,code,title,page_hint,order_no,enabled,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (item.get("parentId"), item["code"], item["title"], item.get("pageHint"),
                 item.get("orderNo", 999), int(item.get("enabled", True)), now_iso()),
            )
            row = connection.execute(
                "SELECT * FROM admin_template_chapters WHERE id=?", (cursor.lastrowid,),
            ).fetchone()
        return self._chapter_to_api(dict(row))

    def update_template_chapter(self, chapter_id: int, item: dict[str, Any]) -> dict[str, Any] | None:
        columns = {"parentId": "parent_id", "code": "code", "title": "title", "pageHint": "page_hint",
                   "orderNo": "order_no", "enabled": "enabled"}
        values = {column: int(item[key]) if key == "enabled" else item[key]
                  for key, column in columns.items() if key in item}
        if not values:
            return next((value for value in self.list_template_chapters() if value["id"] == chapter_id), None)
        values["updated_at"] = now_iso()
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE admin_template_chapters SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                (*values.values(), chapter_id),
            )
            row = connection.execute("SELECT * FROM admin_template_chapters WHERE id=?", (chapter_id,)).fetchone()
        return self._chapter_to_api(dict(row)) if row else None

    def delete_template_chapter(self, chapter_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_template_chapters WHERE id=?", (chapter_id,))
        return cursor.rowcount > 0
