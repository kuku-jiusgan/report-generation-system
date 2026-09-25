import json
from typing import Any

from ..database import now_iso
from .docx_segment_table import validate_segment_layout


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
            text = json.dumps(layout, ensure_ascii=False)
            DesignerConfigRepositoryMixin._validate_matrix_layout(layout)
            if item.get("mode") == "TABLE_REPEAT" and item.get("innerMode") == "SEGMENT_REPEAT":
                validate_segment_layout(layout)
            return text
        text = str(layout or "").strip()
        if not text:
            if item.get("mode") == "TABLE_REPEAT" and item.get("innerMode") == "SEGMENT_REPEAT":
                raise ValueError("独立行片段必须配置布局 JSON")
            return ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"矩阵版式不是合法 JSON：{error}") from error
        if not isinstance(parsed, dict):
            raise ValueError("矩阵版式必须是 JSON 对象")
        DesignerConfigRepositoryMixin._validate_matrix_layout(parsed)
        if item.get("mode") == "TABLE_REPEAT" and item.get("innerMode") == "SEGMENT_REPEAT":
            validate_segment_layout(parsed)
        return text

    @staticmethod
    def _validate_matrix_layout(layout: dict[str, Any]) -> None:
        row_fields = layout.get("rowFields")
        if row_fields is not None:
            if not isinstance(row_fields, list):
                raise ValueError("矩阵版式的 rowFields 必须是数组")
            for entry in row_fields:
                try:
                    row = int(entry.get("row", 0) or 0) if isinstance(entry, dict) else 0
                except (TypeError, ValueError):
                    row = 0
                if not isinstance(entry, dict) or row < 1 or not str(entry.get("field") or "").strip():
                    raise ValueError("矩阵版式的 rowFields 必须包含正整数 row 和非空 field")
        fixed_rows = layout.get("fixedRowSpans")
        if fixed_rows is not None:
            if not isinstance(fixed_rows, dict):
                raise ValueError("矩阵固定行列宽配置必须是对象")
            for row, spans in fixed_rows.items():
                if (not str(row).isdigit() or int(row) < 1 or not isinstance(spans, list)
                        or not spans or any(type(span) is not int or span < 1 for span in spans)):
                    raise ValueError("矩阵固定行列宽配置必须按行号给出正整数跨度数组")
        policy = layout.get("columnPolicy")
        if policy is None:
            if fixed_rows:
                raise ValueError("矩阵固定行列宽配置需要启用横向扩展")
            return
        if not isinstance(row_fields, list) or not row_fields:
            raise ValueError("启用矩阵横向扩展时，rowFields 不能为空")
        if not isinstance(policy, dict):
            raise ValueError("矩阵横向扩展的 columnPolicy 必须是 JSON 对象")
        if str(policy.get("mode") or "DATA_LENGTH") != "DATA_LENGTH":
            raise ValueError("矩阵横向扩展的 mode 只能是 DATA_LENGTH")
        if str(policy.get("overflow") or "") != "HORIZONTAL":
            raise ValueError("矩阵横向扩展的 overflow 只能是 HORIZONTAL")
        try:
            minimum = int(policy.get("minColumns", 1))
        except (TypeError, ValueError) as error:
            raise ValueError("矩阵横向扩展的 minColumns 必须是正整数") from error
        if minimum < 1 or minimum > 1000:
            raise ValueError("矩阵横向扩展的 minColumns 必须在 1 到 1000 之间")
        width_mode = str(policy.get("widthMode") or "PROTOTYPE")
        if width_mode not in {"PROTOTYPE", "PRESERVE_TOTAL"}:
            raise ValueError("矩阵横向扩展的 widthMode 只能是 PROTOTYPE 或 PRESERVE_TOTAL")

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
