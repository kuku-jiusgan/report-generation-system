import tempfile
from pathlib import Path

from backend.app.database import Database
from backend.app.services.system_field_groups import (
    assign_field_to_group,
    ensure_system_field_groups,
    list_system_field_groups,
    save_system_field_group,
)


def test_user_group_label_survives_default_synchronization() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "groups.db")
        database.initialize()
        database.upsert_lims_field({
            "fieldCode": "systemSuitabilitySolutions.field1",
            "label": "溶液名称",
            "groupCode": "系统适用性溶液",
            "collectionCode": "systemSuitabilitySolutions",
            "dataType": "string",
            "cardinality": "MANY",
            "dbTable": "lims_standard_records",
            "dbColumn": "data_json",
            "jsonKey": "field1",
            "legacyJsonPath": "$.systemSuitabilitySolutions[*].field1",
            "description": "",
            "outputFormat": "",
            "defaultValue": "",
            "validationRegex": "",
            "orderNo": 1,
            "enabled": True,
        })
        ensure_system_field_groups(database)

        saved = save_system_field_group(database, {
            "groupCode": "systemSuitabilitySolutions",
            "label": "系统适用性溶液配置",
            "cardinality": "MANY",
        })
        ensure_system_field_groups(database)
        listed = next(
            item for item in list_system_field_groups(database)
            if item["groupCode"] == "systemSuitabilitySolutions"
        )

        assert saved["label"] == "系统适用性溶液配置"
        assert listed["label"] == "系统适用性溶液配置"


def test_field_catalog_uses_formal_group_relationship_for_display() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "groups.db")
        database.initialize()
        database.upsert_lims_field({
            "fieldCode": "custom.lodName", "label": "杂质名称", "groupCode": "未分类",
            "collectionCode": "custom", "dataType": "string", "cardinality": "MANY",
            "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "lodName",
            "legacyJsonPath": "$.custom.lodName", "description": "", "outputFormat": "",
            "defaultValue": "", "validationRegex": "", "orderNo": 1, "enabled": True,
        })
        save_system_field_group(database, {
            "groupCode": "detectionLimit", "label": "检测限试验结果表", "cardinality": "MANY",
        })

        assign_field_to_group(database, "detectionLimit", "custom.lodName", "impurityName")

        field = database.get_lims_field("custom.lodName")
        assert field["groupCode"] == "未分类"
        assert field["groupLabel"] == "检测限试验结果表"
        listed = next(item for item in database.list_lims_fields() if item["fieldCode"] == "custom.lodName")
        assert listed["groupCode"] == "未分类"
        assert listed["groupLabel"] == "检测限试验结果表"


def test_chapter_field_list_only_uses_groups_assigned_to_that_chapter() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "groups.db")
        database.initialize()
        with database.connect() as connection:
            chapter_id = connection.execute(
                """INSERT INTO admin_template_chapters(code,title,order_no,enabled,updated_at)
                   VALUES('7.3','检测限与定量限',1,1,'now')"""
            ).lastrowid
        for code, label in (("specificity.name", "专属性杂质"), ("detection.name", "检测限杂质")):
            database.upsert_lims_field({
                "fieldCode": code, "label": label, "groupCode": "未分类", "collectionCode": "custom",
                "dataType": "string", "cardinality": "MANY", "dbTable": "lims_standard_records",
                "dbColumn": "data_json", "jsonKey": "name", "legacyJsonPath": f"$.{code}",
                "description": "", "outputFormat": "", "defaultValue": "", "validationRegex": "",
                "orderNo": 1, "enabled": True,
            })
        save_system_field_group(database, {"groupCode": "specificity", "label": "专属性", "cardinality": "MANY"})
        save_system_field_group(database, {"groupCode": "detection", "label": "检测限", "cardinality": "MANY"})
        assign_field_to_group(database, "specificity", "specificity.name")
        assign_field_to_group(database, "detection", "detection.name")
        with database.connect() as connection:
            connection.execute(
                "INSERT INTO system_field_group_chapters(group_code,chapter_id) VALUES('detection',?)",
                (chapter_id,),
            )

        listed = database.list_lims_fields_for_chapter(chapter_id)

        assert [item["fieldCode"] for item in listed] == ["detection.name"]
