#!/usr/bin/env python3
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def replace_references(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {mapping.get(str(key), str(key)): replace_references(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_references(item, mapping) for item in value]
    if not isinstance(value, str):
        return value
    for old, new in mapping.items():
        value = value.replace(old, new)
    return value


def build_mapping(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute(
        """SELECT collection_code,label,group_concat(field_code,'|') codes
           FROM lims_field_catalog GROUP BY collection_code,label HAVING COUNT(*)=2"""
    ).fetchall()
    mapping: dict[str, str] = {}
    for row in rows:
        codes = str(row["codes"]).split("|")
        prefix = f'{row["collection_code"]}.'
        canonical = [code for code in codes if code.startswith(prefix)]
        legacy = [code for code in codes if not code.startswith(prefix)]
        if len(canonical) == 1 and len(legacy) == 1:
            mapping[legacy[0]] = canonical[0]
    return mapping


def merge_rules(connection: sqlite3.Connection, table: str, old: str, new: str) -> None:
    columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})") if row[1] != "id"]
    select_columns = ",".join(columns)
    placeholders = ",".join("?" for _ in columns)
    for row in connection.execute(f"SELECT {select_columns} FROM {table} WHERE field_code=?", (old,)).fetchall():
        values = [new if column == "field_code" else row[column] for column in columns]
        connection.execute(f"INSERT OR IGNORE INTO {table}({select_columns}) VALUES({placeholders})", values)
    connection.execute(f"DELETE FROM {table} WHERE field_code=?", (old,))


def update_json_column(connection: sqlite3.Connection, table: str, key: str, column: str,
                       mapping: dict[str, str]) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
    ).fetchone()
    if not exists:
        return
    for row in connection.execute(f"SELECT {key},{column} FROM {table}").fetchall():
        try:
            payload = json.loads(row[column] or "{}")
        except (TypeError, ValueError):
            continue
        updated = replace_references(payload, mapping)
        if updated != payload:
            connection.execute(
                f"UPDATE {table} SET {column}=? WHERE {key}=?",
                (json.dumps(updated, ensure_ascii=False), row[key]),
            )


def migrate(database: Path, mapping: dict[str, str]) -> Path:
    backup_dir = database.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{database.stem}-before-field-dedup-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(database, backup)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        for old, new in mapping.items():
            merge_rules(connection, "system_field_rules", old, new)
            connection.execute("UPDATE admin_mapping_rules SET standard_field_code=? WHERE standard_field_code=?", (new, old))
            old_ai = connection.execute("SELECT 1 FROM admin_ai_rules WHERE field_code=?", (old,)).fetchone()
            new_ai = connection.execute("SELECT 1 FROM admin_ai_rules WHERE field_code=?", (new,)).fetchone()
            if old_ai and not new_ai:
                connection.execute("UPDATE admin_ai_rules SET field_code=? WHERE field_code=?", (new, old))
            elif old_ai:
                connection.execute("DELETE FROM admin_ai_rules WHERE field_code=?", (old,))
            connection.execute(
                """INSERT OR IGNORE INTO system_field_chapters(field_code,chapter_id,order_no)
                   SELECT ?,chapter_id,order_no FROM system_field_chapters WHERE field_code=?""", (new, old),
            )
            connection.execute("DELETE FROM system_field_chapters WHERE field_code=?", (old,))
            connection.execute("DELETE FROM system_field_group_fields WHERE field_code=?", (old,))
            connection.execute("DELETE FROM standard_field_code_aliases WHERE old_code=?", (new,))
            connection.execute("UPDATE OR IGNORE standard_field_code_aliases SET new_code=? WHERE new_code=?", (new, old))
            connection.execute("DELETE FROM standard_field_code_aliases WHERE new_code=?", (old,))
            connection.execute(
                "INSERT OR REPLACE INTO standard_field_code_aliases(old_code,new_code,migrated_at) VALUES(?,?,?)",
                (old, new, datetime.now().isoformat(timespec="seconds")),
            )
            connection.execute("DELETE FROM lims_field_catalog WHERE field_code=?", (old,))
        for row in connection.execute("SELECT id,config FROM system_field_rules").fetchall():
            config = replace_references(json.loads(row["config"] or "{}"), mapping)
            connection.execute("UPDATE system_field_rules SET config=? WHERE id=?", (json.dumps(config, ensure_ascii=False), row["id"]))
        for row in connection.execute("SELECT id,input_fields,prompt_template FROM admin_ai_rules").fetchall():
            inputs = replace_references(json.loads(row["input_fields"] or "[]"), mapping)
            prompt = replace_references(str(row["prompt_template"] or ""), mapping)
            connection.execute("UPDATE admin_ai_rules SET input_fields=?,prompt_template=? WHERE id=?", (json.dumps(inputs, ensure_ascii=False), prompt, row["id"]))
        for table, key, column in (("admin_template_versions", "id", "snapshot"), ("admin_rule_versions", "id", "snapshot"), ("reports", "id", "resolved_data"), ("report_versions", "id", "data")):
            update_json_column(connection, table, key, column, mapping)
        connection.commit()
        return backup
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="合并同一编组内的同名系统标准字段")
    parser.add_argument("database", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    mapping = build_mapping(connection)
    connection.close()
    if args.dry_run:
        print(json.dumps(mapping, ensure_ascii=False, indent=2))
        return
    backup = migrate(args.database, mapping)
    print(f"merged={len(mapping)} backup={backup}")


if __name__ == "__main__":
    main()
