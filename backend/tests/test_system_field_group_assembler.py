import pytest

from backend.app.services.system_field_group_assembler import apply_group_contracts
from backend.app.services.system_field_group_levels import structure_preview


def _field(json_key: str, level_key: str, order_no: int) -> dict:
    return {"fieldCode": f"systemSuitability.{json_key}", "label": json_key,
            "jsonKey": json_key, "levelKey": level_key, "orderNo": order_no}


SUITABILITY_GROUP = {
    "groupCode": "systemSuitability", "cardinality": "MANY", "enabled": True,
    "levels": [{"levelKey": "summary", "label": "聚合统计", "kind": "OBJECT", "orderNo": 0},
               {"levelKey": "injections", "label": "明细列表", "kind": "ARRAY", "orderNo": 1}],
    "fields": [_field("impurityName", "", 0), _field("solutionName", "injections", 1),
               _field("retentionTime", "injections", 3), _field("peakArea", "injections", 4),
               _field("retentionTimeRsd", "summary", 5), _field("peakAreaRsd", "summary", 6)],
}
# 来源解析写出来的原始顺序：键的先后取决于提取顺序，不是标准字段目录的顺序。
UNORDERED_RECORD = {
    "summary": {"peakAreaRsd": 1.4, "retentionTimeRsd": 0.1},
    "injections": [{"peakArea": 1593245, "solutionName": "系统适用性溶液1", "retentionTime": 4.21}],
    "impurityName": "3-吡啶磺酸甲酯",
}


def test_many_group_preserves_record_pairing_and_evidence():
    payload = {"samples": [
        {"sampleName": "样品A", "batchNo": "A01", "evidence": {"row": 1}},
        {"sampleName": "样品B", "batchNo": "B02", "evidence": {"row": 2}},
    ]}
    groups = [{
        "groupCode": "samples", "cardinality": "MANY", "enabled": True,
        "itemKey": "batchNo", "levels": [], "fields": [
            {"fieldCode": "samples.sampleName", "jsonKey": "sampleName", "levelKey": "", "orderNo": 0},
            {"fieldCode": "samples.batchNo", "jsonKey": "batchNo", "levelKey": "", "orderNo": 1},
        ],
    }]

    result = apply_group_contracts(payload, groups)

    assert result["samples"][0]["batchNo"] == "A01"
    assert result["samples"][1]["sampleName"] == "样品B"
    assert result["samples"][1]["evidence"] == {"row": 2}


def test_one_group_rejects_list_payload():
    payload = {"project": [{"name": "项目A"}]}
    groups = [{
        "groupCode": "project", "cardinality": "ONE", "enabled": True, "levels": [],
        "fields": [{"fieldCode": "project.name", "jsonKey": "name", "levelKey": "", "orderNo": 0}],
    }]

    with pytest.raises(ValueError, match="单值数据必须是对象"):
        apply_group_contracts(payload, groups)


def test_record_key_order_follows_the_catalog_structure():
    payload = {"systemSuitability": [UNORDERED_RECORD]}

    record = apply_group_contracts(payload, [SUITABILITY_GROUP])["systemSuitability"][0]

    preview = structure_preview(SUITABILITY_GROUP["levels"], SUITABILITY_GROUP["fields"])
    assert list(record) == list(preview) == ["impurityName", "summary", "injections"]
    assert list(record["injections"][0]) == list(preview["injections"][0])
    assert list(record["summary"]) == list(preview["summary"])


def test_missing_configured_data_list_is_skipped_for_this_source():
    group = {"groupCode": "accuracySolutions", "label": "准确度溶液", "cardinality": "MANY",
             "enabled": True, "itemPath": "$.accuracySolutions", "payloadKey": "accuracySolutions",
             "levels": [], "fields": []}

    assert apply_group_contracts({}, [group]) == {}
