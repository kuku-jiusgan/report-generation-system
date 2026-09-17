import hashlib
import json
from typing import Any

from ..database_common import now_iso
from ..services.lims_normalizer import COLLECTION_ORDER, DERIVED_COLLECTION_CODES


# 归一化载荷里不成行的段（project、document，以及基数为 ONE 的编组）整段存这一列。
# 记录型集合（samples、weighings……）仍然一行一条存在 lims_standard_records。
# 过去这些段只被投影成 project_id/project_name/document_code/document_version 四个列，
# 键名写死在代码里，段里其余的键落库时就丢了——客户名称走 `$.project.clientName`，
# 原始数据里有值，存完却取不到，生成报告时整个字段是空的。
SECTION_COLUMN = "sections_json"

# 导入时一行一条写进 lims_standard_records 的集合。
RECORD_COLLECTIONS = frozenset({"approval", *COLLECTION_ORDER})


def collection_storage(collection_code: str, cardinality: str) -> tuple[str, str] | None:
    """某个集合的数据落在哪张表哪一列，没落库的返回 None。

    字段的证据位置由它所属集合的落库方式决定，不逐字段声明——声明和实际存法是两份东西，
    迟早会对不上：客户名称的集合是 project（不成行的段），声明却写着"一行一条存在
    lims_standard_records"，而 project 从来没有记录行，取值预览因此永远是 0 条。

    基数为 ONE 的编组是不成行的段，整段存在段列里；其余集合（例如溶液视图，读取时才从
    solutions 派生）根本不落库，没有自己的证据可查。
    """
    configured_many = (
        str(cardinality or "").upper() == "MANY" and collection_code not in DERIVED_COLLECTION_CODES
    )
    if collection_code in RECORD_COLLECTIONS or configured_many:
        return "lims_standard_records", "data_json"
    if str(cardinality or "").upper() == "ONE":
        return "lims_experiments", SECTION_COLUMN
    return None


