import tempfile
from pathlib import Path

import pytest

from backend.app.database import Database
from backend.app.services.system_field_group_levels import save_group_level
from backend.app.services.system_field_groups import (
    assign_field_to_group,
    delete_system_field_group,
    ensure_system_field_groups,
    list_system_field_groups,
    move_field_ownership,
    save_system_field_group,
)
from backend.tests.database_helpers import make_test_database


def _database(directory: Path) -> Database:
    return make_test_database(directory)


def test_group_schema_requires_item_key_column(tmp_path: Path) -> None:
    database = _database(tmp_path)
    ensure_system_field_groups(database)

    with database.connect() as connection:
        columns = {row["Field"] for row in connection.execute(
            "SHOW COLUMNS FROM system_field_groups"
        ).fetchall()}
    assert "item_key" in columns
    assert list_system_field_groups(database) == []


def test_user_group_label_survives_default_synchronization() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
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
        assert saved["itemPath"] == "$.systemSuitabilitySolutions"
        assert listed["label"] == "系统适用性溶液配置"
        assert listed["itemPath"] == "$.systemSuitabilitySolutions"


def test_group_path_is_derived_when_not_configured() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        saved = save_system_field_group(database, {
            "groupCode": "customResults", "label": "自定义结果", "cardinality": "MANY",
        })

        assert saved["itemPath"] == "$.customResults"


def test_group_path_cannot_use_a_second_business_name() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))

        with pytest.raises(ValueError, match=r"\$\.jiancexian"):
            save_system_field_group(database, {
                "groupCode": "jiancexian", "label": "检测限", "cardinality": "MANY",
                "itemPath": "$.lod",
            })


def test_group_levels_only_accept_the_shared_summary_and_injections_contract() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        save_system_field_group(database, {
            "groupCode": "customResults", "label": "自定义结果", "cardinality": "MANY",
        })

        save_group_level(database, "customResults", {
            "levelKey": "injections", "label": "自定义名称", "kind": "ARRAY", "orderNo": 1,
        })
        saved = next(item for item in list_system_field_groups(database)
                     if item["groupCode"] == "customResults")

        assert saved["levels"] == [{
            "levelKey": "injections", "label": "进样明细", "kind": "ARRAY", "orderNo": 1,
        }]
        with pytest.raises(ValueError, match="已废弃"):
            save_group_level(database, "customResults", {"levelKey": "mingxi", "kind": "ARRAY"})
        with pytest.raises(ValueError, match="summary 或 injections"):
            save_group_level(database, "customResults", {"levelKey": "details", "kind": "ARRAY"})
        with pytest.raises(ValueError, match="必须是对象层"):
            save_group_level(database, "customResults", {"levelKey": "summary", "kind": "ARRAY"})


def test_group_initialization_preserves_existing_detection_limit_records() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        database.create_lims_import({
            "id": "legacy-lod", "file_name": "legacy.json", "stored_name": "legacy.json",
            "size": 1, "summary": {}, "created_at": "2026-09-17T00:00:00",
        })
        raw = {"instanceId": "EXP-LOD", "projectId": "P1"}
        normalized = {
            "project": {"id": "P1"}, "document": {}, "lod": [{"name": "杂质A"}],
            "validationSummary": [{"validationItemCode": "lod", "field1": "检测限"}],
        }
        database.replace_lims_instance(
            "legacy-lod", raw, normalized, ["lod", "validationSummary"],
        )

        ensure_system_field_groups(database)

        payload = database.get_lims_normalized_payload("legacy-lod", "EXP-LOD")
        assert payload["lod"][0]["name"] == "杂质A"
        assert "jiancexian" not in payload
        assert payload["validationSummary"][0]["validationItemCode"] == "lod"


def test_field_catalog_uses_formal_group_relationship_for_display() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
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
        assert field["collectionCode"] == "detectionLimit"
        listed = next(item for item in database.list_lims_fields() if item["fieldCode"] == "custom.lodName")
        assert listed["groupCode"] == "未分类"
        assert listed["groupLabel"] == "检测限试验结果表"
        assert listed["collectionCode"] == "detectionLimit"


