import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.admin_routes.rule_catalog import _resolve_standard_field
from backend.app.services.rule_admin import RuleAdminRepository
from backend.tests.database_helpers import make_test_database


def _standard_field(label: str) -> dict:
    return {
        "fieldCode": "validation.field_009", "label": label,
        "groupCode": "验证", "collectionCode": "validation",
        "dataType": "string", "cardinality": "ONE", "jsonKey": "field_009",
        "legacyJsonPath": "$.validation.field_009", "description": "",
        "outputFormat": "", "defaultValue": "", "validationRegex": "",
        "orderNo": 9, "enabled": True,
    }


def test_standard_mapping_label_always_comes_from_catalog() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        database.initialize()
        repository = RuleAdminRepository(database, Path(directory) / "unused.json")
        database.upsert_lims_field(_standard_field("检测限-结论"))

        mapping = repository.create_mapping({
            "standardFieldCode": "validation.field_009",
            "wordLabel": "检测限与定量限-结论", "fieldCode": "report.validation.conclusion",
            "sourceType": "SYSTEM", "enabled": True,
        })

        assert mapping["wordLabel"] == "检测限-结论"
        with database.connect() as connection:
            stored = connection.execute(
                "SELECT word_label FROM admin_mapping_rules WHERE id=%s", (mapping["id"],),
            ).fetchone()
        assert stored["word_label"] == ""

        database.upsert_lims_field(_standard_field("检测限结论（新名称）"))
        assert repository.list_mappings()[0]["wordLabel"] == "检测限结论（新名称）"


def test_standard_mapping_rejects_missing_catalog_field() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        database.initialize()
        repository = RuleAdminRepository(database, Path(directory) / "unused.json")

        with pytest.raises(HTTPException, match="标准字段不存在或已停用") as error:
            _resolve_standard_field(repository, {"standardFieldCode": "missing.field"})
        assert error.value.status_code == 422
