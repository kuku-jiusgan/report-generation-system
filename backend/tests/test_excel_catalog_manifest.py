from backend.tests.database_helpers import make_test_database
from backend.app.services.system_field_groups import (
    assign_field_to_group, list_system_field_groups, save_system_field_group,
)
from backend.app.services import excel_catalog_manifest


class FakeDatabase:
    def __init__(self) -> None:
        self.rules = [{
            "id": 17, "fieldCode": "uncategorized.field_128", "name": "人员",
            "sourceType": "EXCEL", "priority": 65,
            "config": {"sheet": "对照品配制", "required": True},
            "enabled": True, "transform": "TRIM",
        }]
        self.saved = []

    def get_lims_field(self, field_code: str) -> dict:
        return {"fieldCode": field_code, "cardinality": "MANY"}

    def list_system_field_rules(self, field_code: str = "") -> list[dict]:
        if field_code:
            return [rule for rule in self.rules if rule["fieldCode"] == field_code]
        return self.rules

    def save_system_field_rule(self, item: dict, rule_id: int | None = None) -> dict:
        self.saved.append((item, rule_id))
        self.rules = [item]
        return item


def test_apply_manifest_preserves_existing_database_excel_rule(monkeypatch) -> None:
    field_code = "uncategorized.field_128"
    manifest = {
        "groupCode": "staff", "fields": [{
            "code": field_code, "label": "人员A", "level": "",
            "config": {"rowStart": 1, "rowEnd": 1, "valueMode": "REPEAT_VALUE",
                       "repeatValueSource": {"literal": "技术员A"}},
        }],
        "defaults": {"mode": "REPEAT_BLOCK", "required": True},
    }
    group = {
        "groupCode": "staff", "cardinality": "MANY", "levels": [],
        "fields": [{"fieldCode": field_code, "label": "人员A", "jsonKey": "field_128",
                    "fieldPath": "field_128", "levelKey": ""}],
    }
    database = FakeDatabase()
    monkeypatch.setattr(excel_catalog_manifest, "list_system_field_groups", lambda _: [group])

    added_rules = excel_catalog_manifest.apply_manifest(database, manifest)

    assert added_rules == []
    assert database.saved == []
    assert database.rules[0]["config"] == {"sheet": "对照品配制", "required": True}


def test_apply_manifest_assigns_new_fields_to_nested_levels(tmp_path) -> None:
    database = make_test_database(tmp_path)
    save_system_field_group(database, {
        "groupCode": "results", "label": "结果", "cardinality": "MANY",
    })
    manifest = {
        "groupCode": "results", "defaults": {"mode": "REPEAT_BLOCK", "sheet": "结果"},
        "levels": [
            {"levelKey": "technicians", "kind": "ARRAY", "parentLevelKey": ""},
            {"levelKey": "injections", "kind": "ARRAY", "parentLevelKey": "technicians"},
        ],
        "fields": [
            {"code": "results.impurityName", "label": "杂质", "level": "", "config": {"rowStart": 1}},
            {"code": "results.technicianName", "label": "技术员", "level": "technicians", "config": {"rowStart": 2}},
            {"code": "results.area", "label": "峰面积", "level": "injections", "config": {"rowStart": 3}},
        ],
    }

    assert excel_catalog_manifest.apply_manifest(database, manifest) == [
        "results.impurityName", "results.technicianName", "results.area",
    ]
    group = next(item for item in list_system_field_groups(database) if item["groupCode"] == "results")
    fields = {item["fieldCode"]: item for item in group["fields"]}
    assert fields["results.technicianName"]["fieldPath"] == "technicians[*].technicianName"
    assert fields["results.area"]["fieldPath"] == "technicians[*].injections[*].area"
    assert database.get_lims_field("results.area")["legacyJsonPath"] == (
        "$.results[*].technicians[*].injections[*].area"
    )


def test_apply_manifest_retires_replaced_fields_without_deleting_catalog_records(tmp_path) -> None:
    database = make_test_database(tmp_path)
    save_system_field_group(database, {
        "groupCode": "results", "label": "结果", "cardinality": "MANY",
    })
    database.upsert_lims_field({
        "fieldCode": "old.personA", "label": "旧人员", "groupCode": "结果",
        "collectionCode": "results", "cardinality": "MANY", "jsonKey": "personA",
        "legacyJsonPath": "$.results[*].personA", "enabled": True,
    })
    assign_field_to_group(database, "results", "old.personA")
    manifest = {
        "groupCode": "results", "defaults": {"mode": "REPEAT_BLOCK"},
        "retireFields": ["old.personA"],
        "fields": [{"code": "results.name", "label": "人员", "level": "", "config": {}}],
    }

    excel_catalog_manifest.apply_manifest(database, manifest)

    group = next(item for item in list_system_field_groups(database) if item["groupCode"] == "results")
    assert [field["fieldCode"] for field in group["fields"]] == ["results.name"]
    assert database.get_lims_field("old.personA")["enabled"] is False
