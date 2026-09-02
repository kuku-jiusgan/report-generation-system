import json
from typing import Any

from ..database_common import now_iso


class LimsCatalogRepositoryMixin:
    """LIMS standard-field catalog and extraction-rule persistence."""

    @staticmethod
    def _group_tables_exist(connection: Any) -> bool:
        rows = connection.execute(
            """SELECT table_name AS name FROM information_schema.tables
               WHERE table_schema=DATABASE() AND table_name IN ('system_field_groups','system_field_group_fields')"""
        ).fetchall()
        return len(rows) == 2

    def upsert_lims_field(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO lims_field_catalog(field_code,label,group_code,collection_code,data_type,
                   cardinality,db_table,db_column,json_key,legacy_json_path,description,output_format,
                   default_value,validation_regex,order_no,enabled,updated_at)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                   label=VALUES(label),group_code=VALUES(group_code),collection_code=VALUES(collection_code),
                   data_type=VALUES(data_type),cardinality=VALUES(cardinality),db_table=VALUES(db_table),
                   db_column=VALUES(db_column),json_key=VALUES(json_key),legacy_json_path=VALUES(legacy_json_path),
                   description=VALUES(description),output_format=VALUES(output_format),default_value=VALUES(default_value),
                   validation_regex=VALUES(validation_regex),order_no=VALUES(order_no),enabled=VALUES(enabled),updated_at=VALUES(updated_at)""",
                (item["fieldCode"], item["label"], item["groupCode"], item["collectionCode"],
                 item.get("dataType", "string"), item.get("cardinality", "ONE"), item["dbTable"],
                 item["dbColumn"], item.get("jsonKey", ""), item.get("legacyJsonPath", ""),
                 item.get("description", ""), item.get("outputFormat", ""), item.get("defaultValue", ""),
                 item.get("validationRegex", ""), int(item.get("orderNo", 0)),
                 int(item.get("enabled", True)), now_iso()),
            )
        return self.get_lims_field(item["fieldCode"])

    @staticmethod
    def _lims_field_to_api(row: Any) -> dict[str, Any]:
        group_codes = row["group_codes"] if "group_codes" in row.keys() else ""
        group_labels = row["group_labels"] if "group_labels" in row.keys() else ""
        return {
            "id": row["id"], "fieldCode": row["field_code"], "label": row["label"],
            "groupCode": row["group_code"], "groupCodes": group_codes.split(" / ") if group_codes else [],
            "groupLabel": group_labels or row["group_code"],
            "groupLabels": group_labels.split(" / ") if group_labels else [],
            "collectionCode": row["collection_code"],
            "dataType": row["data_type"], "cardinality": row["cardinality"],
            "dbTable": row["db_table"], "dbColumn": row["db_column"], "jsonKey": row["json_key"],
            "legacyJsonPath": row["legacy_json_path"], "description": row["description"],
            "outputFormat": row["output_format"], "defaultValue": row["default_value"],
            "validationRegex": row["validation_regex"], "orderNo": row["order_no"],
            "enabled": bool(row["enabled"]), "updatedAt": row["updated_at"],
        }

    def get_lims_field(self, field_code: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            if not self._group_tables_exist(connection):
                row = connection.execute(
                    "SELECT *,NULL AS group_codes,NULL AS group_labels FROM lims_field_catalog WHERE field_code=%s",
                    (field_code,),
                ).fetchone()
            else:
                row = connection.execute(
                """SELECT f.*,grp.group_codes,grp.group_labels FROM lims_field_catalog f
                   LEFT JOIN (
                     SELECT gf.field_code,GROUP_CONCAT(g.group_code SEPARATOR ' / ') AS group_codes,
                            GROUP_CONCAT(g.label SEPARATOR ' / ') AS group_labels
                     FROM system_field_group_fields gf
                     JOIN system_field_groups g ON g.group_code=gf.group_code
                     WHERE g.enabled=1 GROUP BY gf.field_code
                   ) grp ON grp.field_code=f.field_code
                   WHERE f.field_code=%s""", (field_code,),
                ).fetchone()
        return self._lims_field_to_api(row) if row else None

    def list_lims_fields(self, include_disabled: bool = False) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if not self._group_tables_exist(connection):
                rows = connection.execute(
                    "SELECT *,NULL AS group_codes,NULL AS group_labels FROM lims_field_catalog "
                    + ("" if include_disabled else "WHERE enabled=1 ")
                    + "ORDER BY group_code,order_no,field_code"
                ).fetchall()
            else:
                rows = connection.execute(
                """SELECT f.*,grp.group_codes,grp.group_labels FROM lims_field_catalog f
                   LEFT JOIN (
                     SELECT grouped.field_code,GROUP_CONCAT(grouped.group_code SEPARATOR ' / ') AS group_codes,
                            GROUP_CONCAT(grouped.label SEPARATOR ' / ') AS group_labels
                     FROM (
                       SELECT gf.field_code,g.group_code,g.label FROM system_field_group_fields gf
                       JOIN system_field_groups g ON g.group_code=gf.group_code
                       WHERE g.enabled=1 ORDER BY g.order_no,g.group_code
                     ) grouped GROUP BY grouped.field_code
                   ) grp ON grp.field_code=f.field_code """
                + ("" if include_disabled else "WHERE f.enabled=1 ")
                + "ORDER BY COALESCE(grp.group_labels,f.group_code),f.order_no,f.field_code"
                ).fetchall()
        return [self._lims_field_to_api(row) for row in rows]

    def list_lims_fields_for_chapter(self, chapter_id: int) -> list[dict[str, Any]]:
        fields = {item["fieldCode"]: item for item in self.list_lims_fields()}
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT gf.field_code FROM system_field_group_chapters gc
                   JOIN system_field_group_fields gf ON gf.group_code=gc.group_code
                   WHERE gc.chapter_id=%s""",
                (chapter_id,),
            ).fetchall()
        return [fields[row["field_code"]] for row in rows if row["field_code"] in fields]

    def delete_lims_field(self, field_code: str) -> bool:
        with self.connect() as connection:
            connection.execute("DELETE FROM system_field_rules WHERE field_code=%s", (field_code,))
            if self._group_tables_exist(connection):
                connection.execute("DELETE FROM system_field_group_fields WHERE field_code=%s", (field_code,))
            connection.execute("DELETE FROM system_field_chapters WHERE field_code=%s", (field_code,))
            cursor = connection.execute("DELETE FROM lims_field_catalog WHERE field_code=%s", (field_code,))
        return bool(cursor.rowcount)

    @staticmethod
    def _system_rule_to_api(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"], "fieldCode": row["field_code"], "name": row["name"],
            "sourceType": row["source_type"], "priority": row["priority"],
            "config": json.loads(row["config"] or "{}"), "transform": row["transform"],
            "enabled": bool(row["enabled"]), "updatedAt": row["updated_at"],
        }

    def list_system_field_rules(self, field_code: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM system_field_rules "
                + ("WHERE field_code=%s " if field_code else "")
                + "ORDER BY field_code,priority,id", (field_code,) if field_code else (),
            ).fetchall()
        return [self._system_rule_to_api(row) for row in rows]

    def list_lims_parser_rules(self, field_code: str = "") -> list[dict[str, Any]]:
        rules = [rule for rule in self.list_system_field_rules(field_code)
                 if rule.get("sourceType") == "LIMS"]
        for rule in rules:
            config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
            rule.update({
                "sourceType": config.get("extractionType", "NORMALIZED_PATH"),
                "sourceUnitType": config.get("sourceUnitType", ""),
                "sourcePath": config.get("sourcePath", ""),
                "sectionPattern": config.get("sectionPattern", ""),
                "headerPattern": config.get("headerPattern", ""),
                "valuePattern": config.get("valuePattern", ""),
            })
        return rules

    def save_system_field_rule(self, item: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        values = (
            item["fieldCode"], item["name"], item.get("sourceType", "LIMS"),
            int(item.get("priority", 100)), json.dumps(item.get("config", {}), ensure_ascii=False),
            item.get("transform", "TRIM"), int(item.get("enabled", True)), now_iso(),
        )
        with self.connect() as connection:
            if rule_id is None:
                cursor = connection.execute(
                    """INSERT INTO system_field_rules(field_code,name,source_type,priority,config,
                       transform,enabled,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", values,
                )
                rule_id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """UPDATE system_field_rules SET field_code=%s,name=%s,source_type=%s,priority=%s,config=%s,
                       transform=%s,enabled=%s,updated_at=%s WHERE id=%s""", (*values, rule_id),
                )
            row = connection.execute("SELECT * FROM system_field_rules WHERE id=%s", (rule_id,)).fetchone()
        if not row:
            raise KeyError(rule_id)
        return self._system_rule_to_api(row)

    def delete_system_field_rule(self, rule_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM system_field_rules WHERE id=%s", (rule_id,))
        return bool(cursor.rowcount)
