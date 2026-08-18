#!/usr/bin/env python3
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


CHAPTER_PREFIXES = {
    "cover": "cover", "headerFooter": "header", "1": "overview", "2": "purpose",
    "3": "standards", "4": "materials", "5": "summary", "6": "method",
    "7": "validation", "8": "sample_test", "9": "formula", "10": "deviation",
    "11": "attachment", "12": "history",
}
COLLECTION_PREFIXES = {
    "approval": "cover", "project": "cover", "document": "header",
    "samples": "materials", "referenceStandards": "materials", "instruments": "materials",
    "columns": "materials", "reagents": "materials", "validationSummary": "summary",
    "methodParameters": "method", "narrative": "overview", "custom": "uncategorized",
}


def replace_json(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {mapping.get(str(key), str(key)): replace_json(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_json(item, mapping) for item in value]
    if isinstance(value, str):
        if value in mapping:
            return mapping[value]
        for old, new in mapping.items():
            value = value.replace(f"{{{{{old}}}}}", f"{{{{{new}}}}}")
        return value
    return value


def top_chapter(chapter_id: int, chapters: dict[int, sqlite3.Row]) -> sqlite3.Row | None:
    chapter = chapters.get(chapter_id)
    while chapter and chapter["parent_id"]:
        chapter = chapters.get(int(chapter["parent_id"]))
    return chapter


def build_mapping(connection: sqlite3.Connection) -> dict[str, str]:
    chapters = {int(row["id"]): row for row in connection.execute(
        "SELECT id,parent_id,code,order_no FROM admin_template_chapters"
    )}
    links: dict[str, list[sqlite3.Row]] = {}
    rows = connection.execute(
        """SELECT mc.chapter_id,m.standard_field_code field_code FROM admin_mapping_chapters mc
           JOIN admin_mapping_rules m ON m.id=mc.mapping_id WHERE m.standard_field_code<>''
           UNION SELECT chapter_id,field_code FROM system_field_chapters"""
    ).fetchall()
    for row in rows:
        top = top_chapter(int(row["chapter_id"]), chapters)
        if top:
            links.setdefault(str(row["field_code"]), []).append(top)
    fields = connection.execute(
        "SELECT id,field_code,collection_code FROM lims_field_catalog ORDER BY id"
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for field in fields:
        candidates = sorted(links.get(str(field["field_code"]), []), key=lambda item: item["order_no"])
        prefix = CHAPTER_PREFIXES.get(str(candidates[0]["code"])) if candidates else None
        prefix = prefix or COLLECTION_PREFIXES.get(str(field["collection_code"]), "validation")
        grouped.setdefault(prefix, []).append(field)
    mapping: dict[str, str] = {}
    for prefix, items in grouped.items():
        for index, field in enumerate(items, start=1):
            mapping[str(field["field_code"])] = f"{prefix}.field_{index:03d}"
    return mapping


def update_json_column(connection: sqlite3.Connection, table: str, key: str, column: str,
                       mapping: dict[str, str]) -> None:
    for row in connection.execute(f"SELECT {key},{column} FROM {table}").fetchall():
        try:
            payload = json.loads(row[column] or "{}")
        except (TypeError, ValueError):
            continue
        updated = replace_json(payload, mapping)
        if updated != payload:
            connection.execute(
                f"UPDATE {table} SET {column}=? WHERE {key}=?",
                (json.dumps(updated, ensure_ascii=False), row[key]),
            )


def migrate(database: Path) -> tuple[Path, dict[str, str]]:
    backup_dir = database.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{database.stem}-before-field-codes-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(database, backup)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        mapping = build_mapping(connection)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS standard_field_code_aliases (
               old_code TEXT PRIMARY KEY,new_code TEXT NOT NULL UNIQUE,migrated_at TEXT NOT NULL)"""
        )
        for index, (old, new) in enumerate(mapping.items(), start=1):
            temporary = f"migration_tmp.field_{index:04d}"
            connection.execute("UPDATE lims_field_catalog SET field_code=? WHERE field_code=?", (temporary, old))
            connection.execute("UPDATE admin_mapping_rules SET standard_field_code=? WHERE standard_field_code=?", (temporary, old))
            connection.execute("UPDATE admin_ai_rules SET field_code=? WHERE field_code=?", (temporary, old))
            mapping[old] = new
        for index, (old, new) in enumerate(mapping.items(), start=1):
            temporary = f"migration_tmp.field_{index:04d}"
            connection.execute("UPDATE lims_field_catalog SET field_code=? WHERE field_code=?", (new, temporary))
            connection.execute("UPDATE admin_mapping_rules SET standard_field_code=? WHERE standard_field_code=?", (new, temporary))
            connection.execute("UPDATE admin_ai_rules SET field_code=? WHERE field_code=?", (new, temporary))
            connection.execute(
                "INSERT OR REPLACE INTO standard_field_code_aliases VALUES(?,?,?)",
                (old, new, datetime.now().isoformat(timespec="seconds")),
            )
        for row in connection.execute("SELECT id,config FROM system_field_rules").fetchall():
            config = replace_json(json.loads(row["config"] or "{}"), mapping)
            connection.execute("UPDATE system_field_rules SET config=? WHERE id=?",
                               (json.dumps(config, ensure_ascii=False), row["id"]))
        for row in connection.execute("SELECT id,input_fields,prompt_template FROM admin_ai_rules").fetchall():
            inputs = replace_json(json.loads(row["input_fields"] or "[]"), mapping)
            prompt = replace_json(str(row["prompt_template"] or ""), mapping)
            connection.execute("UPDATE admin_ai_rules SET input_fields=?,prompt_template=? WHERE id=?",
                               (json.dumps(inputs, ensure_ascii=False), prompt, row["id"]))
        for table, key, column in (
            ("admin_template_versions", "id", "snapshot"), ("admin_rule_versions", "id", "snapshot"),
            ("reports", "id", "resolved_data"), ("report_versions", "id", "data"),
        ):
            update_json_column(connection, table, key, column, mapping)
        connection.commit()
        return backup, mapping
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
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
    backup, mapping = migrate(args.database)
    print(f"migrated={len(mapping)} backup={backup}")


if __name__ == "__main__":
    main()
