from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services import report_template_runtime
from backend.app.services.runtime_version_repository import RuntimeVersionRepositoryMixin


def test_selected_template_lookup_is_independent_of_workspace():
    repository = RuntimeVersionRepositoryMixin()
    repository.database = MagicMock()
    connection = repository.database.connect.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = {
        "template_id": "selected", "template_code": "CODE", "template_name": "所选模板",
        "version_id": "published", "version_no": 2, "snapshot": '{"tableRules": []}',
        "template_file": "published.docx",
    }
    result = repository.active_runtime_template("selected")
    query, parameters = connection.execute.call_args.args
    assert "t.id=%s" in query
    assert "admin_template_workspace" not in query
    assert parameters == ("selected",)
    assert result["templateId"] == "selected"


def test_report_template_lookup_is_pinned_to_exact_published_or_archived_version():
    repository = RuntimeVersionRepositoryMixin()
    repository.database = MagicMock()
    connection = repository.database.connect.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = {
        "template_id": "selected", "template_code": "CODE", "template_name": "所选模板",
        "version_id": "report-version", "version_no": 1, "snapshot": '{"tableRules": []}',
        "template_file": "published-v1.docx",
    }

    result = repository.active_runtime_template("selected", "report-version")

    query, parameters = connection.execute.call_args.args
    assert "v.id=%s" in query
    assert "v.status IN ('PUBLISHED','ARCHIVED')" in query
    assert parameters == ("selected", "report-version")
    assert result["versionId"] == "report-version"


def test_unavailable_selected_template_is_rejected():
    repository = RuntimeVersionRepositoryMixin()
    repository.database = MagicMock()
    repository.database.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
    with pytest.raises(ValueError, match="没有已发布版本"):
        repository.active_runtime_template("missing")


def test_selected_template_uses_its_own_rules(tmp_path: Path, monkeypatch):
    source = tmp_path / "selected.docx"
    source.write_bytes(b"selected template")
    snapshot = {"mappings": [{"id": "selected-field"}], "tableRules": [{"id": "selected-table"}]}
    repository = MagicMock()
    repository.active_runtime_template.return_value = {
        "templateId": "selected", "templateName": "所选模板", "templateCode": "CODE",
        "versionId": "published", "versionNo": 2, "snapshot": snapshot,
        "templateFile": str(source),
    }
    compiler = MagicMock(return_value={"valid": True})
    monkeypatch.setattr(report_template_runtime, "compile_template", compiler)
    settings = SimpleNamespace(template_path=tmp_path / "base.docx")
    _, mappings, tables, metadata = report_template_runtime.resolve_runtime_template(
        settings, repository, lambda value: value["mappings"], "selected",
    )
    assert mappings == snapshot["mappings"]
    assert tables == snapshot["tableRules"]
    assert metadata["template_id"] == "selected"
    repository.active_runtime_template.assert_called_with("selected", None)
    repository.list_table_rules.assert_not_called()
    repository.active_runtime_rules.assert_not_called()
    assert compiler.call_args.args[0] == source

    source.unlink()
    with pytest.raises(RuntimeError, match="已发布文件缺失"):
        report_template_runtime.resolve_runtime_template(
            settings, repository, lambda value: value["mappings"], "selected",
        )
