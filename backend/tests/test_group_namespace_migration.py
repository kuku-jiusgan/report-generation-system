import pytest

from backend.app.services.group_namespace_migration import migrate_standard_payload


def test_standard_payload_uses_jiancexian_as_the_only_collection_code() -> None:
    payload = {
        "lod": [{"name": "杂质A"}],
        "validationSummary": [{"validationItemCode": "lod", "field1": "检测限"}],
    }

    assert migrate_standard_payload(payload)
    assert "lod" not in payload
    assert payload["jiancexian"] == [{"name": "杂质A"}]
    assert payload["validationSummary"][0]["validationItemCode"] == "jiancexian"


def test_conflicting_detection_limit_names_fail_fast() -> None:
    with pytest.raises(ValueError, match="内容不一致"):
        migrate_standard_payload({"lod": [{"name": "A"}], "jiancexian": [{"name": "B"}]})
