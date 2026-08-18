import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .database_common import now_iso
from .services.system_rule_migration import migrate_legacy_lims_rules
from .repositories.auth import AuthRepositoryMixin
from .repositories.reports import ReportRepositoryMixin
from .repositories.lims_catalog import LimsCatalogRepositoryMixin
from .repositories.lims_instances import LimsInstanceRepositoryMixin
from .repositories.lims_evidence import LimsEvidenceRepositoryMixin
from .repositories.excel_rules import ExcelRuleRepositoryMixin


class Database(
    LimsEvidenceRepositoryMixin, LimsInstanceRepositoryMixin, LimsCatalogRepositoryMixin,
    ReportRepositoryMixin, AuthRepositoryMixin, ExcelRuleRepositoryMixin,
):
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
                    source_type TEXT NOT NULL DEFAULT 'PDF',
                    payload TEXT NOT NULL DEFAULT '{}',
                    warnings TEXT NOT NULL DEFAULT '[]',
                    sha256 TEXT NOT NULL DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS excel_rule_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    validation_report TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT
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

                CREATE TABLE IF NOT EXISTS system_field_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    field_code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'LIMS',
                    priority INTEGER NOT NULL DEFAULT 100,
                    config TEXT NOT NULL DEFAULT '{}',
                    transform TEXT NOT NULL DEFAULT 'TRIM',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(field_code) REFERENCES lims_field_catalog(field_code)
                        ON UPDATE CASCADE ON DELETE CASCADE,
                    UNIQUE(field_code, name)
                );
                CREATE INDEX IF NOT EXISTS idx_system_field_rules_field
                    ON system_field_rules(field_code, priority, id);
                """
            )
            migrate_legacy_lims_rules(connection)
            for row in connection.execute(
                """SELECT a.* FROM admin_ai_rules a JOIN lims_field_catalog f
                   ON f.field_code=a.field_code"""
            ).fetchall():
                config = {
                    "inputFields": json.loads(row["input_fields"] or "[]"),
                    "promptTemplate": row["prompt_template"], "outputType": row["output_type"],
                    "maxLength": row["max_length"], "requireCitations": bool(row["require_citations"]),
                    "requiresApproval": bool(row["requires_approval"]), "provider": row["provider"],
                    "model": row["model"],
                }
                connection.execute(
                    """INSERT OR IGNORE INTO system_field_rules
                       (field_code,name,source_type,priority,config,transform,enabled,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (row["field_code"], row["name"], "AI", 80,
                     json.dumps(config, ensure_ascii=False), "TRIM", row["enabled"], row["updated_at"]),
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
            for row in connection.execute(
                """SELECT * FROM admin_mapping_rules WHERE COALESCE(standard_field_code,'')<>''
                   AND source_type IN ('PDF','CALCULATED','FIXED','MANUAL')"""
            ).fetchall():
                source_type = row["source_type"]
                config = {"sourcePath": row["source_path"]}
                if source_type == "CALCULATED":
                    config.update({
                        "expression": row["calculation_expression"],
                        "dependencies": json.loads(row["calculation_dependencies"] or "[]"),
                        "precision": row["calculation_precision"],
                        "nullBehavior": row["calculation_null_behavior"],
                    })
                connection.execute(
                    """INSERT OR IGNORE INTO system_field_rules
                       (field_code,name,source_type,priority,config,transform,enabled,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (row["standard_field_code"], f"模板迁移 · {row['word_label']}", source_type, 100,
                     json.dumps(config, ensure_ascii=False), "TRIM", row["enabled"], row["updated_at"]),
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
            source_columns = {row["name"] for row in connection.execute("PRAGMA table_info(source_documents)")}
            for column, definition in {
                "source_type": "TEXT NOT NULL DEFAULT 'PDF'", "payload": "TEXT NOT NULL DEFAULT '{}'",
                "warnings": "TEXT NOT NULL DEFAULT '[]'", "sha256": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if column not in source_columns:
                    connection.execute(f"ALTER TABLE source_documents ADD COLUMN {column} {definition}")

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
                """INSERT INTO source_documents(id,file_name,stored_name,size,extracted_fields,
                   source_type,payload,warnings,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (item["id"], item["file_name"], item["stored_name"], item["size"], "[]",
                 item.get("source_type", "PDF"), "{}", "[]", item.get("sha256", ""), item["created_at"]),
            )
        return self.get_source(item["id"])

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM source_documents WHERE id=?", (source_id,)).fetchone()
        return self._decode(row, ("extracted_fields", "payload", "warnings"))

    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM source_documents ORDER BY created_at DESC").fetchall()
        return [self._decode(row, ("extracted_fields", "payload", "warnings")) for row in rows]

    def update_extracted_fields(self, source_id: str, fields: list[dict[str, Any]]) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE source_documents SET extracted_fields=? WHERE id=?",
                (json.dumps(fields, ensure_ascii=False), source_id),
            )
        return self.get_source(source_id)

    def update_source_payload(self, source_id: str, payload: dict[str, Any], warnings: list[str],
                              sha256: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE source_documents SET payload=?,warnings=?,sha256=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), json.dumps(warnings, ensure_ascii=False), sha256, source_id),
            )
        return self.get_source(source_id)
