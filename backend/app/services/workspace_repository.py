import json
from typing import Any

from ..database import now_iso
from .mapping_repository import MAPPING_COLUMNS


class WorkspaceRepositoryMixin:
    """Active designer workspace snapshots and restoration."""

    def snapshot(self) -> dict[str, Any]:
        return {
            "mappings": self.list_mappings(), "tableRules": self.list_table_rules(),
            "dataSources": self.list_data_sources(), "aiRules": self.list_ai_rules(),
            "chapters": self.list_template_chapters(), "contentBlocks": self.list_content_blocks(),
        }

    def active_workspace(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT w.active_template_id,w.active_version_id,t.name AS template_name,
                   v.version_no,v.status AS version_status,v.template_file FROM admin_template_workspace w
                   JOIN admin_templates t ON t.id=w.active_template_id
                   JOIN admin_template_versions v ON v.id=w.active_version_id WHERE w.id=1"""
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        return {
            "templateId": item["active_template_id"], "versionId": item["active_version_id"],
            "templateName": item["template_name"], "versionNo": item["version_no"],
            "versionStatus": item["version_status"], "templateFile": item["template_file"],
        }

    def save_active_workspace(self, template_file: str | None = None) -> None:
        active = self.active_workspace()
        if not active:
            return
        values: list[Any] = [json.dumps(self.snapshot(), ensure_ascii=False)]
        assignment = "snapshot=?"
        if template_file is not None:
            assignment += ",template_file=?"
            values.append(template_file)
        values.extend([now_iso(), active["versionId"]])
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE admin_template_versions SET {assignment},updated_at=? WHERE id=?", values,
            )

    def _restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        chapters = snapshot.get("chapters") or self.list_template_chapters()
        with self.database.connect() as connection:
            self._clear_workspace(connection)
            self._restore_chapters(connection, chapters)
            self._restore_mappings(connection, snapshot.get("mappings", []))
            self._restore_content_blocks(connection, snapshot.get("contentBlocks", []))
            self._restore_table_rules(connection, snapshot.get("tableRules", []))
            self._restore_ai_rules(connection, snapshot.get("aiRules", []))
        if not snapshot.get("contentBlocks"):
            self._seed_content_blocks()

    @staticmethod
    def _clear_workspace(connection: Any) -> None:
        for table in (
            "admin_mapping_blocks", "admin_content_blocks", "admin_mapping_chapters",
            "admin_mapping_rules", "admin_template_chapters", "admin_table_rules", "admin_ai_rules",
        ):
            connection.execute(f"DELETE FROM {table}")

    @staticmethod
    def _restore_chapters(connection: Any, chapters: list[dict[str, Any]]) -> None:
        for item in sorted(chapters, key=lambda value: (value.get("orderNo", 0), value.get("id", 0))):
            connection.execute(
                """INSERT INTO admin_template_chapters(id,parent_id,code,title,page_hint,order_no,enabled,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (item["id"], item.get("parentId"), item["code"], item["title"], item.get("pageHint"),
                 item.get("orderNo", 0), int(item.get("enabled", True)), now_iso()),
            )

    @staticmethod
    def _mapping_restore_values(item: dict[str, Any]) -> list[Any]:
        values = [item.get(api, False if api in {"required", "sourcePending"}
                           else True if api == "enabled" else "") for api in MAPPING_COLUMNS]
        indexes = {key: list(MAPPING_COLUMNS).index(key) for key in (
            "calculationDependencies", "calculationScope", "calculationPrecision", "calculationNullBehavior",
        )}
        values[indexes["calculationDependencies"]] = json.dumps(
            item.get("calculationDependencies", []), ensure_ascii=False,
        )
        values[indexes["calculationScope"]] = item.get("calculationScope", "REPORT") or "REPORT"
        values[indexes["calculationPrecision"]] = int(item.get("calculationPrecision", 2) or 2)
        values[indexes["calculationNullBehavior"]] = item.get("calculationNullBehavior", "ERROR") or "ERROR"
        return values

    def _restore_mappings(self, connection: Any, mappings: list[dict[str, Any]]) -> None:
        for item in mappings:
            values = self._mapping_restore_values(item)
            connection.execute(
                f"INSERT INTO admin_mapping_rules(id,{','.join(MAPPING_COLUMNS.values())},updated_at) "
                f"VALUES({','.join('?' for _ in range(len(values) + 2))})",
                (item["id"], *values, now_iso()),
            )
            if item.get("chapterId"):
                connection.execute(
                    "INSERT INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(?,?)",
                    (item["id"], item["chapterId"]),
                )

    @staticmethod
    def _restore_content_blocks(connection: Any, blocks: list[dict[str, Any]]) -> None:
        for item in blocks:
            connection.execute(
                """INSERT INTO admin_content_blocks(id,chapter_id,title,kind,table_no,source_path,repeat_key,
                   prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["id"], item["chapterId"], item["title"], item.get("kind", "MAPPED_FIELD"),
                 item.get("tableNo", ""), item.get("sourcePath", ""), item.get("repeatKey", ""),
                 item.get("prototypeLocation", ""), item.get("dedupKey", ""), item.get("sortRule", ""),
                 item.get("emptyBehavior", "KEEP"), item.get("mergeRule", "NONE"), item.get("orderNo", 0),
                 int(item.get("enabled", True)), now_iso()),
            )
            connection.executemany(
                "INSERT INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(?,?,?)",
                [(mapping_id, item["id"], order_no)
                 for order_no, mapping_id in enumerate(item.get("mappingIds", []))],
            )

    @staticmethod
    def _restore_table_rules(connection: Any, rules: list[dict[str, Any]]) -> None:
        for item in rules:
            connection.execute(
                """INSERT INTO admin_table_rules(table_no,section_code,mode,header_rows,data_row_start,data_row_end,
                   footer_rows,record_key,merge_fields,enabled,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["tableNo"], item.get("sectionCode", ""), item.get("mode", "ROW_REPEAT"),
                 item.get("headerRows", 1), item.get("dataRowStart", 2), item.get("dataRowEnd", 2),
                 item.get("footerRows", 0), item.get("recordKey", ""),
                 json.dumps(item.get("mergeFields", []), ensure_ascii=False), int(item.get("enabled", True)),
                 item.get("notes", ""), now_iso()),
            )

    @staticmethod
    def _restore_ai_rules(connection: Any, rules: list[dict[str, Any]]) -> None:
        for item in rules:
            connection.execute(
                """INSERT INTO admin_ai_rules(id,field_code,name,input_fields,prompt_template,output_type,max_length,
                   require_citations,requires_approval,provider,model,enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item.get("id"), item["fieldCode"], item["name"],
                 json.dumps(item.get("inputFields", []), ensure_ascii=False), item.get("promptTemplate", ""),
                 item.get("outputType", "richText"), item.get("maxLength", 500),
                 int(item.get("requireCitations", True)), int(item.get("requiresApproval", True)),
                 item.get("provider", "unconfigured"), item.get("model", ""),
                 int(item.get("enabled", True)), now_iso()),
            )
