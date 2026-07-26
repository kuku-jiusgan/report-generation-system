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
                    word_edit_locked INTEGER NOT NULL DEFAULT 0,
                    word_edited_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_document_id) REFERENCES source_documents(id)
                );

                CREATE INDEX IF NOT EXISTS idx_reports_updated_at ON reports(updated_at DESC);

                CREATE TABLE IF NOT EXISTS app_migrations (
                    key TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

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

                CREATE TABLE IF NOT EXISTS auth_roles (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    immutable INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role_code TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT,
                    FOREIGN KEY(role_code) REFERENCES auth_roles(code)
                );

                CREATE TABLE IF NOT EXISTS auth_role_permissions (
                    role_code TEXT NOT NULL,
                    permission_code TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(role_code, permission_code),
                    FOREIGN KEY(role_code) REFERENCES auth_roles(code) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);

                CREATE TABLE IF NOT EXISTS report_generation_history (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL,
                    version_id INTEGER,
                    generated_by TEXT,
                    status TEXT NOT NULL,
                    output_name TEXT,
                    error_message TEXT NOT NULL DEFAULT '',
                    generated_at TEXT NOT NULL,
                    legacy INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
                    FOREIGN KEY(version_id) REFERENCES report_versions(id),
                    FOREIGN KEY(generated_by) REFERENCES auth_users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_generation_history_time
                    ON report_generation_history(generated_at DESC);

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
            report_columns = {row["name"] for row in connection.execute("PRAGMA table_info(reports)")}
            if "created_by" not in report_columns:
                connection.execute("ALTER TABLE reports ADD COLUMN created_by TEXT")
            if "updated_by" not in report_columns:
                connection.execute("ALTER TABLE reports ADD COLUMN updated_by TEXT")
            if "word_edit_locked" not in report_columns:
                connection.execute("ALTER TABLE reports ADD COLUMN word_edit_locked INTEGER NOT NULL DEFAULT 0")
            if "word_edited_at" not in report_columns:
                connection.execute("ALTER TABLE reports ADD COLUMN word_edited_at TEXT")
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
            } for rule in self.list_lims_extraction_rules(field["fieldCode"])],
            "unitGroups": list(groups.values()),
        }
        return {
            "fieldCode": field["fieldCode"], "importId": import_id,
            "instanceId": instance_id, "recordKey": "",
            "matchedBy": "instanceId+unitId", "matchedValue": instance_id,
            "source": source,
        }

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

    def preview_lims_field(self, field: dict[str, Any], limit: int = 12,
                           instance_ids: list[str] | None = None) -> dict[str, Any]:
        limit = max(1, min(int(limit), 50))
        selected_instances = {str(value) for value in (instance_ids or []) if str(value)}
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
                               i.file_name,i.created_at,e.{db_column} AS preview_value
                        FROM lims_experiments e JOIN lims_imports i ON i.id=e.import_id
                        WHERE e.{db_column} IS NOT NULL AND trim(CAST(e.{db_column} AS TEXT))<>''
                        ORDER BY i.created_at DESC,e.normalized_at DESC"""
                ).fetchall()
            unique_rows: dict[str, sqlite3.Row] = {}
            for row in rows:
                unique_rows.setdefault(str(row["instance_id"]), row)
            options = [{
                "instanceId": row["instance_id"], "experimentTitle": row["title"],
                "projectName": row["project_name"], "normalizedAt": row["normalized_at"],
                "recognizedCount": 1,
            } for row in unique_rows.values()]
            filtered_rows = [row for key, row in unique_rows.items()
                             if not selected_instances or key in selected_instances]
            items = [{
                "importId": row["import_id"], "instanceId": row["instance_id"],
                "projectName": row["project_name"], "experimentTitle": row["title"],
                "fileName": row["file_name"], "collectionCode": field.get("collectionCode") or "",
                "recordKey": "", "value": row["preview_value"], "evidence": {},
                "normalizedAt": row["normalized_at"],
            } for row in filtered_rows[:limit]]
            total = len(filtered_rows)
            return {"fieldCode": field["fieldCode"], "total": total, "recognizedTotal": total,
                    "availableTotal": len(unique_rows), "options": options,
                    "items": items, "storageSupported": True}

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

        recognized_total = 0
        grouped: dict[str, dict[str, Any]] = {}
        latest_import_by_instance: dict[str, str] = {}
        for row in rows:
            instance_id = str(row["instance_id"])
            latest_import = latest_import_by_instance.setdefault(instance_id, str(row["import_id"]))
            if str(row["import_id"]) != latest_import:
                continue
            value = self._json_path_value(json.loads(row["data_json"]), json_key)
            if value is None or value == "" or value == []:
                continue
            recognized_total += 1
            group_key = instance_id
            evidence = json.loads(row["evidence_json"] or "{}")
            if group_key not in grouped:
                grouped[group_key] = {
                    "importId": row["import_id"], "instanceId": row["instance_id"],
                    "projectName": row["project_name"], "experimentTitle": row["title"],
                    "fileName": row["file_name"], "collectionCode": row["collection_code"],
                    "recordKey": row["record_key"], "recordKeys": [], "value": [],
                    "evidence": {**evidence, "unitIds": [], "itemCount": 0},
                    "normalizedAt": row["normalized_at"],
                }
            group = grouped[group_key]
            group["recordKeys"].append(row["record_key"])
            group["value"].append(value)
            unit_id = str(evidence.get("unitId") or evidence.get("richTextId") or "")
            if unit_id and unit_id not in group["evidence"]["unitIds"]:
                group["evidence"]["unitIds"].append(unit_id)
            group["evidence"]["itemCount"] += 1
        options = [{
            "instanceId": item["instanceId"], "experimentTitle": item["experimentTitle"],
            "projectName": item["projectName"], "normalizedAt": item["normalizedAt"],
            "recognizedCount": int(item["evidence"].get("itemCount") or 0),
        } for item in grouped.values()]
        filtered_groups = [item for key, item in grouped.items()
                           if not selected_instances or key in selected_instances]
        items = filtered_groups[:limit]
        filtered_recognized_total = sum(int(item["evidence"].get("itemCount") or 0)
                                        for item in filtered_groups)
        return {"fieldCode": field["fieldCode"], "total": len(filtered_groups),
                "availableTotal": len(grouped), "recognizedTotal": filtered_recognized_total,
                "options": options, "items": items, "storageSupported": True}

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

    def list_reports(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if owner_id:
                rows = connection.execute(
                    "SELECT * FROM reports WHERE created_by=? ORDER BY updated_at DESC", (owner_id,)
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM reports ORDER BY updated_at DESC").fetchall()
        return [self._decode(row, ("resolved_data",)) for row in rows]

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return self._decode(row, ("resolved_data",))

    def create_report(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO reports(id,title,status,source_document_id,resolved_data,output_name,
                   created_at,updated_at,created_by,updated_by,word_edit_locked,word_edited_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item["id"], item["title"], item["status"], item.get("source_document_id"),
                    json.dumps(item["resolved_data"], ensure_ascii=False), item.get("output_name"),
                    item["created_at"], item["updated_at"], item.get("created_by"), item.get("updated_by"),
                    int(item.get("word_edit_locked", False)), item.get("word_edited_at"),
                ),
            )
        return self.get_report(item["id"])

    def update_report(self, report_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"title", "status", "source_document_id", "resolved_data", "output_name", "updated_by",
                   "word_edit_locked", "word_edited_at"}
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

    def migration_applied(self, key: str) -> bool:
        with self.connect() as connection:
            return bool(connection.execute("SELECT 1 FROM app_migrations WHERE key=?", (key,)).fetchone())

    def clear_report_test_data(self) -> None:
        """Delete report-domain test data while preserving configuration and identity data."""
        with self.connect() as connection:
            connection.execute("DELETE FROM report_generation_history")
            connection.execute("DELETE FROM change_history")
            connection.execute("DELETE FROM report_versions")
            connection.execute("DELETE FROM reports")
            connection.execute("DELETE FROM source_documents")

    def mark_migration_applied(self, key: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO app_migrations(key,applied_at) VALUES(?,?)", (key, now_iso())
            )

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

    # Authentication and authorization
    def seed_roles(self, roles: list[dict[str, Any]], permissions: dict[str, set[str]]) -> None:
        timestamp = now_iso()
        with self.connect() as connection:
            for role in roles:
                connection.execute(
                    """INSERT INTO auth_roles(code,name,description,immutable,updated_at) VALUES(?,?,?,?,?)
                       ON CONFLICT(code) DO UPDATE SET name=excluded.name,description=excluded.description,
                       immutable=excluded.immutable""",
                    (role["code"], role["name"], role.get("description", ""), int(role.get("immutable", False)), timestamp),
                )
                exists = connection.execute(
                    "SELECT 1 FROM auth_role_permissions WHERE role_code=? LIMIT 1", (role["code"],)
                ).fetchone()
                if not exists:
                    connection.executemany(
                        "INSERT INTO auth_role_permissions(role_code,permission_code,updated_at) VALUES(?,?,?)",
                        [(role["code"], code, timestamp) for code in sorted(permissions.get(role["code"], set()))],
                    )

    def count_users(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0])

    def create_user(self, item: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO auth_users(id,username,display_name,password_hash,role_code,enabled,
                   must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (item["id"], item["username"], item["display_name"], item["password_hash"], item["role_code"],
                 int(item.get("enabled", True)), int(item.get("must_change_password", True)), timestamp, timestamp),
            )
        return self.get_user(item["id"])

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM auth_users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM auth_users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        return dict(row) if row else None

    def list_users(self, query: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            if query:
                pattern = f"%{query}%"
                rows = connection.execute(
                    """SELECT * FROM auth_users WHERE username LIKE ? OR display_name LIKE ?
                       ORDER BY created_at DESC""", (pattern, pattern)
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM auth_users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def update_user(self, user_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"display_name", "password_hash", "role_code", "enabled", "must_change_password", "last_login_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return self.get_user(user_id)
        values["updated_at"] = now_iso()
        assignments = ",".join(f"{key}=?" for key in values)
        with self.connect() as connection:
            connection.execute(f"UPDATE auth_users SET {assignments} WHERE id=?", (*values.values(), user_id))
        return self.get_user(user_id)

    def delete_user_sessions(self, user_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))

    def delete_user_sessions_for_role(self, role_code: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE user_id IN (SELECT id FROM auth_users WHERE role_code=?)",
                (role_code,),
            )

    def create_session(self, token_hash: str, user_id: str, expires_at: str) -> None:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions(token_hash,user_id,expires_at,created_at,last_seen_at) VALUES(?,?,?,?,?)",
                (token_hash, user_id, expires_at, timestamp, timestamp),
            )

    def get_session_user(self, token_hash: str) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self.connect() as connection:
            row = connection.execute(
                """SELECT u.* FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1""", (token_hash, timestamp)
            ).fetchone()
            if row:
                connection.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (timestamp, token_hash))
            else:
                connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
        return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))

    def role_permissions(self, role_code: str) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT permission_code FROM auth_role_permissions WHERE role_code=?", (role_code,)
            ).fetchall()
        return {str(row["permission_code"]) for row in rows}

    def list_roles(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            roles = [dict(row) for row in connection.execute("SELECT * FROM auth_roles ORDER BY code").fetchall()]
        for role in roles:
            role["permissions"] = sorted(self.role_permissions(role["code"]))
        return roles

    def replace_role_permissions(self, role_code: str, permissions: set[str]) -> None:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_role_permissions WHERE role_code=?", (role_code,))
            connection.executemany(
                "INSERT INTO auth_role_permissions(role_code,permission_code,updated_at) VALUES(?,?,?)",
                [(role_code, code, timestamp) for code in sorted(permissions)],
            )
            connection.execute("UPDATE auth_roles SET updated_at=? WHERE code=?", (timestamp, role_code))

    def backfill_report_ownership(self, user_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE reports SET created_by=? WHERE created_by IS NULL", (user_id,))
            connection.execute("UPDATE reports SET updated_by=? WHERE updated_by IS NULL", (user_id,))

    # Immutable report generation history
    def create_generation(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO report_generation_history(id,report_id,version_id,generated_by,status,
                   output_name,error_message,generated_at,legacy) VALUES(?,?,?,?,?,?,?,?,?)""",
                (item["id"], item["report_id"], item.get("version_id"), item.get("generated_by"), item["status"],
                 item.get("output_name"), item.get("error_message", ""), item.get("generated_at", now_iso()),
                 int(item.get("legacy", False))),
            )
        return self.get_generation(item["id"])

    def update_generation(self, generation_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"status", "output_name", "error_message"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if values:
            assignments = ",".join(f"{key}=?" for key in values)
            with self.connect() as connection:
                connection.execute(
                    f"UPDATE report_generation_history SET {assignments} WHERE id=?",
                    (*values.values(), generation_id),
                )
        return self.get_generation(generation_id)

    def get_generation(self, generation_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT g.*,r.title,r.status AS report_status,r.resolved_data,
                   u.username,u.display_name,v.version_no
                   FROM report_generation_history g JOIN reports r ON r.id=g.report_id
                   LEFT JOIN auth_users u ON u.id=g.generated_by
                   LEFT JOIN report_versions v ON v.id=g.version_id WHERE g.id=?""", (generation_id,)
            ).fetchone()
        return self._decode(row, ("resolved_data",))

    def is_generation_output(self, output_name: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM report_generation_history WHERE output_name=? LIMIT 1", (output_name,)
            ).fetchone()
        return bool(row)

    def list_generations(self, query: str = "", status: str = "", user_id: str = "",
                         date_from: str = "", date_to: str = "", page: int = 1,
                         page_size: int = 20) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append("(r.title LIKE ? OR json_extract(r.resolved_data,'$.report_no') LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        if status:
            where.append("g.status=?")
            params.append(status)
        if user_id:
            where.append("g.generated_by=?")
            params.append(user_id)
        if date_from:
            where.append("g.generated_at>=?")
            params.append(date_from)
        if date_to:
            where.append("g.generated_at<=?")
            params.append(date_to)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.connect() as connection:
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM report_generation_history g JOIN reports r ON r.id=g.report_id {clause}", params
            ).fetchone()[0])
            rows = connection.execute(
                f"""SELECT g.*,r.title,r.status AS report_status,r.resolved_data,
                    u.username,u.display_name,v.version_no
                    FROM report_generation_history g JOIN reports r ON r.id=g.report_id
                    LEFT JOIN auth_users u ON u.id=g.generated_by
                    LEFT JOIN report_versions v ON v.id=g.version_id {clause}
                    ORDER BY g.generated_at DESC LIMIT ? OFFSET ?""",
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {"total": total, "page": page, "pageSize": page_size,
                "items": [self._decode(row, ("resolved_data",)) for row in rows]}
