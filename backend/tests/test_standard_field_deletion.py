"""Deleting a standard field removes its bindings from every template version."""

import json
from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException

from backend.app.admin_routes.rule_catalog import register_rule_catalog_routes
from backend.app.services.rule_admin import RuleAdminRepository
from backend.tests.database_helpers import make_test_database


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIELD_CODE = "uncategorized.field_105"


def _setup(tmp_path: Path):
    database = make_test_database(tmp_path)
    repository = RuleAdminRepository(database, PROJECT_ROOT / "mapping" / "template-mapping.json")
    repository.seed()
    database.upsert_lims_field({
        "fieldCode": FIELD_CODE, "label": "待删除字段", "groupCode": "uncategorized",
        "collectionCode": "", "dataType": "string", "enabled": True,
    })
    mapping = repository.create_mapping({
        "fieldCode": "report.test.field_105", "standardFieldCode": FIELD_CODE,
        "controlTag": "cc.test.field_105", "locationId": "word.content_control.cc.test.field_105",
        "sourceType": "LIMS", "enabled": True,
    })
    repository.save_active_workspace()
    template = repository.list_templates()[0]
    v14 = repository.list_template_versions(template["id"])[0]
    v15 = repository.create_template_version(template["id"], v14["id"], "V15")
    archived = repository.create_template_version(template["id"], v14["id"], "历史版本")
    repository.activate_template_version(template["id"], v15["id"])
    repository.delete_mapping(mapping["id"])
    repository.save_active_workspace()
    # Simulate another unsaved binding in the active workspace.
    repository.create_mapping({
        "fieldCode": "report.test.unsaved", "standardFieldCode": FIELD_CODE,
        "controlTag": "cc.test.unsaved", "locationId": "word.content_control.cc.test.unsaved",
        "sourceType": "LIMS", "enabled": True,
    })
    published_file = tmp_path / "published.docx"
    published_file.write_bytes(b"published template remains unchanged")
    with database.connect() as connection:
        connection.execute(
            "UPDATE admin_template_versions SET status='PUBLISHED',template_file=%s WHERE id=%s",
            (str(published_file), v14["id"]),
        )
        connection.execute(
            "UPDATE admin_template_versions SET status='ARCHIVED' WHERE id=%s", (archived["id"],),
        )
    router = APIRouter()
    register_rule_catalog_routes(router, repository)
    delete = next(route.endpoint for route in router.routes
                  if route.path == "/standard-fields/{field_code:path}" and "DELETE" in route.methods)
    return repository, delete, (v14["id"], v15["id"], archived["id"]), published_file


def test_delete_field_cleans_published_draft_archived_and_workspace(tmp_path: Path) -> None:
    repository, delete, version_ids, published_file = _setup(tmp_path)
    with repository.database.connect() as connection:
        before = {row["id"]: json.loads(row["snapshot"]) for row in connection.execute(
            "SELECT id,snapshot FROM admin_template_versions WHERE id IN (%s,%s,%s)", version_ids,
        ).fetchall()}
    assert any(item["standardFieldCode"] == FIELD_CODE for item in before[version_ids[0]]["mappings"])
    assert not any(item["standardFieldCode"] == FIELD_CODE for item in before[version_ids[1]]["mappings"])

    assert delete(FIELD_CODE) == {"deleted": True}
    assert repository.database.get_lims_field(FIELD_CODE) is None
    assert not any(item["standardFieldCode"] == FIELD_CODE for item in repository.list_mappings())
    with repository.database.connect() as connection:
        rows = connection.execute(
            "SELECT id,status,snapshot FROM admin_template_versions WHERE id IN (%s,%s,%s)", version_ids,
        ).fetchall()
    for row in rows:
        snapshot = json.loads(row["snapshot"])
        assert snapshot["mappings"] == [item for item in before[row["id"]]["mappings"]
                                         if item["standardFieldCode"] != FIELD_CODE]
        assert {key: value for key, value in snapshot.items() if key != "mappings"} == {
            key: value for key, value in before[row["id"]].items() if key != "mappings"
        }
    assert {row["status"] for row in rows} == {"PUBLISHED", "DRAFT", "ARCHIVED"}
    assert published_file.read_bytes() == b"published template remains unchanged"
    repository.activate_template_version(repository.list_templates()[0]["id"], version_ids[0])
    assert not any(item["standardFieldCode"] == FIELD_CODE for item in repository.list_mappings())


def test_invalid_version_snapshot_rolls_back_field_deletion(tmp_path: Path) -> None:
    repository, delete, version_ids, _ = _setup(tmp_path)
    with repository.database.connect() as connection:
        connection.execute(
            "UPDATE admin_template_versions SET snapshot=%s WHERE id=%s", ("{}", version_ids[2]),
        )
    with pytest.raises(HTTPException, match="字段映射无法解析") as error:
        delete(FIELD_CODE)
    assert error.value.status_code == 409
    assert repository.database.get_lims_field(FIELD_CODE) is not None
    assert any(item["standardFieldCode"] == FIELD_CODE for item in repository.list_mappings())
    with repository.database.connect() as connection:
        row = connection.execute(
            "SELECT snapshot FROM admin_template_versions WHERE id=%s", (version_ids[0],),
        ).fetchone()
    assert any(item["standardFieldCode"] == FIELD_CODE for item in json.loads(row["snapshot"])["mappings"])
