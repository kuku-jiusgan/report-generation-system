import hashlib
import json
from typing import Any

from ..database_common import now_iso


class LimsInstanceRepositoryMixin:
    """LIMS imports, normalized experiments and persisted standard records."""

    def create_lims_import(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO lims_imports(id,file_name,stored_name,size,summary,created_at) VALUES(?,?,?,?,?,?)",
                (item["id"], item["file_name"], item["stored_name"], item["size"],
                 json.dumps(item["summary"], ensure_ascii=False), item["created_at"]),
            )
        return self.get_lims_import(item["id"])

    def get_lims_import(self, import_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM lims_imports WHERE id=?", (import_id,)).fetchone()
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
        connection.execute(
            """INSERT INTO lims_experiments(import_id,instance_id,project_id,project_name,document_code,
               document_version,title,experiment_version,created_by,created_at_source,approved_by,
               approved_at_source,raw_payload,normalized_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(import_id,instance_id) DO UPDATE SET project_id=excluded.project_id,
               project_name=excluded.project_name,document_code=excluded.document_code,
               document_version=excluded.document_version,title=excluded.title,
               experiment_version=excluded.experiment_version,created_by=excluded.created_by,
               created_at_source=excluded.created_at_source,approved_by=excluded.approved_by,
               approved_at_source=excluded.approved_at_source,raw_payload=excluded.raw_payload,
               normalized_at=excluded.normalized_at""",
            (import_id, instance_id, raw.get("projectId"), project.get("name") or "",
             document.get("code") or "", document.get("version") or "", raw.get("title") or "",
             str(raw.get("version") or ""), raw.get("createdBy") or "", raw.get("createdTime"),
             raw.get("approvedBy") or "", raw.get("approvedTime"),
             json.dumps(raw, ensure_ascii=False), now_iso()),
        )

    @classmethod
    def _replace_standard_records(cls, connection: Any, import_id: str, instance_id: str,
                                  normalized: dict[str, Any], collections: list[str]) -> None:
        connection.execute(
            "DELETE FROM lims_standard_records WHERE import_id=? AND instance_id=?", (import_id, instance_id),
        )
        for collection in collections:
            for order_no, item in enumerate(normalized.get(collection, [])):
                evidence = item.get("evidence", {}) if isinstance(item, dict) else {}
                data = {key: value for key, value in item.items() if key != "evidence"}
                record_key = f"{collection}:{cls._record_identity(data)}:{order_no}"
                connection.execute(
                    """INSERT INTO lims_standard_records(import_id,instance_id,collection_code,record_key,
                       order_no,data_json,evidence_json) VALUES(?,?,?,?,?,?,?)""",
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
            "DELETE FROM lims_unrecognized_items WHERE import_id=? AND instance_id=?", (import_id, instance_id),
        )
        for order_no, item in enumerate(items):
            evidence = item.get("evidence", {}) if isinstance(item, dict) else {}
            connection.execute(
                """INSERT INTO lims_unrecognized_items(import_id,instance_id,item_key,raw_json,evidence_json)
                   VALUES(?,?,?,?,?)""",
                (import_id, instance_id, f"unmatched:{order_no}", json.dumps(item, ensure_ascii=False),
                 json.dumps(evidence, ensure_ascii=False)),
            )

    def get_lims_instance_payload(self, import_id: str, instance_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT raw_payload FROM lims_experiments WHERE import_id=? AND instance_id=?",
                (import_id, instance_id),
            ).fetchone()
        return json.loads(row["raw_payload"]) if row else None

    def get_lims_normalized_payload(self, import_id: str, instance_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            experiment = connection.execute(
                """SELECT project_id,project_name,document_code,document_version,title,
                          experiment_version,created_by,created_at_source FROM lims_experiments
                   WHERE import_id=? AND instance_id=?""", (import_id, instance_id),
            ).fetchone()
            if not experiment:
                return None
            rows = connection.execute(
                """SELECT collection_code,data_json,evidence_json FROM lims_standard_records
                   WHERE import_id=? AND instance_id=? ORDER BY collection_code,order_no""",
                (import_id, instance_id),
            ).fetchall()
            unmatched = connection.execute(
                """SELECT raw_json FROM lims_unrecognized_items WHERE import_id=? AND instance_id=?
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
            "project": {"id": experiment["project_id"] or "", "name": experiment["project_name"] or ""},
            "document": {"code": experiment["document_code"] or "", "version": experiment["document_version"] or ""},
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
                   FROM lims_standard_records WHERE import_id=? AND instance_id=?
                   ORDER BY collection_code,order_no""", (import_id, instance_id),
            ).fetchall()
        return [{
            "id": row["id"], "collectionCode": row["collection_code"], "recordKey": row["record_key"],
            "orderNo": row["order_no"], "data": json.loads(row["data_json"]),
            "evidence": json.loads(row["evidence_json"]),
        } for row in rows]
