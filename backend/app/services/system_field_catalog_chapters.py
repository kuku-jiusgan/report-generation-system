import logging
import re
from typing import Any

from ..database import Database, now_iso


logger = logging.getLogger(__name__)
MIGRATION_KEY = "decouple-system-field-catalog-chapters-v1"
SQL_TYPE_PATTERN = re.compile(r"^varchar\([1-9][0-9]*\)$", re.IGNORECASE)
SQL_COLLATION_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def _table_exists(connection: Any, table: str) -> bool:
    return bool(connection.execute(
        """SELECT 1 FROM information_schema.tables
           WHERE table_schema=DATABASE() AND table_name=%s""",
        (table,),
    ).fetchone())


def _reference_column_sql(connection: Any, table: str, column: str) -> str:
    row = connection.execute(
        """SELECT COLUMN_TYPE AS column_type,COLLATION_NAME AS collation_name
           FROM information_schema.columns
           WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s""",
        (table, column),
    ).fetchone()
    if not row:
        raise ValueError(f"缺少字段目录外键来源列 {table}.{column}")
    column_type = str(row["column_type"] or "")
    collation = str(row["collation_name"] or "")
    if not SQL_TYPE_PATTERN.fullmatch(column_type):
        raise ValueError(f"字段目录外键来源列类型不受支持：{table}.{column}={column_type}")
    if not SQL_COLLATION_PATTERN.fullmatch(collation):
        raise ValueError(f"字段目录外键来源列排序规则无效：{table}.{column}={collation}")
    return f"{column_type} COLLATE {collation}"


def _create_catalog_tables(connection: Any) -> None:
    field_code_sql = _reference_column_sql(connection, "lims_field_catalog", "field_code")
    group_code_sql = _reference_column_sql(connection, "system_field_groups", "group_code")
    connection.execute("""CREATE TABLE IF NOT EXISTS system_field_catalog_chapters (
      id INTEGER AUTO_INCREMENT PRIMARY KEY,
      parent_id INTEGER NULL,
      code VARCHAR(255) NOT NULL UNIQUE,
      title VARCHAR(500) NOT NULL,
      page_hint VARCHAR(255) NULL,
      order_no INTEGER NOT NULL DEFAULT 0,
      enabled INTEGER NOT NULL DEFAULT 1,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(parent_id) REFERENCES system_field_catalog_chapters(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""")
    connection.execute(f"""CREATE TABLE IF NOT EXISTS system_field_catalog_fields (
      field_code {field_code_sql} NOT NULL,
      chapter_id INTEGER NOT NULL,
      order_no INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(field_code,chapter_id),
      FOREIGN KEY(field_code) REFERENCES lims_field_catalog(field_code)
        ON UPDATE CASCADE ON DELETE CASCADE,
      FOREIGN KEY(chapter_id) REFERENCES system_field_catalog_chapters(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""")
    connection.execute(f"""CREATE TABLE IF NOT EXISTS system_field_catalog_groups (
      group_code {group_code_sql} NOT NULL,
      chapter_id INTEGER NOT NULL,
      order_no INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(group_code,chapter_id),
      FOREIGN KEY(group_code) REFERENCES system_field_groups(group_code) ON DELETE CASCADE,
      FOREIGN KEY(chapter_id) REFERENCES system_field_catalog_chapters(id) ON DELETE CASCADE
    ) ENGINE=InnoDB""")


def _seed_catalog_chapters(connection: Any) -> int:
    if connection.execute("SELECT 1 FROM system_field_catalog_chapters LIMIT 1").fetchone():
        return 0
    chapters = [dict(row) for row in connection.execute(
        "SELECT * FROM admin_template_chapters ORDER BY order_no,id"
    ).fetchall()]
    if not chapters:
        return 0
    codes = [str(item["code"]) for item in chapters]
    if len(codes) != len(set(codes)):
        raise ValueError("模板章节编码不唯一，无法建立独立字段目录章节")
    for item in chapters:
        connection.execute(
            """INSERT INTO system_field_catalog_chapters
               (id,parent_id,code,title,page_hint,order_no,enabled,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (item["id"], None, item["code"], item["title"],
             item.get("page_hint"), item.get("order_no", 0), item.get("enabled", 1), now_iso()),
        )
    for item in chapters:
        if item.get("parent_id") is not None:
            connection.execute(
                "UPDATE system_field_catalog_chapters SET parent_id=%s WHERE id=%s",
                (item["parent_id"], item["id"]),
            )
    return len(chapters)


def _migrate_legacy_memberships(connection: Any) -> tuple[int, int]:
    direct_count = group_count = 0
    if _table_exists(connection, "system_field_chapters"):
        direct_count = connection.execute(
            """INSERT IGNORE INTO system_field_catalog_fields(field_code,chapter_id,order_no)
               SELECT legacy.field_code,catalog.id,legacy.order_no
               FROM system_field_chapters legacy
               JOIN admin_template_chapters template ON template.id=legacy.chapter_id
               JOIN system_field_catalog_chapters catalog ON catalog.code=template.code"""
        ).rowcount
    if _table_exists(connection, "system_field_group_chapters"):
        group_count = connection.execute(
            """INSERT IGNORE INTO system_field_catalog_groups(group_code,chapter_id,order_no)
               SELECT legacy.group_code,catalog.id,legacy.order_no
               FROM system_field_group_chapters legacy
               JOIN admin_template_chapters template ON template.id=legacy.chapter_id
               JOIN system_field_catalog_chapters catalog ON catalog.code=template.code"""
        ).rowcount
    return direct_count, group_count


def ensure_system_field_catalog_chapters(database: Database) -> None:
    with database.connect() as connection:
        _create_catalog_tables(connection)
        seeded = _seed_catalog_chapters(connection)
        if not connection.execute(
            "SELECT 1 FROM system_field_catalog_chapters LIMIT 1"
        ).fetchone():
            return
        applied = connection.execute(
            "SELECT 1 FROM app_migrations WHERE `key`=%s", (MIGRATION_KEY,),
        ).fetchone()
        if applied:
            return
        direct_count, group_count = _migrate_legacy_memberships(connection)
        connection.execute(
            "INSERT INTO app_migrations(`key`,applied_at) VALUES(%s,%s)",
            (MIGRATION_KEY, now_iso()),
        )
        logger.info(
            "字段目录章节已与模板章节解耦 chapters=%d directFields=%d groups=%d",
            seeded, direct_count, group_count,
        )


def list_system_field_catalog_chapters(database: Database) -> list[dict[str, Any]]:
    ensure_system_field_catalog_chapters(database)
    with database.connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM system_field_catalog_chapters ORDER BY order_no,id"
        ).fetchall()]
