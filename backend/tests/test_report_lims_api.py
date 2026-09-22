import pytest

from backend.app.report_lims_api import _standard_value


def _field(code: str, key: str, path: str) -> dict:
    return {
        "fieldCode": code, "collectionCode": "samples", "jsonKey": key,
        "legacyJsonPath": path, "enabled": True,
    }


def test_report_summary_reads_sample_fields_from_configured_array_level() -> None:
    payload = {"samples": [{
        "batchNo": "B-01",
        "injections": [{"sampleName": "样品甲", "clientName": "委托方甲"}],
    }]}
    fields = [
        _field("samples.sampleName", "sampleName", "$.samples[*].injections[*].sampleName"),
        _field("samples.field4", "clientName", "$.samples[*].injections[*].clientName"),
    ]

    assert _standard_value(payload, fields, "samples", "sampleName") == "样品甲"
    assert _standard_value(payload, fields, "samples", "clientName") == "委托方甲"


def test_report_summary_rejects_an_ambiguous_standard_field_contract() -> None:
    fields = [
        _field("samples.sampleName", "sampleName", "$.samples[*].sampleName"),
        _field("samples.duplicateName", "sampleName", "$.samples[*].injections[*].sampleName"),
    ]

    with pytest.raises(ValueError, match="必须且只能配置一次"):
        _standard_value({"samples": []}, fields, "samples", "sampleName")
