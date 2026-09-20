from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app import main
from backend.app.schemas import CreateReportRequest


def configure_creation(monkeypatch: pytest.MonkeyPatch, reports_dir: Path) -> tuple[Mock, dict]:
    database = Mock()
    stored: dict = {}

    def create_report(item: dict) -> dict:
        stored.update(item)
        stored.update(report_number="R202609190001", output_name=None)
        return dict(stored)

    def update_report(_: str, **changes) -> dict:
        stored.update(changes)
        return dict(stored)

    database.create_report.side_effect = create_report
    database.update_report.side_effect = update_report
    database.list_lims_fields.return_value = []
    database.list_system_field_rules.return_value = []
    monkeypatch.setattr(main, "database", database)
    monkeypatch.setattr(main, "settings", SimpleNamespace(reports_dir=reports_dir, api_prefix="/api/v1"))
    monkeypatch.setattr(main, "runtime_template_and_mappings", lambda *_: (None, [], [], {
        "template_id": "template-1", "template_name": "验证模板",
    }))
    monkeypatch.setattr(main, "list_system_field_groups", lambda *_: [])
    monkeypatch.setattr(main, "refresh_protocol_source", lambda *_: None)
    monkeypatch.setattr(main, "resolve_system_fields", lambda *_: None)
    monkeypatch.setattr(main, "report_response", lambda item: item)
    return database, stored


def test_create_report_generates_working_file_before_success(tmp_path: Path, monkeypatch) -> None:
    database, _ = configure_creation(monkeypatch, tmp_path)

    def write_working_file(item: dict, *_args, **_kwargs) -> str:
        name = f"report-{item['id']}-working.docx"
        (tmp_path / name).write_bytes(b"generated")
        return name

    render = Mock(side_effect=write_working_file)
    monkeypatch.setattr(main, "render_report_word", render)

    result = main.create_report(
        CreateReportRequest(title="  正确的报告名称  ", template_id="template-1"),
        {"id": "user-1"},
    )

    assert result["title"] == "正确的报告名称"
    assert result["status"] == "EDITING"
    assert result["output_name"] == f"report-{result['id']}-working.docx"
    assert (tmp_path / result["output_name"]).is_file()
    assert database.update_report.call_args.kwargs["resolved_data"] == result["resolved_data"]
    assert database.create_version.call_args.args[2] == "初始版本"
    assert render.call_args.kwargs == {"phase": "创建报告", "actor": "user-1"}


def test_lims_workflow_explicitly_defers_initial_word_generation(tmp_path: Path, monkeypatch) -> None:
    database, _ = configure_creation(monkeypatch, tmp_path)
    render = Mock()
    monkeypatch.setattr(main, "render_report_word", render)

    result = main.create_report(
        CreateReportRequest(title="LIMS 报告", defer_word_generation=True),
        {"id": "user-1"},
    )

    assert result["status"] == "DATA_REVIEW"
    assert result["output_name"] is None
    render.assert_not_called()
    database.update_report.assert_not_called()
    database.create_version.assert_called_once()


def test_create_report_removes_draft_and_working_file_when_state_update_fails(
    tmp_path: Path, monkeypatch,
) -> None:
    database, _ = configure_creation(monkeypatch, tmp_path)
    database.update_report.side_effect = None
    database.update_report.return_value = None

    def render(item: dict, *_args, **_kwargs) -> str:
        name = f"report-{item['id']}-working.docx"
        (tmp_path / name).write_bytes(b"generated")
        return name

    monkeypatch.setattr(main, "render_report_word", render)

    with pytest.raises(HTTPException, match="报告状态更新失败"):
        main.create_report(CreateReportRequest(title="失败报告"), {"id": "user-1"})

    report_id = database.create_report.call_args.args[0]["id"]
    database.delete_report.assert_called_once_with(report_id)
    assert not (tmp_path / f"report-{report_id}-working.docx").exists()


@pytest.mark.parametrize("payload", [{}, {"title": "   "}, {"title": "x" * 201}])
def test_create_report_requires_explicit_valid_title(payload: dict) -> None:
    with pytest.raises(ValidationError):
        CreateReportRequest(**payload)
