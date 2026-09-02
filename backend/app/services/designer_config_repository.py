import json
from typing import Any

from ..database import now_iso


class DesignerConfigRepositoryMixin:
    """Persistence for table, data-source and AI designer configuration."""

    @staticmethod
    def _table_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "tableNo": row["table_no"], "sectionCode": row["section_code"], "mode": row["mode"],
            "headerRows": row["header_rows"], "dataRowStart": row["data_row_start"],
            "dataRowEnd": row["data_row_end"], "footerRows": row["footer_rows"],
            "recordKey": row["record_key"], "mergeFields": json.loads(row["merge_fields"]),
            "physicalTableIndex": row["physical_table_index"],
            "preservedRowLabels": json.loads(row["preserved_row_labels"] or "[]"),
            "clearEmbeddedObjects": bool(row["clear_embedded_objects"]),
            "matrixLayout": row["matrix_layout"] or "",
            "groupKey": row["group_key"] or "",
            "innerMode": row["inner_mode"] or "ROW_REPEAT",
            "enabled": bool(row["enabled"]), "notes": row["notes"], "updatedAt": row["updated_at"],
        }

    def list_table_rules(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_table_rules ORDER BY CAST(SUBSTRING(table_no,2) AS SIGNED)"
            ).fetchall()]
        return [self._table_to_api(row) for row in rows]

    @staticmethod
    def _matrix_layout_text(item: dict[str, Any]) -> str:
        """矩阵版式以 JSON 文本保存；格式错误必须在保存时就说清楚，不能留到生成时。"""
        layout = item.get("matrixLayout", "")
        if isinstance(layout, dict):
            return json.dumps(layout, ensure_ascii=False)
        text = str(layout or "").strip()
        if not text:
            return ""
        try:
            json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"矩阵版式不是合法 JSON：{error}") from error
        return text

    def upsert_table_rule(self, item: dict[str, Any]) -> dict[str, Any]:
        values = (
            item["tableNo"], item.get("sectionCode", ""), item.get("mode", "ROW_REPEAT"),
            item.get("headerRows", 1), item.get("dataRowStart", 2), item.get("dataRowEnd", 2),
            item.get("footerRows", 0), item.get("recordKey", ""),
            json.dumps(item.get("mergeFields", []), ensure_ascii=False),
            int(item.get("physicalTableIndex", 0) or 0),
            json.dumps(item.get("preservedRowLabels", []), ensure_ascii=False),
            int(bool(item.get("clearEmbeddedObjects", False))),
            self._matrix_layout_text(item), int(item.get("enabled", True)),
            item.get("notes", ""), item.get("groupKey", ""), item.get("innerMode", "ROW_REPEAT"), now_iso(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_table_rules(table_no,section_code,mode,header_rows,data_row_start,data_row_end,
                   footer_rows,record_key,merge_fields,physical_table_index,preserved_row_labels,
                   clear_embedded_objects,matrix_layout,enabled,notes,group_key,inner_mode,updated_at)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE section_code=VALUES(section_code),mode=VALUES(mode),
                   header_rows=VALUES(header_rows),data_row_start=VALUES(data_row_start),data_row_end=VALUES(data_row_end),
                   footer_rows=VALUES(footer_rows),record_key=VALUES(record_key),merge_fields=VALUES(merge_fields),
                   physical_table_index=VALUES(physical_table_index),preserved_row_labels=VALUES(preserved_row_labels),
                   clear_embedded_objects=VALUES(clear_embedded_objects),matrix_layout=VALUES(matrix_layout),
                   enabled=VALUES(enabled),notes=VALUES(notes),group_key=VALUES(group_key),inner_mode=VALUES(inner_mode),updated_at=VALUES(updated_at)""", values,
            )
            row = connection.execute("SELECT * FROM admin_table_rules WHERE table_no=%s", (item["tableNo"],)).fetchone()
        return self._table_to_api(dict(row))

    @staticmethod
    def _data_source_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"], "code": row["code"], "name": row["name"], "sourceType": row["source_type"],
            "priority": row["priority"], "enabled": bool(row["enabled"]), "config": json.loads(row["config"]),
            "updatedAt": row["updated_at"],
        }

    def list_data_sources(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_data_sources ORDER BY priority"
            ).fetchall()]
        return [self._data_source_to_api(row) for row in rows]

    def upsert_data_source(self, item: dict[str, Any]) -> dict[str, Any]:
        values = (
            item["code"], item["name"], item["sourceType"], item.get("priority", 100),
            int(item.get("enabled", True)), json.dumps(item.get("config", {}), ensure_ascii=False), now_iso(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_data_sources(code,name,source_type,priority,enabled,config,updated_at)
                   VALUES(%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name),
                   source_type=VALUES(source_type),priority=VALUES(priority),enabled=VALUES(enabled),
                   config=VALUES(config),updated_at=VALUES(updated_at)""", values,
            )
            row = connection.execute("SELECT * FROM admin_data_sources WHERE code=%s", (item["code"],)).fetchone()
        return self._data_source_to_api(dict(row))

    @staticmethod
    def _ai_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"], "fieldCode": row["field_code"], "name": row["name"],
            "inputFields": json.loads(row["input_fields"]), "promptTemplate": row["prompt_template"],
            "outputType": row["output_type"], "maxLength": row["max_length"],
            "requireCitations": bool(row["require_citations"]),
            "requiresApproval": bool(row["requires_approval"]), "provider": row["provider"],
            "model": row["model"], "enabled": bool(row["enabled"]), "updatedAt": row["updated_at"],
        }

    def list_ai_rules(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_ai_rules ORDER BY field_code"
            ).fetchall()]
        return [self._ai_to_api(row) for row in rows]

    def upsert_ai_rule(self, item: dict[str, Any]) -> dict[str, Any]:
        values = (
            item["fieldCode"], item["name"], json.dumps(item.get("inputFields", []), ensure_ascii=False),
            item.get("promptTemplate", ""), item.get("outputType", "richText"), item.get("maxLength", 500),
            int(item.get("requireCitations", True)), int(item.get("requiresApproval", True)),
            item.get("provider", "unconfigured"), item.get("model", ""), int(item.get("enabled", True)), now_iso(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_ai_rules(field_code,name,input_fields,prompt_template,output_type,max_length,
                   require_citations,requires_approval,provider,model,enabled,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE name=VALUES(name),input_fields=VALUES(input_fields),
                   prompt_template=VALUES(prompt_template),output_type=VALUES(output_type),max_length=VALUES(max_length),
                   require_citations=VALUES(require_citations),requires_approval=VALUES(requires_approval),
                   provider=VALUES(provider),model=VALUES(model),enabled=VALUES(enabled),updated_at=VALUES(updated_at)""", values,
            )
            row = connection.execute("SELECT * FROM admin_ai_rules WHERE field_code=%s", (item["fieldCode"],)).fetchone()
        return self._ai_to_api(dict(row))

    def delete_ai_rule(self, rule_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_ai_rules WHERE id=%s", (rule_id,))
        return cursor.rowcount > 0
