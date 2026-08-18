import json
from typing import Any

from ..database import now_iso


MAPPING_COLUMNS = {
    "locationId": "location_id", "sectionCode": "section_code", "tableNo": "table_no",
    "wordLabel": "word_label", "fieldCode": "field_code", "dataType": "data_type",
    "sourceType": "source_type", "sourcePath": "source_path", "standardFieldCode": "standard_field_code",
    "repeatType": "repeat_type", "repeatKey": "repeat_key", "mergeRule": "merge_rule",
    "fillRule": "fill_rule", "calculationRule": "calculation_rule",
    "calculationExpression": "calculation_expression", "calculationDependencies": "calculation_dependencies",
    "calculationScope": "calculation_scope", "calculationPrecision": "calculation_precision",
    "calculationNullBehavior": "calculation_null_behavior", "controlTag": "control_tag",
    "required": "required", "sourcePending": "source_pending", "enabled": "enabled",
}
REVERSE_MAPPING_COLUMNS = {value: key for key, value in MAPPING_COLUMNS.items()}


class MappingRepositoryMixin:
    """Persistence and relationship management for template field mappings."""

    @staticmethod
    def _mapping_to_api(row: dict[str, Any]) -> dict[str, Any]:
        item = {REVERSE_MAPPING_COLUMNS.get(key, key): value
                for key, value in row.items() if key != "updated_at"}
        for key in ("required", "sourcePending", "enabled"):
            if key in item:
                item[key] = bool(item[key])
        item["updatedAt"] = row.get("updated_at")
        dependencies = item.get("calculationDependencies", "[]")
        if isinstance(dependencies, str):
            try:
                item["calculationDependencies"] = json.loads(dependencies)
            except json.JSONDecodeError:
                item["calculationDependencies"] = []
        if "assigned_chapter_id" in row:
            item["chapterId"] = row.get("assigned_chapter_id")
        if "assigned_block_id" in row:
            item["blockId"] = row.get("assigned_block_id")
        return item

    def list_mappings(self, search: str = "", table_no: str = "", source_type: str = "") -> list[dict[str, Any]]:
        clauses, params = [], []
        for value, clause in ((table_no, "m.table_no=?"), (source_type, "m.source_type=?")):
            if value:
                clauses.append(clause)
                params.append(value)
        if search:
            clauses.insert(0, "(m.field_code LIKE ? OR m.word_label LIKE ? OR m.location_id LIKE ?)")
            params[0:0] = [f"%{search}%"] * 3
        sql = """SELECT m.*,mc.chapter_id AS assigned_chapter_id,mb.block_id AS assigned_block_id
                 FROM admin_mapping_rules m LEFT JOIN admin_mapping_chapters mc ON mc.mapping_id=m.id
                 LEFT JOIN admin_mapping_blocks mb ON mb.mapping_id=m.id"""
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY CASE WHEN m.table_no='HEADER' THEN 0 ELSE CAST(SUBSTR(m.table_no,2) AS INTEGER) END,m.id"
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(sql, params).fetchall()]
        return [self._mapping_to_api(row) for row in rows]

    @staticmethod
    def _mapping_values(item: dict[str, Any], partial: bool) -> dict[str, Any]:
        values = {db: item[api] for api, db in MAPPING_COLUMNS.items() if api in item} if partial else {
            db: item.get(api, False if api in {"required", "sourcePending", "enabled"} else "")
            for api, db in MAPPING_COLUMNS.items()
        }
        if "calculationDependencies" in item or not partial:
            values["calculation_dependencies"] = json.dumps(item.get("calculationDependencies", []), ensure_ascii=False)
        if not partial:
            values.update({
                "calculation_scope": item.get("calculationScope", "REPORT"),
                "calculation_precision": int(item.get("calculationPrecision", 2)),
                "calculation_null_behavior": item.get("calculationNullBehavior", "ERROR"),
                "enabled": item.get("enabled", True),
            })
        values["updated_at"] = now_iso()
        return values

    def create_mapping(self, item: dict[str, Any]) -> dict[str, Any]:
        item = self.ensure_mapping_identifiers(item)
        self.validate_calculation_mapping(item)
        if item.get("sourceType") == "CALCULATED" and item.get("calculationExpression"):
            item["sourcePath"] = ""
        values = self._mapping_values(item, partial=False)
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO admin_mapping_rules({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
            row = connection.execute("SELECT * FROM admin_mapping_rules WHERE id=?", (cursor.lastrowid,)).fetchone()
        self._create_mapping_relations(cursor.lastrowid, item)
        return next((value for value in self.list_mappings() if value["id"] == cursor.lastrowid),
                    self._mapping_to_api(dict(row)))

    def _create_mapping_relations(self, mapping_id: int, item: dict[str, Any]) -> None:
        if item.get("chapterId"):
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(?,?)",
                    (mapping_id, item["chapterId"]),
                )
        block_id = item.get("blockId")
        if not block_id and item.get("chapterId"):
            block_id = self.create_content_block({
                "chapterId": item["chapterId"], "title": item.get("wordLabel") or "字段组",
                "kind": "MAPPED_FIELD", "tableNo": "", "enabled": True,
            })["id"]
        if block_id:
            self._assign_mapping_block(mapping_id, block_id)

    def _assign_mapping_block(self, mapping_id: int, block_id: int) -> None:
        with self.database.connect() as connection:
            current = connection.execute(
                "SELECT block_id FROM admin_mapping_blocks WHERE mapping_id=?", (mapping_id,),
            ).fetchone()
            if current and int(current["block_id"]) == int(block_id):
                return
            order_no = connection.execute(
                "SELECT COALESCE(MAX(order_no),-1)+1 FROM admin_mapping_blocks WHERE block_id=?", (block_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT OR REPLACE INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(?,?,?)",
                (mapping_id, block_id, order_no),
            )

    def update_mapping(self, rule_id: int, item: dict[str, Any]) -> dict[str, Any] | None:
        item = self.ensure_mapping_identifiers(item, rule_id)
        self.validate_calculation_mapping(item, rule_id)
        if item.get("sourceType") == "CALCULATED" and item.get("calculationExpression"):
            item["sourcePath"] = ""
        values = self._mapping_values(item, partial=True)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE admin_mapping_rules SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                (*values.values(), rule_id),
            )
            row = connection.execute("SELECT * FROM admin_mapping_rules WHERE id=?", (rule_id,)).fetchone()
            self._update_chapter_relation(connection, rule_id, item)
            if "blockId" in item and not item.get("blockId"):
                connection.execute("DELETE FROM admin_mapping_blocks WHERE mapping_id=?", (rule_id,))
        if item.get("blockId"):
            self._assign_mapping_block(rule_id, item["blockId"])
        return next((value for value in self.list_mappings() if value["id"] == rule_id),
                    self._mapping_to_api(dict(row))) if row else None

    @staticmethod
    def _update_chapter_relation(connection: Any, rule_id: int, item: dict[str, Any]) -> None:
        if "chapterId" not in item:
            return
        if item.get("chapterId"):
            connection.execute(
                "INSERT OR REPLACE INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(?,?)",
                (rule_id, item["chapterId"]),
            )
        else:
            connection.execute("DELETE FROM admin_mapping_chapters WHERE mapping_id=?", (rule_id,))

    def delete_mapping(self, rule_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_mapping_rules WHERE id=?", (rule_id,))
        return cursor.rowcount > 0
