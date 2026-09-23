import json
import logging
from typing import Any

from ..database_common import now_iso
from .lims_instances import collection_storage


logger = logging.getLogger(__name__)


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
                   cardinality,json_key,legacy_json_path,description,output_format,fill_rule,
                   default_value,validation_regex,order_no,enabled,updated_at)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                   label=VALUES(label),group_code=VALUES(group_code),collection_code=VALUES(collection_code),
                   data_type=VALUES(data_type),cardinality=VALUES(cardinality),
                   json_key=VALUES(json_key),legacy_json_path=VALUES(legacy_json_path),
                   description=VALUES(description),output_format=VALUES(output_format),fill_rule=VALUES(fill_rule),
                   default_value=VALUES(default_value),
                   validation_regex=VALUES(validation_regex),order_no=VALUES(order_no),enabled=VALUES(enabled),updated_at=VALUES(updated_at)""",
                (item["fieldCode"], item["label"], item["groupCode"], item["collectionCode"],
                 item.get("dataType", "string"), item.get("cardinality", "ONE"),
                 item.get("jsonKey", ""), item.get("legacyJsonPath", ""),
                 item.get("description", ""), item.get("outputFormat", ""), item.get("fillRule", ""),
                 item.get("defaultValue", ""),
                 item.get("validationRegex", ""), int(item.get("orderNo", 0)),
                 int(item.get("enabled", True)), now_iso()),
            )
        return self.get_lims_field(item["fieldCode"])

    @staticmethod
    def _lims_field_to_api(row: Any) -> dict[str, Any]:
        group_codes = row["group_codes"] if "group_codes" in row.keys() else ""
        group_labels = row["group_labels"] if "group_labels" in row.keys() else ""
        # 字段级 collection_code 是历史存储字段；正式编组关系存在时，
        # LIMS 集合编码统一由所属编组编码派生，避免两套配置不一致。
        formal_group = next((code.strip() for code in str(group_codes or "").split(" / ") if code.strip()), "")
        collection_code = formal_group or row["collection_code"]
        return {
            "id": row["id"], "fieldCode": row["field_code"], "label": row["label"],
            "groupCode": row["group_code"], "groupCodes": group_codes.split(" / ") if group_codes else [],
            "groupLabel": group_labels or row["group_code"],
            "groupLabels": group_labels.split(" / ") if group_labels else [],
            "collectionCode": collection_code,
            "dataType": row["data_type"], "cardinality": row["cardinality"],
            "jsonKey": row["json_key"],
            "legacyJsonPath": row["legacy_json_path"], "description": row["description"],
            "outputFormat": row["output_format"], "fillRule": row.get("fill_rule"),
            "defaultValue": row["default_value"],
            "validationRegex": row["validation_regex"], "orderNo": row["order_no"],
            "enabled": bool(row["enabled"]), "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _group_cardinalities(connection: Any) -> dict[str, str]:
        return {str(row["group_code"]): str(row["cardinality"] or "ONE") for row in connection.execute(
            "SELECT group_code,cardinality FROM system_field_groups WHERE enabled=1"
        ).fetchall()}

    @staticmethod
    def _apply_storage(item: dict[str, Any], cardinalities: dict[str, str]) -> None:
        """存储位置由集合的落库方式推出来，目录里不再单独存一份声明。"""
        collection = str(item.get("collectionCode") or "")
        storage = collection_storage(collection, cardinalities.get(collection, ""))
        item["dbTable"], item["dbColumn"] = storage or ("", "")

    @staticmethod
    def _field_contract(connection: Any, field_code: str, json_key: str = "") -> tuple[str, str] | None:
        """根据正式编组关系推导集合编码和完整标准路径。"""
        row = connection.execute(
            """SELECT gf.group_code,gf.level_key,g.cardinality,l.kind
               FROM system_field_group_fields gf
               JOIN system_field_groups g ON BINARY g.group_code=BINARY gf.group_code
               LEFT JOIN system_field_group_levels l
                 ON BINARY l.group_code=BINARY gf.group_code AND BINARY l.level_key=BINARY gf.level_key
              WHERE gf.field_code=%s ORDER BY gf.order_no,gf.group_code LIMIT 1""",
            (field_code,),
        ).fetchone()
        if not row:
            return None
        group_code = str(row["group_code"] or "").strip()
        collection = f"$.{group_code}"
        prefix = f"{collection}[*]" if str(row["cardinality"] or "ONE").upper() == "MANY" else collection
        level_key = str(row["level_key"] or "").strip()
        if level_key:
            level_prefix = level_key + ("[*]" if str(row["kind"] or "") == "ARRAY" else "")
            prefix = f"{prefix}.{level_prefix}"
        key = str(json_key or "").strip() or field_code.rsplit(".", 1)[-1]
        return group_code, f"{prefix}.{key}"

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
                     JOIN system_field_groups g ON BINARY g.group_code=BINARY gf.group_code
                     WHERE g.enabled=1 GROUP BY gf.field_code
                   ) grp ON grp.field_code=f.field_code
                   WHERE f.field_code=%s""", (field_code,),
                ).fetchone()
        if not row:
            return None
        item = self._lims_field_to_api(row)
        with self.connect() as connection:
            cardinalities: dict[str, str] = {}
            if self._group_tables_exist(connection):
                contract = self._field_contract(connection, field_code, str(row["json_key"] or ""))
                if contract:
                    item["collectionCode"], item["legacyJsonPath"] = contract
                cardinalities = self._group_cardinalities(connection)
        self._apply_storage(item, cardinalities)
        return item

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
                       JOIN system_field_groups g ON BINARY g.group_code=BINARY gf.group_code
                       WHERE g.enabled=1 ORDER BY g.order_no,g.group_code
                     ) grouped GROUP BY grouped.field_code
                   ) grp ON grp.field_code=f.field_code """
                + ("" if include_disabled else "WHERE f.enabled=1 ")
                + "ORDER BY COALESCE(grp.group_labels,f.group_code),f.order_no,f.field_code"
                ).fetchall()
        items = [self._lims_field_to_api(row) for row in rows]
        cardinalities: dict[str, str] = {}
        if items:
            with self.connect() as connection:
                if self._group_tables_exist(connection):
                    for item in items:
                        contract = self._field_contract(connection, item["fieldCode"], str(item.get("jsonKey") or ""))
                        if contract:
                            item["collectionCode"], item["legacyJsonPath"] = contract
                    cardinalities = self._group_cardinalities(connection)
        for item in items:
            self._apply_storage(item, cardinalities)
        return items

    def list_lims_fields_for_chapter(self, chapter_id: int) -> list[dict[str, Any]]:
        fields = {item["fieldCode"]: item for item in self.list_lims_fields()}
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT DISTINCT field_code FROM (
                   SELECT gf.field_code FROM system_field_catalog_groups gc
                   JOIN system_field_group_fields gf ON gf.group_code=gc.group_code
                   WHERE gc.chapter_id=%s
                   UNION ALL
                   SELECT sf.field_code FROM system_field_catalog_fields sf
                   WHERE sf.chapter_id=%s
                ) chapter_fields""",
                (chapter_id, chapter_id),
            ).fetchall()
        return [fields[row["field_code"]] for row in rows if row["field_code"] in fields]

    def delete_lims_field(self, field_code: str) -> bool:
        with self.connect() as connection:
            field = connection.execute(
                "SELECT field_code FROM lims_field_catalog WHERE field_code=%s FOR UPDATE", (field_code,),
            ).fetchone()
            if not field:
                return False
            versions = connection.execute(
                "SELECT id,snapshot FROM admin_template_versions FOR UPDATE"
            ).fetchall()
            removed = 0
            for version in versions:
                try:
                    snapshot = json.loads(version["snapshot"])
                    mappings = snapshot["mappings"]
                    if not isinstance(mappings, list) or not all(isinstance(item, dict) for item in mappings):
                        raise ValueError("模板字段映射格式错误")
                except (TypeError, KeyError, json.JSONDecodeError, ValueError) as error:
                    raise ValueError(f"模板版本 {version['id']} 的字段映射无法解析，标准字段未删除") from error
                remaining = [item for item in mappings if item.get("standardFieldCode") != field_code]
                if len(remaining) != len(mappings):
                    snapshot["mappings"] = remaining
                    removed += len(mappings) - len(remaining)
                    connection.execute(
                        "UPDATE admin_template_versions SET snapshot=%s,updated_at=%s WHERE id=%s",
                        (json.dumps(snapshot, ensure_ascii=False), now_iso(), version["id"]),
                    )
            # 当前设计工作区也必须同步清理，避免下一次保存草稿时恢复已删除的引用。
            connection.execute("DELETE FROM admin_mapping_rules WHERE standard_field_code=%s", (field_code,))
            connection.execute("DELETE FROM system_field_rules WHERE field_code=%s", (field_code,))
            if self._group_tables_exist(connection):
                connection.execute("DELETE FROM system_field_group_fields WHERE field_code=%s", (field_code,))
            connection.execute("DELETE FROM system_field_catalog_fields WHERE field_code=%s", (field_code,))
            cursor = connection.execute("DELETE FROM lims_field_catalog WHERE field_code=%s", (field_code,))
        logger.info("标准字段 %s 已删除，清理 %d 条模板版本映射", field_code, removed)
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

    def list_lims_extraction_rules(self, field_code: str = "") -> list[dict[str, Any]]:
        return [rule for rule in self.list_system_field_rules(field_code)
                if rule.get("sourceType") == "LIMS"]

    def save_system_field_rule(self, item: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        source_type = str(item.get("sourceType") or "LIMS").upper()
        values = (
            item["fieldCode"], item["name"], source_type,
            int(item.get("priority", 100)), json.dumps(item.get("config", {}), ensure_ascii=False),
            item.get("transform", "TRIM"), int(item.get("enabled", True)), now_iso(),
        )
        with self.connect() as connection:
            if rule_id is None:
                existing = connection.execute(
                    "SELECT id FROM system_field_rules WHERE field_code=%s AND source_type=%s",
                    (item["fieldCode"], source_type),
                ).fetchone()
                if existing:
                    raise ValueError(
                        f"系统字段 {item['fieldCode']} 已有 {source_type} 来源规则，请编辑现有规则"
                    )
                cursor = connection.execute(
                    """INSERT INTO system_field_rules(field_code,name,source_type,priority,config,
                       transform,enabled,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", values,
                )
                rule_id = int(cursor.lastrowid)
            else:
                current = connection.execute(
                    "SELECT id FROM system_field_rules WHERE id=%s", (rule_id,),
                ).fetchone()
                if not current:
                    raise KeyError(rule_id)
                conflict = connection.execute(
                    "SELECT id FROM system_field_rules WHERE field_code=%s AND source_type=%s AND id<>%s",
                    (item["fieldCode"], source_type, rule_id),
                ).fetchone()
                if conflict:
                    raise ValueError(f"系统字段 {item['fieldCode']} 已有 {source_type} 来源规则")
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
