import pytest

from backend.app.services.group_namespace_migration import migrate_standard_payload
from backend.app.services.lims_normalizer import COLLECTION_ORDER


def test_standard_payload_uses_jiancexian_as_the_only_collection_code() -> None:
    payload = {
        "lod": [{"name": "杂质A"}],
        "solutions": [{"name": "检测限溶液", "validationCode": "lod"}],
        "validationSummary": [{"validationItemCode": "lod", "field1": "检测限"}],
    }

    assert migrate_standard_payload(payload)
    assert "lod" not in payload
    assert payload["jiancexian"] == [{"name": "杂质A"}]
    assert payload["solutions"][0]["validationCode"] == "jiancexian"
    assert payload["validationSummary"][0]["validationItemCode"] == "jiancexian"
    assert "jiancexian" in COLLECTION_ORDER
    assert "lod" not in COLLECTION_ORDER


def test_conflicting_detection_limit_names_fail_fast() -> None:
    with pytest.raises(ValueError, match="内容不一致"):
        migrate_standard_payload({"lod": [{"name": "A"}], "jiancexian": [{"name": "B"}]})
