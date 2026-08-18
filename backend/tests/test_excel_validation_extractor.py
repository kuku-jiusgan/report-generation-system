from pathlib import Path

from backend.app.services.excel_validation_extractor import ValidationWorkbookReader, extract_validation_workbook


WORKBOOK = Path(__file__).parents[2] / "excel" / "文霞-标准计算表-动态-V49-解锁版.xlsm"


def test_extracts_vba_fixed_blocks_without_raw_impurity_sheets() -> None:
    payload = extract_validation_workbook(WORKBOOK)

    assert payload["_meta"]["impurityNames"] == ["杂质D", "杂质A2"]
    assert len(payload["systemSuitability"]) == 12
    assert payload["systemSuitability"][0]["retentionTime"] == 8.21
    assert payload["systemSuitability"][6]["impurityName"] == "杂质A2"
    assert payload["systemSuitability"][0]["_evidence"]["cell"] == "A3:C3"
    assert payload["systemSuitability"][6]["_evidence"]["cell"] == "D3:F3"
    assert len(payload["specificity"]) == 8
    assert payload["limit"][0]["field4"] == 25
    assert "杂质D" not in payload["validationResults"]["sheets"]


def test_keeps_missing_cached_values_as_warnings() -> None:
    payload = extract_validation_workbook(WORKBOOK)

    assert any("首页!B3" in warning for warning in payload["_meta"]["warnings"])


def test_validation_reader_uses_excel_display_values() -> None:
    reader = ValidationWorkbookReader(WORKBOOK)

    assert reader.cell("重复性跟中间精密度", "I12") == 107.527

    payload = reader.extract()
    matrix = payload["validationResults"]["sheets"]["重复性跟中间精密度"]
    assert matrix[11][8] == 107.527
