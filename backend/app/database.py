import json
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_documents (
                    id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    extracted_fields TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_document_id TEXT,
                    resolved_data TEXT NOT NULL,
                    output_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_document_id) REFERENCES source_documents(id)
                );

                CREATE INDEX IF NOT EXISTS idx_reports_updated_at ON reports(updated_at DESC);

                CREATE TABLE IF NOT EXISTS change_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL,
                    field_code TEXT NOT NULL,
                    old_value TEXT NOT NULL,
                    new_value TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS report_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL,
                    version_no INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                    UNIQUE(report_id, version_no)
                );

                CREATE TABLE IF NOT EXISTS admin_mapping_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_id TEXT NOT NULL UNIQUE,
                    section_code TEXT NOT NULL,
                    table_no TEXT NOT NULL,
                    word_label TEXT NOT NULL,
                    field_code TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_path TEXT NOT NULL DEFAULT '',
                    repeat_type TEXT NOT NULL DEFAULT 'NONE',
                    repeat_key TEXT NOT NULL DEFAULT '',
                    merge_rule TEXT NOT NULL DEFAULT 'PRESERVE',
                    fill_rule TEXT NOT NULL DEFAULT 'TEXT',
                    calculation_rule TEXT NOT NULL DEFAULT '',
                    calculation_expression TEXT NOT NULL DEFAULT '',
                    calculation_dependencies TEXT NOT NULL DEFAULT '[]',
                    calculation_scope TEXT NOT NULL DEFAULT 'REPORT',
                    calculation_precision INTEGER NOT NULL DEFAULT 2,
                    calculation_null_behavior TEXT NOT NULL DEFAULT 'ERROR',
                    control_tag TEXT NOT NULL DEFAULT '',
                    required INTEGER NOT NULL DEFAULT 0,
                    source_pending INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_template_chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    page_hint INTEGER,
                    order_no INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(parent_id) REFERENCES admin_template_chapters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS admin_mapping_chapters (
                    mapping_id INTEGER PRIMARY KEY,
                    chapter_id INTEGER NOT NULL,
                    FOREIGN KEY(mapping_id) REFERENCES admin_mapping_rules(id) ON DELETE CASCADE,
                    FOREIGN KEY(chapter_id) REFERENCES admin_template_chapters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS admin_content_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'MAPPED_FIELD',
                    table_no TEXT NOT NULL DEFAULT '',
                    source_path TEXT NOT NULL DEFAULT '',
                    repeat_key TEXT NOT NULL DEFAULT '',
                    prototype_location TEXT NOT NULL DEFAULT '',
                    dedup_key TEXT NOT NULL DEFAULT '',
                    sort_rule TEXT NOT NULL DEFAULT '',
                    empty_behavior TEXT NOT NULL DEFAULT 'KEEP',
                    merge_rule TEXT NOT NULL DEFAULT 'NONE',
                    order_no INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(chapter_id) REFERENCES admin_template_chapters(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS admin_mapping_blocks (
                    mapping_id INTEGER PRIMARY KEY,
                    block_id INTEGER NOT NULL,
                    order_no INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(mapping_id) REFERENCES admin_mapping_rules(id) ON DELETE CASCADE,
                    FOREIGN KEY(block_id) REFERENCES admin_content_blocks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_admin_content_blocks_chapter
                    ON admin_content_blocks(chapter_id, order_no, id);

                CREATE TABLE IF NOT EXISTS admin_table_rules (
                    table_no TEXT PRIMARY KEY,
                    section_code TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'ROW_REPEAT',
                    header_rows INTEGER NOT NULL DEFAULT 1,
                    data_row_start INTEGER NOT NULL DEFAULT 2,
                    data_row_end INTEGER NOT NULL DEFAULT 2,
                    footer_rows INTEGER NOT NULL DEFAULT 0,
                    record_key TEXT NOT NULL DEFAULT '',
                    merge_fields TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_data_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    config TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_ai_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    field_code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    input_fields TEXT NOT NULL DEFAULT '[]',
                    prompt_template TEXT NOT NULL DEFAULT '',
                    output_type TEXT NOT NULL DEFAULT 'richText',
                    max_length INTEGER NOT NULL DEFAULT 500,
                    require_citations INTEGER NOT NULL DEFAULT 1,
                    requires_approval INTEGER NOT NULL DEFAULT 1,
                    provider TEXT NOT NULL DEFAULT 'unconfigured',
                    model TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_rule_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_no INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    snapshot TEXT NOT NULL,
                    validation_report TEXT NOT NULL,
                    compiled_template TEXT,
                    created_at TEXT NOT NULL,
                    published_at TEXT
                );

                CREATE TABLE IF NOT EXISTS admin_templates (
                    id TEXT PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_template_versions (
                    id TEXT PRIMARY KEY,
                    template_id TEXT NOT NULL,
                    version_no INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    note TEXT NOT NULL DEFAULT '',
                    snapshot TEXT NOT NULL DEFAULT '{}',
                    template_file TEXT,
                    validation_report TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT,
                    FOREIGN KEY(template_id) REFERENCES admin_templates(id) ON DELETE CASCADE,
                    UNIQUE(template_id, version_no)
                );

                CREATE TABLE IF NOT EXISTS admin_template_workspace (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    active_template_id TEXT,
                    active_version_id TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(active_template_id) REFERENCES admin_templates(id),
                    FOREIGN KEY(active_version_id) REFERENCES admin_template_versions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_admin_template_versions_template
                    ON admin_template_versions(template_id, version_no DESC);

                CREATE TABLE IF NOT EXISTS lims_imports (
                    id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    summary TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_lims_imports_created_at ON lims_imports(created_at DESC);

                CREATE TABLE IF NOT EXISTS lims_experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    project_id TEXT,
                    project_name TEXT NOT NULL DEFAULT '',
                    document_code TEXT NOT NULL DEFAULT '',
                    document_version TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    experiment_version TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at_source TEXT,
                    approved_by TEXT NOT NULL DEFAULT '',
                    approved_at_source TEXT,
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    normalized_at TEXT NOT NULL,
                    FOREIGN KEY(import_id) REFERENCES lims_imports(id) ON DELETE CASCADE,
                    UNIQUE(import_id, instance_id)
                );

                CREATE TABLE IF NOT EXISTS lims_standard_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    collection_code TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    order_no INTEGER NOT NULL DEFAULT 0,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(import_id) REFERENCES lims_imports(id) ON DELETE CASCADE,
                    UNIQUE(import_id, instance_id, collection_code, record_key)
                );

                CREATE INDEX IF NOT EXISTS idx_lims_standard_records_lookup
                    ON lims_standard_records(import_id, instance_id, collection_code, order_no);

                CREATE TABLE IF NOT EXISTS lims_unrecognized_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(import_id) REFERENCES lims_imports(id) ON DELETE CASCADE,
                    UNIQUE(import_id, instance_id, item_key)
                );

                CREATE TABLE IF NOT EXISTS lims_field_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    field_code TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    group_code TEXT NOT NULL,
                    collection_code TEXT NOT NULL,
                    data_type TEXT NOT NULL DEFAULT 'string',
                    cardinality TEXT NOT NULL DEFAULT 'ONE',
                    db_table TEXT NOT NULL,
                    db_column TEXT NOT NULL,
                    json_key TEXT NOT NULL DEFAULT '',
                    legacy_json_path TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    output_format TEXT NOT NULL DEFAULT '',
                    default_value TEXT NOT NULL DEFAULT '',
                    validation_regex TEXT NOT NULL DEFAULT '',
                    order_no INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lims_extraction_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    field_code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'NORMALIZED_PATH',
                    source_unit_type TEXT NOT NULL DEFAULT '',
                    source_path TEXT NOT NULL DEFAULT '',
                    section_pattern TEXT NOT NULL DEFAULT '',
                    header_pattern TEXT NOT NULL DEFAULT '',
                    value_pattern TEXT NOT NULL DEFAULT '',
                    transform TEXT NOT NULL DEFAULT 'TRIM',
                    priority INTEGER NOT NULL DEFAULT 100,
                    config TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(field_code) REFERENCES lims_field_catalog(field_code)
                        ON UPDATE CASCADE ON DELETE CASCADE,
                    UNIQUE(field_code, name)
                );

                CREATE INDEX IF NOT EXISTS idx_lims_extraction_rules_field
                    ON lims_extraction_rules(field_code, priority, id);
                """
            )
            mapping_columns = {row["name"] for row in connection.execute("PRAGMA table_info(admin_mapping_rules)")}
            if "standard_field_code" not in mapping_columns:
                connection.execute("ALTER TABLE admin_mapping_rules ADD COLUMN standard_field_code TEXT NOT NULL DEFAULT ''")
            calculation_columns = {
                "calculation_expression": "TEXT NOT NULL DEFAULT ''",
                "calculation_dependencies": "TEXT NOT NULL DEFAULT '[]'",
                "calculation_scope": "TEXT NOT NULL DEFAULT 'REPORT'",
                "calculation_precision": "INTEGER NOT NULL DEFAULT 2",
                "calculation_null_behavior": "TEXT NOT NULL DEFAULT 'ERROR'",
            }
            for column, definition in calculation_columns.items():
                if column not in mapping_columns:
                    connection.execute(
                        f"ALTER TABLE admin_mapping_rules ADD COLUMN {column} {definition}"
                    )
            block_columns = {row["name"] for row in connection.execute("PRAGMA table_info(admin_content_blocks)")}
            block_defaults = {
                "source_path": "''", "repeat_key": "''", "prototype_location": "''",
                "dedup_key": "''", "sort_rule": "''", "empty_behavior": "'KEEP'", "merge_rule": "'NONE'",
            }
            for column, default in block_defaults.items():
                if column not in block_columns:
                    connection.execute(
                        f"ALTER TABLE admin_content_blocks ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}"
                    )
            mapping_block_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(admin_mapping_blocks)")
            }
            if "order_no" not in mapping_block_columns:
                connection.execute(
                    "ALTER TABLE admin_mapping_blocks ADD COLUMN order_no INTEGER NOT NULL DEFAULT 0"
                )
                block_ids = [
                    row["block_id"] for row in connection.execute(
                        "SELECT DISTINCT block_id FROM admin_mapping_blocks"
                    ).fetchall()
                ]
                for block_id in block_ids:
                    mapping_ids = [
                        row["mapping_id"] for row in connection.execute(
                            "SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=? ORDER BY mapping_id",
                            (block_id,),
                        ).fetchall()
                    ]
                    connection.executemany(
                        "UPDATE admin_mapping_blocks SET order_no=? WHERE mapping_id=?",
                        [(order_no, mapping_id) for order_no, mapping_id in enumerate(mapping_ids)],
                    )
            lims_field_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(lims_field_catalog)")
            }
            lims_field_defaults = {
                "description": "TEXT NOT NULL DEFAULT ''",
                "output_format": "TEXT NOT NULL DEFAULT ''",
                "default_value": "TEXT NOT NULL DEFAULT ''",
                "validation_regex": "TEXT NOT NULL DEFAULT ''",
                "order_no": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, definition in lims_field_defaults.items():
                if column not in lims_field_columns:
                    connection.execute(
                        f"ALTER TABLE lims_field_catalog ADD COLUMN {column} {definition}"
                    )

    @staticmethod
    def _decode(row: sqlite3.Row | None, json_fields: tuple[str, ...]) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for field in json_fields:
            item[field] = json.loads(item[field])
        return item

    def create_source(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO source_documents(id,file_name,stored_name,size,extracted_fields,created_at) VALUES(?,?,?,?,?,?)",
                (item["id"], item["file_name"], item["stored_name"], item["size"], "[]", item["created_at"]),
            )
        return self.get_source(item["id"])

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM source_documents WHERE id=?", (source_id,)).fetchone()
        return self._decode(row, ("extracted_fields",))

    def update_extracted_fields(self, source_id: str, fields: list[dict[str, Any]]) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE source_documents SET extracted_fields=? WHERE id=?",
                (json.dumps(fields, ensure_ascii=False), source_id),
            )
        return self.get_source(source_id)

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

    def replace_lims_instance(self, import_id: str, raw: dict[str, Any], normalized: dict[str, Any],
                              collection_names: list[str]) -> None:
        instance_id = str(raw["instanceId"])
        project = normalized.get("project", {})
        document = normalized.get("document", {})
        with self.connect() as connection:
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
            connection.execute(
                "DELETE FROM lims_standard_records WHERE import_id=? AND instance_id=?", (import_id, instance_id)
            )
            for collection in ["approval", *collection_names]:
                for order_no, item in enumerate(normalized.get(collection, [])):
                    evidence = item.get("evidence", {}) if isinstance(item, dict) else {}
                    data = {key: value for key, value in item.items() if key != "evidence"}
                    identity = str(data.get("sourceRecordId") or "")
                    if not identity:
                        identity = hashlib.sha1(
                            json.dumps(data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                        ).hexdigest()[:20]
                    record_key = f"{collection}:{identity}:{order_no}"
                    connection.execute(
                        """INSERT INTO lims_standard_records(import_id,instance_id,collection_code,record_key,
                           order_no,data_json,evidence_json) VALUES(?,?,?,?,?,?,?)""",
                        (import_id, instance_id, collection, record_key, order_no,
                         json.dumps(data, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False)),
                    )
            connection.execute(
                "DELETE FROM lims_unrecognized_items WHERE import_id=? AND instance_id=?", (import_id, instance_id)
            )
            for order_no, item in enumerate(normalized.get("unmatched", [])):
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

    def list_lims_standard_records(self, import_id: str, instance_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT id,collection_code,record_key,order_no,data_json,evidence_json
                   FROM lims_standard_records WHERE import_id=? AND instance_id=?
                   ORDER BY collection_code,order_no""", (import_id, instance_id)
            ).fetchall()
        return [{"id": row["id"], "collectionCode": row["collection_code"], "recordKey": row["record_key"],
                 "orderNo": row["order_no"], "data": json.loads(row["data_json"]),
                 "evidence": json.loads(row["evidence_json"])} for row in rows]

    def preview_lims_field(self, field: dict[str, Any], limit: int = 12) -> dict[str, Any]:
        limit = max(1, min(int(limit), 50))
        items: list[dict[str, Any]] = []
        db_table = str(field.get("dbTable") or "")
        db_column = str(field.get("dbColumn") or "")

        if db_table == "lims_experiments":
            allowed_columns = {
                "project_id", "project_name", "document_code", "document_version", "title",
                "experiment_version", "created_by", "created_at_source", "approved_by", "approved_at_source",
            }
            if db_column not in allowed_columns:
                return {"fieldCode": field["fieldCode"], "total": 0, "items": [], "storageSupported": False}
            with self.connect() as connection:
                rows = connection.execute(
                    f"""SELECT e.import_id,e.instance_id,e.project_name,e.title,e.normalized_at,
                               i.file_name,e.{db_column} AS preview_value
                        FROM lims_experiments e JOIN lims_imports i ON i.id=e.import_id
                        WHERE e.{db_column} IS NOT NULL AND trim(CAST(e.{db_column} AS TEXT))<>''
                        ORDER BY i.created_at DESC,e.normalized_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
                total = connection.execute(
                    f"""SELECT COUNT(*) FROM lims_experiments
                        WHERE {db_column} IS NOT NULL AND trim(CAST({db_column} AS TEXT))<>''"""
                ).fetchone()[0]
            items = [{
                "importId": row["import_id"], "instanceId": row["instance_id"],
                "projectName": row["project_name"], "experimentTitle": row["title"],
                "fileName": row["file_name"], "collectionCode": field.get("collectionCode") or "",
                "recordKey": "", "value": row["preview_value"], "evidence": {},
                "normalizedAt": row["normalized_at"],
            } for row in rows]
            return {"fieldCode": field["fieldCode"], "total": total, "items": items, "storageSupported": True}

        if db_table != "lims_standard_records" or db_column != "data_json":
            return {"fieldCode": field["fieldCode"], "total": 0, "items": [], "storageSupported": False}

        json_key = str(field.get("jsonKey") or "")
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT r.import_id,r.instance_id,r.collection_code,r.record_key,r.data_json,
                          r.evidence_json,e.project_name,e.title,e.normalized_at,i.file_name
                   FROM lims_standard_records r
                   JOIN lims_experiments e ON e.import_id=r.import_id AND e.instance_id=r.instance_id
                   JOIN lims_imports i ON i.id=r.import_id
                   WHERE r.collection_code=?
                   ORDER BY i.created_at DESC,e.normalized_at DESC,r.order_no""",
                (field.get("collectionCode") or "",),
            ).fetchall()

        total = 0
        for row in rows:
            value = self._json_path_value(json.loads(row["data_json"]), json_key)
            if value is None or value == "" or value == []:
                continue
            total += 1
            if len(items) < limit:
                items.append({
                    "importId": row["import_id"], "instanceId": row["instance_id"],
                    "projectName": row["project_name"], "experimentTitle": row["title"],
                    "fileName": row["file_name"], "collectionCode": row["collection_code"],
                    "recordKey": row["record_key"], "value": value,
                    "evidence": json.loads(row["evidence_json"] or "{}"),
                    "normalizedAt": row["normalized_at"],
                })
        return {"fieldCode": field["fieldCode"], "total": total, "items": items, "storageSupported": True}

    @staticmethod
    def _json_path_value(data: Any, json_key: str) -> Any:
        value = data
        for part in json_key.split(".") if json_key else []:
            value = value.get(part) if isinstance(value, dict) else None
            if value is None:
                break
        return value

    def upsert_lims_field(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO lims_field_catalog(field_code,label,group_code,collection_code,data_type,
                   cardinality,db_table,db_column,json_key,legacy_json_path,description,output_format,
                   default_value,validation_regex,order_no,enabled,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(field_code) DO UPDATE SET
                   label=excluded.label,group_code=excluded.group_code,collection_code=excluded.collection_code,
                   data_type=excluded.data_type,cardinality=excluded.cardinality,db_table=excluded.db_table,
                   db_column=excluded.db_column,json_key=excluded.json_key,
                   legacy_json_path=excluded.legacy_json_path,description=excluded.description,
                   output_format=excluded.output_format,default_value=excluded.default_value,
                   validation_regex=excluded.validation_regex,order_no=excluded.order_no,
                   enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (item["fieldCode"], item["label"], item["groupCode"], item["collectionCode"],
                 item.get("dataType", "string"), item.get("cardinality", "ONE"), item["dbTable"],
                 item["dbColumn"], item.get("jsonKey", ""), item.get("legacyJsonPath", ""),
                 item.get("description", ""), item.get("outputFormat", ""),
                 item.get("defaultValue", ""), item.get("validationRegex", ""),
                 int(item.get("orderNo", 0)), int(item.get("enabled", True)), now_iso()),
            )
        return self.get_lims_field(item["fieldCode"])

    def _lims_field_to_api(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "fieldCode": row["field_code"], "label": row["label"],
                "groupCode": row["group_code"], "collectionCode": row["collection_code"],
                "dataType": row["data_type"], "cardinality": row["cardinality"],
                "dbTable": row["db_table"], "dbColumn": row["db_column"], "jsonKey": row["json_key"],
                "legacyJsonPath": row["legacy_json_path"], "description": row["description"],
                "outputFormat": row["output_format"], "defaultValue": row["default_value"],
                "validationRegex": row["validation_regex"], "orderNo": row["order_no"],
                "enabled": bool(row["enabled"]), "updatedAt": row["updated_at"]}

    def get_lims_field(self, field_code: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM lims_field_catalog WHERE field_code=?", (field_code,)
            ).fetchone()
        return self._lims_field_to_api(row) if row else None

    def list_lims_fields(self, include_disabled: bool = False) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM lims_field_catalog "
                + ("" if include_disabled else "WHERE enabled=1 ")
                + "ORDER BY group_code,order_no,field_code"
            ).fetchall()
        return [self._lims_field_to_api(row) for row in rows]

    def delete_lims_field(self, field_code: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM lims_field_catalog WHERE field_code=?", (field_code,)
            )
        return bool(cursor.rowcount)

    def _lims_rule_to_api(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "fieldCode": row["field_code"], "name": row["name"],
                "sourceType": row["source_type"], "sourceUnitType": row["source_unit_type"],
                "sourcePath": row["source_path"], "sectionPattern": row["section_pattern"],
                "headerPattern": row["header_pattern"], "valuePattern": row["value_pattern"],
                "transform": row["transform"], "priority": row["priority"],
                "config": json.loads(row["config"] or "{}"), "enabled": bool(row["enabled"]),
                "updatedAt": row["updated_at"]}

    def list_lims_extraction_rules(self, field_code: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM lims_extraction_rules "
                + ("WHERE field_code=? " if field_code else "")
                + "ORDER BY field_code,priority,id",
                (field_code,) if field_code else (),
            ).fetchall()
        return [self._lims_rule_to_api(row) for row in rows]

    def save_lims_extraction_rule(self, item: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        values = (item["fieldCode"], item["name"], item.get("sourceType", "NORMALIZED_PATH"),
                  item.get("sourceUnitType", ""), item.get("sourcePath", ""),
                  item.get("sectionPattern", ""), item.get("headerPattern", ""),
                  item.get("valuePattern", ""), item.get("transform", "TRIM"),
                  int(item.get("priority", 100)), json.dumps(item.get("config", {}), ensure_ascii=False),
                  int(item.get("enabled", True)), now_iso())
        with self.connect() as connection:
            if rule_id is None:
                cursor = connection.execute(
                    """INSERT INTO lims_extraction_rules(field_code,name,source_type,source_unit_type,
                       source_path,section_pattern,header_pattern,value_pattern,transform,priority,
                       config,enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", values
                )
                rule_id = int(cursor.lastrowid)
            else:
                connection.execute(
                    """UPDATE lims_extraction_rules SET field_code=?,name=?,source_type=?,source_unit_type=?,
                       source_path=?,section_pattern=?,header_pattern=?,value_pattern=?,transform=?,priority=?,
                       config=?,enabled=?,updated_at=? WHERE id=?""", (*values, rule_id)
                )
            row = connection.execute("SELECT * FROM lims_extraction_rules WHERE id=?", (rule_id,)).fetchone()
        if not row:
            raise KeyError(rule_id)
        return self._lims_rule_to_api(row)

    def delete_lims_extraction_rule(self, rule_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM lims_extraction_rules WHERE id=?", (rule_id,))
        return bool(cursor.rowcount)

    def list_reports(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM reports ORDER BY updated_at DESC").fetchall()
        return [self._decode(row, ("resolved_data",)) for row in rows]

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return self._decode(row, ("resolved_data",))

    def create_report(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO reports(id,title,status,source_document_id,resolved_data,output_name,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    item["id"], item["title"], item["status"], item.get("source_document_id"),
                    json.dumps(item["resolved_data"], ensure_ascii=False), item.get("output_name"),
                    item["created_at"], item["updated_at"],
                ),
            )
        return self.get_report(item["id"])

    def update_report(self, report_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"title", "status", "source_document_id", "resolved_data", "output_name"}
        values = {key: value for key, value in changes.items() if key in allowed}
        values["updated_at"] = now_iso()
        if "resolved_data" in values:
            values["resolved_data"] = json.dumps(values["resolved_data"], ensure_ascii=False)
        assignments = ",".join(f"{key}=?" for key in values)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE reports SET {assignments} WHERE id=?",
                (*values.values(), report_id),
            )
        return self.get_report(report_id)

    def add_change(self, report_id: str, field_code: str, old_value: str, new_value: str,
                   operator: str = "当前用户", reason: str = "人工编辑") -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO change_history(report_id,field_code,old_value,new_value,operator,reason,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (report_id, field_code, old_value, new_value, operator, reason, now_iso()),
            )

    def list_changes(self, report_id: str, field_code: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM change_history WHERE report_id=?"
        params: tuple[Any, ...] = (report_id,)
        if field_code:
            sql += " AND field_code=?"
            params += (field_code,)
        sql += " ORDER BY id DESC"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def create_version(self, report_id: str, data: dict[str, Any], note: str = "手工保存") -> dict[str, Any]:
        with self.connect() as connection:
            version_no = connection.execute(
                "SELECT COALESCE(MAX(version_no),0)+1 FROM report_versions WHERE report_id=?", (report_id,)
            ).fetchone()[0]
            cursor = connection.execute(
                "INSERT INTO report_versions(report_id,version_no,note,data,created_at) VALUES(?,?,?,?,?)",
                (report_id, version_no, note, json.dumps(data, ensure_ascii=False), now_iso()),
            )
            version_id = cursor.lastrowid
        return self.get_version(report_id, version_id)

    def get_version(self, report_id: str, version_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM report_versions WHERE report_id=? AND id=?", (report_id, version_id)
            ).fetchone()
        return self._decode(row, ("data",))

    def list_versions(self, report_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM report_versions WHERE report_id=? ORDER BY version_no DESC", (report_id,)
            ).fetchall()
        return [self._decode(row, ("data",)) for row in rows]