def test_chapter_field_list_only_uses_groups_assigned_to_that_chapter() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        ensure_system_field_groups(database)
        with database.connect() as connection:
            chapter_id = connection.execute(
                """INSERT INTO system_field_catalog_chapters(code,title,order_no,enabled,updated_at)
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
                "INSERT INTO system_field_catalog_groups(group_code,chapter_id) VALUES('detection',%s)",
                (chapter_id,),
            )

        listed = database.list_lims_fields_for_chapter(chapter_id)

        assert [item["fieldCode"] for item in listed] == ["detection.name"]


def test_move_field_ownership_replaces_every_previous_directory_location() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        database.upsert_lims_field({
            "fieldCode": "custom.target", "label": "目标字段", "groupCode": "未分类",
            "collectionCode": "custom", "dataType": "string", "cardinality": "ONE",
            "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "target",
            "legacyJsonPath": "$.custom.target", "description": "", "outputFormat": "",
            "defaultValue": "", "validationRegex": "", "orderNo": 7, "enabled": True,
        })
        save_system_field_group(database, {"groupCode": "source", "label": "原编组"})
        save_system_field_group(database, {"groupCode": "target", "label": "目标编组"})
        assign_field_to_group(database, "source", "custom.target")
        ensure_system_field_groups(database)
        with database.connect() as connection:
            chapter_id = connection.execute(
                """INSERT INTO system_field_catalog_chapters(code,title,order_no,enabled,updated_at)
                   VALUES('8','目标章节',8,1,'now')"""
            ).lastrowid
            # 构造历史脏数据，验证迁移不会留下双重目录归属。
            connection.execute(
                "INSERT INTO system_field_catalog_fields(field_code,chapter_id,order_no) VALUES(%s,%s,%s)",
                ("custom.target", chapter_id, 7),
            )

        moved_to_group = move_field_ownership(database, "custom.target", group_code="target")
        assert moved_to_group["groupLabels"] == ["目标编组"]
        assert moved_to_group["collectionCode"] == "target"
        with database.connect() as connection:
            group_rows = connection.execute(
                "SELECT group_code FROM system_field_group_fields WHERE field_code=%s", ("custom.target",),
            ).fetchall()
            chapter_rows = connection.execute(
                "SELECT chapter_id FROM system_field_catalog_fields WHERE field_code=%s", ("custom.target",),
            ).fetchall()
        assert [row["group_code"] for row in group_rows] == ["target"]
        assert chapter_rows == []

        moved_to_chapter = move_field_ownership(database, "custom.target", chapter_id=chapter_id)
        assert moved_to_chapter["groupLabels"] == []
        with database.connect() as connection:
            group_rows = connection.execute(
                "SELECT group_code FROM system_field_group_fields WHERE field_code=%s", ("custom.target",),
            ).fetchall()
            chapter_rows = connection.execute(
                "SELECT chapter_id,order_no FROM system_field_catalog_fields WHERE field_code=%s", ("custom.target",),
            ).fetchall()
        assert group_rows == []
        assert [(row["chapter_id"], row["order_no"]) for row in chapter_rows] == [(chapter_id, 7)]


def test_delete_group_with_fields_is_rejected_without_changing_field() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        database.upsert_lims_field({
            "fieldCode": "custom.target", "label": "目标字段", "groupCode": "未分类",
            "collectionCode": "custom", "dataType": "string", "cardinality": "MANY",
            "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "target",
            "legacyJsonPath": "$.custom.target", "description": "", "outputFormat": "",
            "defaultValue": "", "validationRegex": "", "orderNo": 1, "enabled": True,
        })
        save_system_field_group(database, {
            "groupCode": "legacy", "label": "历史编组", "cardinality": "MANY",
        })
        assign_field_to_group(database, "legacy", "custom.target")

        with pytest.raises(ValueError, match="仍包含 1 个字段"):
            delete_system_field_group(database, "legacy")

        field = database.get_lims_field("custom.target")
        assert field is not None
        assert field["groupCodes"] == ["legacy"]
        assert field["groupCode"] == "未分类"
        assert field["collectionCode"] == "legacy"
        assert field["legacyJsonPath"] == "$.legacy[*].target"


def test_delete_group_with_duplicate_field_membership_is_also_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        database.upsert_lims_field({
            "fieldCode": "custom.conclusion", "label": "验证结论", "groupCode": "验证结论",
            "collectionCode": "legacy", "dataType": "string", "cardinality": "MANY",
            "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "text",
            "legacyJsonPath": "$.legacy[*].text", "description": "", "outputFormat": "",
            "defaultValue": "", "validationRegex": "", "orderNo": 1, "enabled": True,
        })
        save_system_field_group(database, {
            "groupCode": "legacy", "label": "历史编组", "cardinality": "MANY",
        })
        save_system_field_group(database, {
            "groupCode": "summary", "label": "结果汇总", "cardinality": "MANY",
        })
        save_group_level(database, "summary", {
            "levelKey": "injections", "kind": "ARRAY", "orderNo": 1,
        })
        assign_field_to_group(database, "legacy", "custom.conclusion")
        assign_field_to_group(database, "summary", "custom.conclusion")
        with database.connect() as connection:
            connection.execute(
                "UPDATE system_field_group_fields SET level_key='injections' "
                "WHERE group_code='summary' AND field_code='custom.conclusion'"
            )
        before = database.get_lims_field("custom.conclusion")

        with pytest.raises(ValueError, match="仍包含 1 个字段"):
            delete_system_field_group(database, "legacy")

        field = database.get_lims_field("custom.conclusion")
        assert field is not None
        assert before is not None
        assert field["groupCodes"] == ["legacy", "summary"]
        assert field["collectionCode"] == before["collectionCode"]
        assert field["legacyJsonPath"] == before["legacyJsonPath"]


def test_delete_empty_group_succeeds() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        save_system_field_group(database, {
            "groupCode": "empty", "label": "空编组", "cardinality": "ONE",
        })

        assert delete_system_field_group(database, "empty") is True
        assert all(group["groupCode"] != "empty" for group in list_system_field_groups(database))
