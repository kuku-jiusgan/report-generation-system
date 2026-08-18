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
            "enabled": bool(row["enabled"]), "notes": row["notes"], "updatedAt": row["updated_at"],
        }

    def list_table_rules(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_table_rules ORDER BY CAST(SUBSTR(table_no,2) AS INTEGER)"
            ).fetchall()]
        return [self._table_to_api(row) for row in rows]

    def upsert_table_rule(self, item: dict[str, Any]) -> dict[str, Any]:
        values = (
            item["tableNo"], item.get("sectionCode", ""), item.get("mode", "ROW_REPEAT"),
            item.get("headerRows", 1), item.get("dataRowStart", 2), item.get("dataRowEnd", 2),
            item.get("footerRows", 0), item.get("recordKey", ""),
            json.dumps(item.get("mergeFields", []), ensure_ascii=False), int(item.get("enabled", True)),
            item.get("notes", ""), now_iso(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_table_rules(table_no,section_code,mode,header_rows,data_row_start,data_row_end,
                   footer_rows,record_key,merge_fields,enabled,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(table_no) DO UPDATE SET section_code=excluded.section_code,mode=excluded.mode,
                   header_rows=excluded.header_rows,data_row_start=excluded.data_row_start,data_row_end=excluded.data_row_end,
                   footer_rows=excluded.footer_rows,record_key=excluded.record_key,merge_fields=excluded.merge_fields,
                   enabled=excluded.enabled,notes=excluded.notes,updated_at=excluded.updated_at""", values,
            )
            row = connection.execute("SELECT * FROM admin_table_rules WHERE table_no=?", (item["tableNo"],)).fetchone()
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
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,
                   source_type=excluded.source_type,priority=excluded.priority,enabled=excluded.enabled,
                   config=excluded.config,updated_at=excluded.updated_at""", values,
            )
            row = connection.execute("SELECT * FROM admin_data_sources WHERE code=?", (item["code"],)).fetchone()
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
                   require_citations,requires_approval,provider,model,enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(field_code) DO UPDATE SET name=excluded.name,input_fields=excluded.input_fields,
                   prompt_template=excluded.prompt_template,output_type=excluded.output_type,max_length=excluded.max_length,
                   require_citations=excluded.require_citations,requires_approval=excluded.requires_approval,
                   provider=excluded.provider,model=excluded.model,enabled=excluded.enabled,updated_at=excluded.updated_at""", values,
            )
            row = connection.execute("SELECT * FROM admin_ai_rules WHERE field_code=?", (item["fieldCode"],)).fetchone()
        return self._ai_to_api(dict(row))

    def delete_ai_rule(self, rule_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_ai_rules WHERE id=?", (rule_id,))
        return cursor.rowcount > 0
