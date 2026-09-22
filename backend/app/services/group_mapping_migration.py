import logging
from typing import Any

from ..database_common import now_iso


MIGRATION_KEY = "20260921_group_mapping_identity_keys_v1"
logger = logging.getLogger(__name__)


def migrate_group_mapping_identity_keys(database: Any) -> dict[str, int]:
    """Move persisted template repeat keys to the identity key of each group."""
    with database.connect() as connection:
        if connection.execute(
            "SELECT 1 FROM app_migrations WHERE `key`=%s", (MIGRATION_KEY,),
        ).fetchone():
            return {"updated": 0}
        rows = connection.execute(
            """SELECT m.id,g.item_key
               FROM admin_mapping_rules m
               JOIN lims_field_catalog f ON f.field_code=m.standard_field_code
               JOIN system_field_groups g ON g.group_code=f.collection_code
               WHERE m.repeat_type='ROW' AND g.cardinality='MANY' AND g.item_key<>''"""
        ).fetchall()
        updated = 0
        for row in rows:
            updated += int(connection.execute(
                "UPDATE admin_mapping_rules SET repeat_key=%s,updated_at=%s WHERE id=%s AND repeat_key<>%s",
                (row["item_key"], now_iso(), row["id"], row["item_key"]),
            ).rowcount)
        connection.execute(
            "INSERT INTO app_migrations(`key`,applied_at) VALUES(%s,%s)",
            (MIGRATION_KEY, now_iso()),
        )
    if updated:
        logger.info("模板映射循环身份键已迁移 updated=%d", updated)
    return {"updated": updated}
