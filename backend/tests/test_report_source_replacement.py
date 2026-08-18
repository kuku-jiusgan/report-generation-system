from backend.app.services.report_source_replacement import replace_report_source


def test_replacing_excel_preserves_other_sources() -> None:
    data = {"source_payloads": {"LIMS": {"sample": "A"}, "EXCEL": {"old": True}}, "warnings": []}
    source = {"id": "new", "file_name": "new.xlsm", "sha256": "abc",
              "payload": {"project": {"name": "新项目"}}, "warnings": ["缓存缺失"]}

    result = replace_report_source(data, source, "EXCEL", "/api/v1")

    assert result["source_payloads"]["LIMS"] == {"sample": "A"}
    assert result["source_payloads"]["EXCEL"] == source["payload"]
    assert result["project_name"] == "新项目"


def test_replacing_pdf_removes_old_pdf_values_only() -> None:
    data = {
        "source_payloads": {"LIMS": {"sample": "A"}},
        "original_values": {"old.pdf": "旧值", "manual": "保留"},
        "field_sources": {"old.pdf": {"type": "PDF"}, "manual": {"type": "MANUAL"}},
    }
    source = {"id": "new", "file_name": "new.pdf", "sha256": "abc", "warnings": [],
              "extracted_fields": [{"field_code": "new.pdf", "value": "新值", "source": {"type": "PDF"}}]}

    result = replace_report_source(data, source, "PDF", "/api/v1")

    assert result["original_values"] == {"manual": "保留", "new.pdf": "新值"}
    assert result["source_payloads"]["LIMS"] == {"sample": "A"}
