from unittest.mock import patch

from app.services.lims_normalizer import COLLECTION_ORDER, merge_instances


def normalized(instance_id: str, collection: str, record: dict) -> dict:
    return {
        "project": {"id": "P1"},
        "document": {},
        "approval": [],
        "instances": [{"instanceId": instance_id, "title": instance_id}],
        "unmatched": [],
        **{name: [record] if name == collection else [] for name in COLLECTION_ORDER},
    }


def raw(instance_id: str) -> dict:
    return {"instanceId": instance_id, "projectId": "P1"}


def test_identical_business_records_with_different_source_ids_are_deduplicated() -> None:
    records = [
        normalized("E1", "columns", {
            "serialNo": "C-01", "name": "C18", "manufacturer": "Vendor",
            "specification": "4.6x250mm", "sourceRecordId": "ROW-1",
        }),
        normalized("E2", "columns", {
            "serialNo": "C-01", "name": "C18", "manufacturer": "Vendor",
            "specification": "4.6x250mm", "sourceRecordId": "ROW-2",
        }),
    ]
    with patch("app.services.lims_normalizer.normalize_instance", side_effect=records):
        result = merge_instances([raw("E1"), raw("E2")])

    assert result["duplicateCount"] == 1
    assert result["conflicts"] == []
    assert len(result["payload"]["columns"]) == 1


def test_same_name_with_different_business_value_remains_a_conflict() -> None:
    records = [
        normalized("E1", "reagents", {
            "name": "Reagent", "batchNo": "B1", "expiryDate": "2026-05-01",
            "sourceRecordId": "ROW-1",
        }),
        normalized("E2", "reagents", {
            "name": "Reagent", "batchNo": "B1", "expiryDate": "2026-06-01",
            "sourceRecordId": "ROW-2",
        }),
    ]
    with patch("app.services.lims_normalizer.normalize_instance", side_effect=records):
        result = merge_instances([raw("E1"), raw("E2")])

    assert result["duplicateCount"] == 0
    assert result["unresolvedConflictCount"] == 1
    assert len(result["conflicts"][0]["options"]) == 2
    assert all("sourceRecordId" not in option["value"] for option in result["conflicts"][0]["options"])


def test_same_reagent_batch_with_different_stock_numbers_are_separate_records() -> None:
    records = [
        normalized("E1", "reagents", {
            "name": "Reagent", "batchNo": "B1", "stockNo": "SJ001",
            "expiryDate": "2026-05-01", "sourceRecordId": "ROW-1",
        }),
        normalized("E2", "reagents", {
            "name": "Reagent", "batchNo": "B1", "stockNo": "SJ002",
            "expiryDate": "2026-06-01", "sourceRecordId": "ROW-2",
        }),
    ]
    with patch("app.services.lims_normalizer.normalize_instance", side_effect=records):
        result = merge_instances([raw("E1"), raw("E2")])

    assert result["duplicateCount"] == 0
    assert result["conflicts"] == []
    assert [item["stockNo"] for item in result["payload"]["reagents"]] == ["SJ001", "SJ002"]


def test_validation_summary_uses_stable_code_across_experiments() -> None:
    record = {
        "validationItemCode": "systemSuitability", "field1": "系统适用性",
        "acceptanceCriteria": "峰面积RSD≤20%", "conclusion": "",
    }
    records = [normalized("E1", "validationSummary", record),
               normalized("E2", "validationSummary", record)]

    result = merge_instances(records, normalized=True)

    assert result["duplicateCount"] == 1
    assert result["conflicts"] == []
    assert len(result["payload"]["validationSummary"]) == 1


def test_validation_summary_is_sorted_by_stable_business_code() -> None:
    records = [
        normalized("E1", "validationSummary", {
            "validationItemCode": "accuracy", "field1": "准确度", "acceptanceCriteria": "A",
        }),
        normalized("E2", "validationSummary", {
            "validationItemCode": "specificity", "field1": "专属性", "acceptanceCriteria": "B",
        }),
    ]

    result = merge_instances(records, normalized=True)

    assert [item["validationItemCode"] for item in result["payload"]["validationSummary"]] == [
        "specificity", "accuracy",
    ]