class LimsInstanceRepositoryMixin:
    """LIMS imports, normalized experiments and persisted standard records."""

    def create_lims_import(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO lims_imports(id,file_name,stored_name,size,summary,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (item["id"], item["file_name"], item["stored_name"], item["size"],
                 json.dumps(item["summary"], ensure_ascii=False), item["created_at"]),
            )
        return self.get_lims_import(item["id"])

    def get_lims_import(self, import_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM lims_imports WHERE id=%s", (import_id,)).fetchone()
        return self._decode(row, ("summary",))

    def list_lims_imports(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM lims_imports ORDER BY created_at DESC").fetchall()
        return [self._decode(row, ("summary",)) for row in rows]

    def replace_lims_instance(
        self, import_id: str, raw: dict[str, Any], normalized: dict[str, Any], collection_names: list[str],
    ) -> None:
        instance_id = str(raw["instanceId"])
        with self.connect() as connection:
            self._upsert_experiment(connection, import_id, instance_id, raw, normalized)
            self._replace_standard_records(
                connection, import_id, instance_id, normalized, ["approval", *collection_names],
            )
            self._replace_unrecognized(connection, import_id, instance_id, normalized.get("unmatched", []))

    @staticmethod
    def _upsert_experiment(connection: Any, import_id: str, instance_id: str,
                           raw: dict[str, Any], normalized: dict[str, Any]) -> None:
        project, document = normalized.get("project", {}), normalized.get("document", {})
        # 段的形状决定存法：字典是不成行的段，整段存进 sections_json；列表是记录型集合，走标准记录表。
        sections = {key: value for key, value in normalized.items() if isinstance(value, dict)}
        connection.execute(
            f"""INSERT INTO lims_experiments(import_id,instance_id,project_id,project_name,document_code,
               document_version,title,experiment_version,created_by,created_at_source,approved_by,
               approved_at_source,raw_payload,{SECTION_COLUMN},normalized_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE project_id=VALUES(project_id),
               project_name=VALUES(project_name),document_code=VALUES(document_code),
               document_version=VALUES(document_version),title=VALUES(title),
               experiment_version=VALUES(experiment_version),created_by=VALUES(created_by),
               created_at_source=VALUES(created_at_source),approved_by=VALUES(approved_by),
               approved_at_source=VALUES(approved_at_source),raw_payload=VALUES(raw_payload),
               {SECTION_COLUMN}=VALUES({SECTION_COLUMN}),normalized_at=VALUES(normalized_at)""",
            (import_id, instance_id, raw.get("projectId"), project.get("name") or "",
             document.get("code") or "", document.get("version") or "", raw.get("title") or "",
             str(raw.get("version") or ""), raw.get("createdBy") or "", raw.get("createdTime"),
             raw.get("approvedBy") or "", raw.get("approvedTime"),
             json.dumps(raw, ensure_ascii=False), json.dumps(sections, ensure_ascii=False), now_iso()),
        )

    @classmethod
    def _replace_standard_records(cls, connection: Any, import_id: str, instance_id: str,
                                  normalized: dict[str, Any], collections: list[str]) -> None:
        connection.execute(
            "DELETE FROM lims_standard_records WHERE import_id=%s AND instance_id=%s", (import_id, instance_id),
        )
        for collection in collections:
            for order_no, item in enumerate(normalized.get(collection, [])):
                evidence = item.get("evidence", {}) if isinstance(item, dict) else {}
                data = {key: value for key, value in item.items() if key != "evidence"}
                record_key = f"{collection}:{cls._record_identity(data)}:{order_no}"
                connection.execute(
                    """INSERT INTO lims_standard_records(import_id,instance_id,collection_code,record_key,
                       order_no,data_json,evidence_json) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (import_id, instance_id, collection, record_key, order_no,
                     json.dumps(data, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False)),
                )

    @staticmethod
    def _record_identity(data: dict[str, Any]) -> str:
        identity = str(data.get("sourceRecordId") or "")
        return identity or hashlib.sha1(
            json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]

    @staticmethod
    def _replace_unrecognized(connection: Any, import_id: str, instance_id: str,
                              items: list[dict[str, Any]]) -> None:
        connection.execute(
            "DELETE FROM lims_unrecognized_items WHERE import_id=%s AND instance_id=%s", (import_id, instance_id),
        )
        for order_no, item in enumerate(items):
            evidence = item.get("evidence", {}) if isinstance(item, dict) else {}
            connection.execute(
                """INSERT INTO lims_unrecognized_items(import_id,instance_id,item_key,raw_json,evidence_json)
                   VALUES(%s,%s,%s,%s,%s)""",
                (import_id, instance_id, f"unmatched:{order_no}", json.dumps(item, ensure_ascii=False),
                 json.dumps(evidence, ensure_ascii=False)),
            )

    def get_lims_instance_payload(self, import_id: str, instance_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT raw_payload FROM lims_experiments WHERE import_id=%s AND instance_id=%s",
                (import_id, instance_id),
            ).fetchone()
        return json.loads(row["raw_payload"]) if row else None

    def get_lims_normalized_payload(self, import_id: str, instance_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            experiment = connection.execute(
                f"""SELECT project_id,title,experiment_version,created_by,created_at_source,
                          {SECTION_COLUMN} FROM lims_experiments
                   WHERE import_id=%s AND instance_id=%s""", (import_id, instance_id),
            ).fetchone()
            if not experiment:
                return None
            rows = connection.execute(
                """SELECT collection_code,data_json,evidence_json FROM lims_standard_records
                   WHERE import_id=%s AND instance_id=%s ORDER BY collection_code,order_no""",
                (import_id, instance_id),
            ).fetchall()
            unmatched = connection.execute(
                """SELECT raw_json FROM lims_unrecognized_items WHERE import_id=%s AND instance_id=%s
                   ORDER BY item_key""", (import_id, instance_id),
            ).fetchall()
        payload = self._normalized_header(experiment, instance_id, unmatched)
        for row in rows:
            payload.setdefault(row["collection_code"], []).append({
                **json.loads(row["data_json"] or "{}"),
                "evidence": json.loads(row["evidence_json"] or "{}"),
            })
        return payload

    @staticmethod
    def _normalized_header(experiment: Any, instance_id: str, unmatched: list[Any]) -> dict[str, Any]:
        return {
            # 段整段还原，键名不在这里写死：段里存了什么键就还回什么键。
            **json.loads(experiment[SECTION_COLUMN] or "{}"),
            "approval": [], "instances": [{
                "instanceId": instance_id, "title": experiment["title"] or "",
                "projectId": experiment["project_id"] or "", "version": experiment["experiment_version"] or "",
                "createdBy": experiment["created_by"] or "", "createdTime": experiment["created_at_source"],
            }], "unmatched": [json.loads(row["raw_json"] or "{}") for row in unmatched],
        }

    def list_lims_standard_records(self, import_id: str, instance_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT id,collection_code,record_key,order_no,data_json,evidence_json
                   FROM lims_standard_records WHERE import_id=%s AND instance_id=%s
                   ORDER BY collection_code,order_no""", (import_id, instance_id),
            ).fetchall()
        return [{
            "id": row["id"], "collectionCode": row["collection_code"], "recordKey": row["record_key"],
            "orderNo": row["order_no"], "data": json.loads(row["data_json"]),
            "evidence": json.loads(row["evidence_json"]),
        } for row in rows]
