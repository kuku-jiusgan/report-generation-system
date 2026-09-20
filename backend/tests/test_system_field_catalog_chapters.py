from pathlib import Path

from backend.app.services.system_field_catalog_chapters import (
    MIGRATION_KEY,
    ensure_system_field_catalog_chapters,
)
from backend.app.services.system_field_groups import ensure_system_field_groups
from backend.tests.database_helpers import make_test_database


def test_legacy_memberships_migrate_by_code_and_survive_template_rebuild(tmp_path: Path) -> None:
    database = make_test_database(tmp_path)
    ensure_system_field_groups(database)

    database.upsert_lims_field({
        "fieldCode": "custom.catalogField", "label": "目录字段", "groupCode": "未分类",
        "collectionCode": "custom", "dataType": "string", "cardinality": "ONE",
        "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "catalogField",
        "legacyJsonPath": "$.custom.catalogField", "description": "", "outputFormat": "",
        "defaultValue": "", "validationRegex": "", "orderNo": 4, "enabled": True,
    })
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO admin_template_chapters
               (id,parent_id,code,title,order_no,enabled,updated_at)
               VALUES(901,NULL,'7.1','子章节',0,1,'now'),
                     (900,NULL,'7','父章节',10,1,'now')"""
        )
        connection.execute(
            "UPDATE admin_template_chapters SET parent_id=900 WHERE id=901"
        )
        connection.execute(
            """INSERT INTO system_field_groups
               (group_code,label,description,cardinality,item_path,item_key,payload_key,
                source_mappings,order_no,enabled,updated_at)
               VALUES('catalogGroup','目录编组','','ONE','$.catalogGroup','','','[]',0,1,'now')"""
        )
        connection.execute(
            "INSERT INTO system_field_chapters(field_code,chapter_id,order_no) VALUES(%s,%s,%s)",
            ("custom.catalogField", 901, 4),
        )
        connection.execute(
            "INSERT INTO system_field_group_chapters(group_code,chapter_id,order_no) VALUES(%s,%s,%s)",
            ("catalogGroup", 901, 6),
        )

    ensure_system_field_catalog_chapters(database)

    with database.connect() as connection:
        catalog_child = dict(connection.execute(
            "SELECT id,parent_id FROM system_field_catalog_chapters WHERE code='7.1'"
        ).fetchone())
        catalog_parent = dict(connection.execute(
            "SELECT id FROM system_field_catalog_chapters WHERE code='7'"
        ).fetchone())
        direct = dict(connection.execute(
            "SELECT chapter_id,order_no FROM system_field_catalog_fields WHERE field_code=%s",
            ("custom.catalogField",),
        ).fetchone())
        grouped = dict(connection.execute(
            "SELECT chapter_id,order_no FROM system_field_catalog_groups WHERE group_code=%s",
            ("catalogGroup",),
        ).fetchone())
        assert connection.execute(
            "SELECT 1 FROM app_migrations WHERE `key`=%s", (MIGRATION_KEY,),
        ).fetchone()

    assert catalog_child["parent_id"] == catalog_parent["id"]
    assert direct == {"chapter_id": catalog_child["id"], "order_no": 4}
    assert grouped == {"chapter_id": catalog_child["id"], "order_no": 6}

    with database.connect() as connection:
        connection.execute("DELETE FROM admin_template_chapters")
        connection.execute(
            """INSERT INTO admin_template_chapters
               (id,parent_id,code,title,order_no,enabled,updated_at)
               VALUES(1900,NULL,'7','新父章节',0,1,'later'),
                     (1901,1900,'7.1','新子章节',1,1,'later')"""
        )
    ensure_system_field_catalog_chapters(database)

    with database.connect() as connection:
        assert dict(connection.execute(
            "SELECT chapter_id,order_no FROM system_field_catalog_fields WHERE field_code=%s",
            ("custom.catalogField",),
        ).fetchone()) == direct
        assert dict(connection.execute(
            "SELECT chapter_id,order_no FROM system_field_catalog_groups WHERE group_code=%s",
            ("catalogGroup",),
        ).fetchone()) == grouped
