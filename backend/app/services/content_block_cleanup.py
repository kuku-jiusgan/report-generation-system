import json

from ..database import Database


CONTENT_BLOCK_CLEANUP_MIGRATION = "2026_remove_legacy_content_blocks_v1"


def remove_legacy_content_blocks(database: Database) -> None:
    """Remove obsolete inferred blocks without touching field mappings."""
    if database.migration_applied(CONTENT_BLOCK_CLEANUP_MIGRATION):
        return
    with database.connect() as connection:
        connection.execute("DELETE FROM admin_mapping_blocks")
        connection.execute("DELETE FROM admin_content_blocks")
        rows = connection.execute(
            "SELECT id,snapshot FROM admin_template_versions"
        ).fetchall()
        for row in rows:
            try:
                snapshot = json.loads(row["snapshot"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if "contentBlocks" not in snapshot:
                continue
            snapshot.pop("contentBlocks", None)
            connection.execute(
                "UPDATE admin_template_versions SET snapshot=%s WHERE id=%s",
                (json.dumps(snapshot, ensure_ascii=False), row["id"]),
            )
    database.mark_migration_applied(CONTENT_BLOCK_CLEANUP_MIGRATION)
