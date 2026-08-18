import json
import sqlite3
from typing import Any


class LimsEvidenceRepositoryMixin:
    """LIMS field evidence, source reconstruction and preview queries."""
    def get_lims_field_source(self, field: dict[str, Any], import_id: str, instance_id: str,
                              record_key: str = "") -> dict[str, Any] | None:
        with self.connect() as connection:
            experiment = connection.execute(
                "SELECT raw_payload FROM lims_experiments WHERE import_id=? AND instance_id=?",
                (import_id, instance_id),
            ).fetchone()
            record = connection.execute(
                """SELECT data_json,evidence_json,order_no FROM lims_standard_records
                   WHERE import_id=? AND instance_id=? AND record_key=?""",
                (import_id, instance_id, record_key),
            ).fetchone() if record_key else None
        if not experiment:
            return None

        raw = json.loads(experiment["raw_payload"] or "{}")
        evidence = json.loads(record["evidence_json"] or "{}") if record else {}
        unit_id = str(evidence.get("unitId") or "")
        rich_text_id = str(evidence.get("richTextId") or "")

        if unit_id:
            unit_items = []
            for item in raw.get("rawStructured", []):
                item_evidence = item.get("evidence", {}) if isinstance(item, dict) else {}
                if str(item_evidence.get("unitId") or "") == unit_id:
                    unit_items.append(item)
            if unit_items:
                return {"fieldCode": field["fieldCode"], "importId": import_id,
                        "instanceId": instance_id, "recordKey": record_key,
                        "matchedBy": "unitId", "matchedValue": unit_id, "source": unit_items}

        if unit_id or rich_text_id:
            rich_text_items = []
            for item in raw.get("richTexts", []):
                item_evidence = item.get("evidence", {}) if isinstance(item, dict) else {}
                item_id = str(item.get("id") or "") if isinstance(item, dict) else ""
                item_unit_id = str(item_evidence.get("unitId") or item_id)
                if ((unit_id and item_unit_id == unit_id)
                        or (rich_text_id and item_id == rich_text_id)):
                    source = dict(item)
                    if evidence.get("tableIndex"):
                        source["tableIndex"] = evidence["tableIndex"]
                    if evidence.get("headers"):
                        source["headers"] = evidence["headers"]
                    rich_text_items.append(source)
            if rich_text_items:
                match_value = unit_id or rich_text_id
                return {"fieldCode": field["fieldCode"], "importId": import_id,
                        "instanceId": instance_id, "recordKey": record_key,
                        "matchedBy": "unitId", "matchedValue": match_value,
                        "source": rich_text_items}

        collection = str(field.get("collectionCode") or "")
        raw_collection = raw.get(collection)
        if isinstance(raw_collection, list):
            if unit_id:
                collection_unit_items = [
                    item for item in raw_collection
                    if isinstance(item, dict)
                    and str((item.get("evidence") or {}).get("unitId") or "") == unit_id
                ]
                if collection_unit_items:
                    return {"fieldCode": field["fieldCode"], "importId": import_id,
                            "instanceId": instance_id, "recordKey": record_key,
                            "matchedBy": "unitId", "matchedValue": unit_id,
                            "source": collection_unit_items}
            if raw_collection:
                return {"fieldCode": field["fieldCode"], "importId": import_id,
                        "instanceId": instance_id, "recordKey": record_key,
                        "matchedBy": "collection", "matchedValue": collection,
                        "source": raw_collection}
        if raw_collection is not None and not isinstance(raw_collection, list):
            return {"fieldCode": field["fieldCode"], "importId": import_id,
                    "instanceId": instance_id, "recordKey": record_key,
                    "matchedBy": "collection", "matchedValue": collection,
                    "source": [raw_collection]}

        return {"fieldCode": field["fieldCode"], "importId": import_id,
                "instanceId": instance_id, "recordKey": record_key,
                "matchedBy": "none", "matchedValue": "", "source": None}

    def get_lims_field_instance_source(self, field: dict[str, Any], import_id: str,
                                       instance_id: str) -> dict[str, Any] | None:
        """Return one field JSON for an experiment, grouped internally by unitId."""
        with self.connect() as connection:
            experiment = connection.execute(
                "SELECT * FROM lims_experiments WHERE import_id=? AND instance_id=?",
                (import_id, instance_id),
            ).fetchone()
            rows = connection.execute(
                """SELECT record_key,data_json,evidence_json,order_no
                   FROM lims_standard_records
                   WHERE import_id=? AND instance_id=? AND collection_code=?
                   ORDER BY order_no,id""",
                (import_id, instance_id, field.get("collectionCode") or ""),
            ).fetchall()
        if not experiment:
            return None

        raw = json.loads(experiment["raw_payload"] or "{}")
        json_key = str(field.get("jsonKey") or "")
        groups: dict[str, dict[str, Any]] = {}
        scalar_columns = {
            "project_id", "project_name", "document_code", "document_version", "title",
            "experiment_version", "created_by", "created_at_source", "approved_by", "approved_at_source",
        }
        db_column = str(field.get("dbColumn") or "")
        if field.get("dbTable") == "lims_experiments" and db_column in scalar_columns:
            value = experiment[db_column]
            if value is not None and str(value).strip():
                raw_collection = raw.get(str(field.get("collectionCode") or ""))
                source_items = list(raw_collection) if isinstance(raw_collection, list) else (
                    [raw_collection] if raw_collection is not None else []
                )
                groups["experiment"] = {
                    "unitId": "",
                    "recognizedItems": [{"recordKey": "", "value": value, "evidence": {}}],
                    "sourceItems": source_items,
                }
        for row in rows:
            value = self._json_path_value(json.loads(row["data_json"] or "{}"), json_key)
            if value is None or value == "" or value == []:
                continue
            evidence = json.loads(row["evidence_json"] or "{}")
            unit_id = str(evidence.get("unitId") or evidence.get("richTextId") or "")
            group_key = unit_id or f"record:{row['record_key']}"
            group = groups.setdefault(group_key, {
                "unitId": unit_id,
                "recognizedItems": [],
                "sourceItems": [],
            })
            group["recognizedItems"].append({
                "recordKey": row["record_key"], "value": value, "evidence": evidence,
            })

        raw_structured = raw.get("rawStructured", [])
        rich_texts = raw.get("richTexts", [])
        raw_collection = raw.get(str(field.get("collectionCode") or ""))
        for group in groups.values():
            unit_id = group["unitId"]
            if unit_id:
                group["sourceItems"] = [
                    item for item in raw_structured
                    if isinstance(item, dict)
                    and str((item.get("evidence") or {}).get("unitId") or "") == unit_id
                ]
                if not group["sourceItems"]:
                    matching_rich_texts = [
                        item for item in rich_texts if isinstance(item, dict)
                        and str((item.get("evidence") or {}).get("unitId") or item.get("id") or "") == unit_id
                    ]
                    if matching_rich_texts:
                        table_groups: dict[int, dict[str, Any]] = {}
                        for recognized in group["recognizedItems"]:
                            recognized_evidence = recognized.get("evidence") or {}
                            table_index = int(recognized_evidence.get("tableIndex") or 0)
                            parsed = table_groups.setdefault(table_index, {
                                "type": "PARSED_HTML_TABLE" if table_index else "PARSED_RICH_TEXT",
                                "richTextId": recognized_evidence.get("richTextId") or unit_id,
                                "tableIndex": table_index or None,
                                "sectionPath": recognized_evidence.get("sectionPath") or [],
                                "headers": recognized_evidence.get("headers") or [],
                                "parsedItems": [],
                            })
                            parsed["parsedItems"].append({
                                "recordKey": recognized["recordKey"], "value": recognized["value"],
                            })
                        group["sourceItems"] = list(table_groups.values())
                if not group["sourceItems"] and isinstance(raw_collection, list):
                    group["sourceItems"] = [
                        item for item in raw_collection
                        if isinstance(item, dict)
                        and str((item.get("evidence") or {}).get("unitId") or "") == unit_id
                    ]
            elif isinstance(raw_collection, list):
                group["sourceItems"] = list(raw_collection)

        recognized_total = sum(len(group["recognizedItems"]) for group in groups.values())
        source = {
            "fieldCode": field["fieldCode"],
            "instanceId": instance_id,
            "experimentTitle": experiment["title"] or raw.get("title") or "",
            "collectionCode": field.get("collectionCode") or "",
            "recognizedTotal": recognized_total,
            "extractionRules": [{
                "id": rule["id"], "name": rule["name"], "sourceType": rule["sourceType"],
                "sourcePath": rule["sourcePath"], "sectionPattern": rule["sectionPattern"],
                "headerPattern": rule["headerPattern"], "valuePattern": rule["valuePattern"],
                "transform": rule["transform"], "priority": rule["priority"],
                "config": rule["config"], "enabled": rule["enabled"],
            } for rule in self.list_lims_parser_rules(field["fieldCode"])],
            "unitGroups": list(groups.values()),
        }
        return {
            "fieldCode": field["fieldCode"], "importId": import_id,
            "instanceId": instance_id, "recordKey": "",
            "matchedBy": "instanceId+unitId", "matchedValue": instance_id,
            "source": source,
        }

    def preview_lims_field(self, field: dict[str, Any], limit: int = 12,
                           instance_ids: list[str] | None = None) -> dict[str, Any]:
        limit = max(1, min(int(limit), 50))
        selected_instances = {str(value) for value in (instance_ids or []) if str(value)}
        db_table = str(field.get("dbTable") or "")
        db_column = str(field.get("dbColumn") or "")
        if db_table == "lims_experiments":
            return self._preview_experiment_field(field, db_column, selected_instances, limit)
        if db_table != "lims_standard_records" or db_column != "data_json":
            return {"fieldCode": field["fieldCode"], "total": 0, "items": [], "storageSupported": False}
        return self._preview_standard_field(field, selected_instances, limit)

    def _preview_experiment_field(self, field: dict[str, Any], db_column: str,
                                  selected: set[str], limit: int) -> dict[str, Any]:
        allowed = {"project_id", "project_name", "document_code", "document_version", "title",
                   "experiment_version", "created_by", "created_at_source", "approved_by", "approved_at_source"}
        if db_column not in allowed:
            return {"fieldCode": field["fieldCode"], "total": 0, "items": [], "storageSupported": False}
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT e.import_id,e.instance_id,e.project_name,e.title,e.normalized_at,
                           i.file_name,i.created_at,e.{db_column} AS preview_value FROM lims_experiments e
                    JOIN lims_imports i ON i.id=e.import_id WHERE e.{db_column} IS NOT NULL
                    AND trim(CAST(e.{db_column} AS TEXT))<>'' ORDER BY i.created_at DESC,e.normalized_at DESC"""
            ).fetchall()
        unique: dict[str, sqlite3.Row] = {}
        for row in rows:
            unique.setdefault(str(row["instance_id"]), row)
        filtered = [row for key, row in unique.items() if not selected or key in selected]
        items = [{"importId": row["import_id"], "instanceId": row["instance_id"],
                  "projectName": row["project_name"], "experimentTitle": row["title"],
                  "fileName": row["file_name"], "collectionCode": field.get("collectionCode") or "",
                  "recordKey": "", "value": row["preview_value"], "evidence": {},
                  "normalizedAt": row["normalized_at"]} for row in filtered[:limit]]
        options = [{"instanceId": row["instance_id"], "experimentTitle": row["title"],
                    "projectName": row["project_name"], "normalizedAt": row["normalized_at"],
                    "recognizedCount": 1} for row in unique.values()]
        return {"fieldCode": field["fieldCode"], "total": len(filtered), "recognizedTotal": len(filtered),
                "availableTotal": len(unique), "options": options, "items": items, "storageSupported": True}

    def _preview_standard_field(self, field: dict[str, Any], selected: set[str], limit: int) -> dict[str, Any]:
        rows = self._standard_preview_rows(str(field.get("collectionCode") or ""))
        grouped = self._group_standard_preview(rows, str(field.get("jsonKey") or ""))
        filtered = [item for key, item in grouped.items() if not selected or key in selected]
        options = [{"instanceId": item["instanceId"], "experimentTitle": item["experimentTitle"],
                    "projectName": item["projectName"], "normalizedAt": item["normalizedAt"],
                    "recognizedCount": int(item["evidence"].get("itemCount") or 0)}
                   for item in grouped.values()]
        recognized = sum(int(item["evidence"].get("itemCount") or 0) for item in filtered)
        return {"fieldCode": field["fieldCode"], "total": len(filtered), "availableTotal": len(grouped),
                "recognizedTotal": recognized, "options": options, "items": filtered[:limit],
                "storageSupported": True}

    def _standard_preview_rows(self, collection_code: str) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """SELECT r.import_id,r.instance_id,r.collection_code,r.record_key,r.data_json,
                          r.evidence_json,e.project_name,e.title,e.normalized_at,i.file_name
                   FROM lims_standard_records r JOIN lims_experiments e
                   ON e.import_id=r.import_id AND e.instance_id=r.instance_id JOIN lims_imports i ON i.id=r.import_id
                   WHERE r.collection_code=? ORDER BY i.created_at DESC,e.normalized_at DESC,r.order_no""",
                (collection_code,),
            ).fetchall()

    def _group_standard_preview(self, rows: list[sqlite3.Row], json_key: str) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        latest: dict[str, str] = {}
        for row in rows:
            instance_id = str(row["instance_id"])
            if str(row["import_id"]) != latest.setdefault(instance_id, str(row["import_id"])):
                continue
            value = self._json_path_value(json.loads(row["data_json"]), json_key)
            if value is None or value == "" or value == []:
                continue
            evidence = json.loads(row["evidence_json"] or "{}")
            group = grouped.setdefault(instance_id, self._preview_group(row, evidence))
            group["recordKeys"].append(row["record_key"])
            group["value"].append(value)
            unit_id = str(evidence.get("unitId") or evidence.get("richTextId") or "")
            if unit_id and unit_id not in group["evidence"]["unitIds"]:
                group["evidence"]["unitIds"].append(unit_id)
            group["evidence"]["itemCount"] += 1
        return grouped

    @staticmethod
    def _preview_group(row: sqlite3.Row, evidence: dict[str, Any]) -> dict[str, Any]:
        return {"importId": row["import_id"], "instanceId": row["instance_id"],
                "projectName": row["project_name"], "experimentTitle": row["title"],
                "fileName": row["file_name"], "collectionCode": row["collection_code"],
                "recordKey": row["record_key"], "recordKeys": [], "value": [],
                "evidence": {**evidence, "unitIds": [], "itemCount": 0}, "normalizedAt": row["normalized_at"]}

    @staticmethod
    def _json_path_value(data: Any, json_key: str) -> Any:
        value = data
        for part in json_key.split(".") if json_key else []:
            value = value.get(part) if isinstance(value, dict) else None
            if value is None:
                break
        return value
