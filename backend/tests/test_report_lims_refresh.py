from unittest.mock import MagicMock

import pytest

from backend.app.services.report_lims_refresh import (
    LimsSourceError,
    lims_source_metadata,
    refresh_report_lims_payload,
    recognize_imported_lims,
    recognize_latest_lims,
)
from backend.app.services.standard_payloads import active_standard_payload


def _field(code: str, key: str) -> dict:
    return {
        "fieldCode": code,
        "collectionCode": "referenceStandards",
        "jsonKey": key,
        "legacyJsonPath": f"$.referenceStandards[*].{key}",
        "cardinality": "MANY",
        "dataType": "string",
        "defaultValue": "",
        "validationRegex": "",
        "enabled": True,
    }


def _rule(code: str, path: str) -> dict:
    return {
        "id": 1,
        "fieldCode": code,
        "name": "对照品字段",
        "sourceType": "LIMS",
        "config": {
            "extractionType": "RAW_UNIT_FIELD",
            "sourceUnitType": "Standard",
            "sourcePath": path,
        },
        "transform": "TRIM",
        "enabled": True,
    }


def _database() -> MagicMock:
    database = MagicMock()
    database.get_lims_import.return_value = {"id": "import-1"}
    database.list_lims_fields.return_value = [
        _field("referenceStandards.name", "name"),
        _field("referenceStandards.batchNo", "batchNo"),
    ]
    database.list_lims_extraction_rules.return_value = [
        _rule("referenceStandards.name", "ext$.mtlname"),
        _rule("referenceStandards.batchNo", "batchNo"),
    ]
    database.get_lims_instance_payload.return_value = {
        "instanceId": "instance-1",
        "projectId": "project-1",
        "title": "验证实验",
        "rawStructured": [{
            "unitType": "Standard",
            "data": {"ext$": {"mtlname": "对照品甲"}, "batchNo": "B-001"},
            "evidence": {"instanceId": "instance-1", "unitId": "standard-1"},
        }],
        "richTexts": [],
    }
    return database


def _current_instance() -> dict:
    return {
        "instanceId": "instance-1",
        "projectId": "project-1",
        "title": "验证实验",
        "rawStructured": [{
            "unitType": "Standard",
            "data": {"ext$": {"mtlname": "最新对照品"}, "batchNo": "B-002"},
            "evidence": {"instanceId": "instance-1", "unitId": "standard-2"},
        }],
        "richTexts": [],
    }


def _mock_latest_query(monkeypatch, instances: list[dict] | None = None) -> None:
    monkeypatch.setattr(
        "backend.app.services.report_lims_refresh.query_lims_project",
        lambda _settings, _project_id: ({"instanceCount": 1}, instances or [_current_instance()]),
    )


def test_import_preview_reextracts_raw_lims_with_current_rules(monkeypatch) -> None:
    database = _database()
    monkeypatch.setattr(
        "backend.app.services.report_lims_refresh.list_system_field_groups", lambda _database: [],
    )

    recognition = recognize_imported_lims(database, "import-1", ["instance-1"])

    assert recognition["payload"]["referenceStandards"] == [{
        "name": "对照品甲",
        "evidence": {"instanceId": "instance-1", "unitId": "standard-1"},
        "batchNo": "B-001",
    }]
    database.get_lims_normalized_payload.assert_not_called()


def test_report_refresh_queries_latest_lims_and_keeps_source_binding(monkeypatch) -> None:
    database = _database()
    settings = MagicMock()
    _mock_latest_query(monkeypatch)
    monkeypatch.setattr(
        "backend.app.services.report_lims_refresh.list_system_field_groups", lambda _database: [],
    )
    source = lims_source_metadata("project-1", ["instance-1"], {})
    data = {
        "source_payloads": {
            "EXCEL": {"referenceStandards": [{"name": "旧 Excel 值"}]},
            "LIMS": {"referenceStandards": []},
            "LIMS_SOURCE": source,
        },
    }

    refresh_report_lims_payload(database, settings, data)

    assert data["active_source_type"] == "LIMS"
    assert data["source_payloads"]["LIMS_SOURCE"] == source
    assert data["source_payloads"]["LIMS"]["referenceStandards"][0]["name"] == "最新对照品"
    assert active_standard_payload(data) is data["source_payloads"]["LIMS"]
    database.get_lims_instance_payload.assert_not_called()


def test_legacy_report_without_lims_source_binding_fails_clearly() -> None:
    with pytest.raises(LimsSourceError, match="旧报告未保存 LIMS 项目绑定"):
        refresh_report_lims_payload(MagicMock(), MagicMock(), {
            "source_payloads": {"LIMS": {"referenceStandards": []}},
        })


def test_latest_lims_allows_an_empty_structured_unit(monkeypatch) -> None:
    database = _database()
    instance = {
        "instanceId": "instance-1",
        "projectId": "project-1",
        "unitCounts": {"Standard": 1},
        "rawStructured": [],
        "richTexts": [],
    }
    _mock_latest_query(monkeypatch, [instance])
    monkeypatch.setattr(
        "backend.app.services.report_lims_refresh.list_system_field_groups", lambda _database: [],
    )

    recognition = recognize_latest_lims(database, MagicMock(), "project-1", ["instance-1"])

    assert recognition["payload"]["referenceStandards"] == []


def test_latest_lims_fails_when_selected_instance_no_longer_exists(monkeypatch) -> None:
    database = _database()
    _mock_latest_query(monkeypatch, [{"instanceId": "instance-2", "rawStructured": [], "richTexts": []}])

    with pytest.raises(LimsSourceError, match="已不存在实验记录：instance-1"):
        recognize_latest_lims(database, MagicMock(), "project-1", ["instance-1"])


def test_multiple_payloads_require_an_explicit_active_source() -> None:
    with pytest.raises(ValueError, match="存在多个数据源"):
        active_standard_payload({"source_payloads": {"EXCEL": {}, "LIMS": {}}})
