from backend.app.services.system_field_group_assembler import apply_group_contracts


def test_many_group_preserves_record_pairing_and_evidence():
    payload = {"samples": [
        {"sampleName": "样品A", "batchNo": "A01", "evidence": {"row": 1}},
        {"sampleName": "样品B", "batchNo": "B02", "evidence": {"row": 2}},
    ]}
    groups = [{
        "groupCode": "samples", "cardinality": "MANY", "enabled": True,
        "itemKey": "batchNo", "fields": [
            {"fieldCode": "samples.sampleName", "fieldPath": "sampleName"},
            {"fieldCode": "samples.batchNo", "fieldPath": "batchNo"},
        ],
    }]

    result = apply_group_contracts(payload, groups)

    assert result["samples"][0]["batchNo"] == "A01"
    assert result["samples"][1]["sampleName"] == "样品B"
    assert result["samples"][1]["evidence"] == {"row": 2}


def test_one_group_converts_legacy_single_item_list():
    payload = {"project": [{"name": "项目A"}]}
    groups = [{
        "groupCode": "project", "cardinality": "ONE", "enabled": True,
        "fields": [{"fieldCode": "project.name", "fieldPath": "name"}],
    }]

    assert apply_group_contracts(payload, groups)["project"] == {"name": "项目A"}
