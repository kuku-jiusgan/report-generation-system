import asyncio
import os
from pathlib import Path

import jwt
import pytest

from backend.app.admin_api import create_admin_router
from backend.app.auth import AuthManager
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.template_file_store import TemplateFileStore
from backend.tests.database_helpers import make_test_database


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeCallbackRequest:
    def __init__(self, body: dict):
        self._body = body
        self.headers = {}

    async def json(self) -> dict:
        return self._body


def test_template_versions_keep_independent_rule_snapshots(tmp_path: Path) -> None:
    database = make_test_database(tmp_path)
    database.initialize()
    repository = RuleAdminRepository(database, PROJECT_ROOT / "mapping" / "template-mapping.json")
    repository.seed()

    default_template = repository.list_templates()[0]
    default_version = repository.list_template_versions(default_template["id"])[0]
    original_title = repository.list_template_chapters()[0]["title"]

    second_template = repository.create_template({"code": "SECOND", "name": "第二套模板"})
    second_version = repository.list_template_versions(second_template["id"])[0]
    repository.activate_template_version(second_template["id"], second_version["id"])
    first_chapter = repository.list_template_chapters()[0]
    repository.update_template_chapter(first_chapter["id"], {"title": "第二套模板封面"})
    repository.save_active_workspace()

    repository.activate_template_version(default_template["id"], default_version["id"])
    assert repository.list_template_chapters()[0]["title"] == original_title

    repository.activate_template_version(second_template["id"], second_version["id"])
    assert repository.list_template_chapters()[0]["title"] == "第二套模板封面"

    third_version = repository.create_template_version(
        second_template["id"], second_version["id"], "第二套模板的新草稿"
    )
    repository.activate_template_version(second_template["id"], third_version["id"])
    repository.update_template_chapter(first_chapter["id"], {"title": "V2 独立封面"})
    repository.save_active_workspace()
    repository.activate_template_version(second_template["id"], second_version["id"])
    assert repository.list_template_chapters()[0]["title"] == "第二套模板封面"

    deleted = repository.delete_template(second_template["id"])
    assert deleted["id"] == second_template["id"]
    assert repository.active_workspace()["templateId"] == default_template["id"]
    try:
        repository.delete_template(default_template["id"])
    except ValueError as error:
        assert "至少需要保留一个" in str(error)
    else:
        raise AssertionError("最后一个模板不应允许删除")


def test_new_templates_get_independent_documents_from_initial_template(tmp_path: Path) -> None:
    initial_template = tmp_path / "templates" / "report-template.docx"
    initial_template.parent.mkdir(parents=True)
    initial_template.write_bytes((PROJECT_ROOT / "templates" / "report-template.docx").read_bytes())
    settings = Settings(
        data_dir=tmp_path / "data",
        template_path=initial_template,
        onlyoffice_jwt_secret="test-secret",
        public_base_url="http://127.0.0.1:8010",
    )
    settings.ensure_directories()
    database = Database(settings)
    database.initialize()
    repository = RuleAdminRepository(database, PROJECT_ROOT / "mapping" / "template-mapping.json")
    repository.seed()
    router = create_admin_router(repository, settings, AuthManager(database, settings))
    create_endpoint = next(
        route.endpoint
        for route in router.routes
        if route.path == "/api/v1/admin/templates" and "POST" in route.methods
    )
    config_endpoint = next(
        route.endpoint
        for route in router.routes
        if route.path == "/api/v1/admin/onlyoffice/config"
    )
    delete_endpoint = next(
        route.endpoint
        for route in router.routes
        if route.path == "/api/v1/admin/templates/{template_id}" and "DELETE" in route.methods
    )

    first = create_endpoint({"code": "DOC-A", "name": "文档 A"})
    second = create_endpoint({"code": "DOC-B", "name": "文档 B"})
    first_version = repository.list_template_versions(first["id"])[0]
    second_version = repository.list_template_versions(second["id"])[0]

    first_file = Path(first_version["templateFile"])
    second_file = Path(second_version["templateFile"])
    assert first_file != second_file
    assert first_file.read_bytes() == initial_template.read_bytes()
    assert second_file.read_bytes() == initial_template.read_bytes()

    repository.activate_template_version(first["id"], first_version["id"])
    config = config_endpoint()["config"]
    assert f"/template/file/{first_version['id']}" in config["document"]["url"]
    assert f"/onlyoffice/callback/{first_version['id']}" in config["editorConfig"]["callbackUrl"]
    plugin_url = config["editorConfig"]["plugins"]["pluginsData"][0]
    assert plugin_url.startswith(settings.onlyoffice_url)
    assert plugin_url.endswith("config.json?v=22")
    issued_key = config["document"]["key"]
    draft_file = Path(first_version["templateFile"])
    current_time = draft_file.stat().st_mtime_ns
    os.utime(draft_file, ns=(current_time + 1_000_000, current_time + 1_000_000))
    refreshed_config = config_endpoint()["config"]
    assert refreshed_config["document"]["key"] == issued_key
    assert not any("/onlyoffice/plugin/" in route.path for route in router.routes)
    assert not any(route.path.endswith("/onlyoffice/command") for route in router.routes)

    result = delete_endpoint(second["id"])
    assert result["deleted"] is True
    assert not second_file.exists()
    assert all(item["id"] != second["id"] for item in repository.list_templates())


def test_publish_freezes_artifact_and_opens_a_new_draft(tmp_path: Path, monkeypatch) -> None:
    initial_template = tmp_path / "templates" / "report-template.docx"
    initial_template.parent.mkdir(parents=True)
    initial_template.write_bytes((PROJECT_ROOT / "templates" / "report-template.docx").read_bytes())
    settings = Settings(
        data_dir=tmp_path / "data", template_path=initial_template,
        onlyoffice_url="http://127.0.0.1:8088", onlyoffice_jwt_secret="test-secret",
        public_base_url="http://127.0.0.1:8010",
    )
    settings.ensure_directories()
    database = Database(settings)
    database.initialize()
    repository = RuleAdminRepository(database, PROJECT_ROOT / "mapping" / "template-mapping.json")
    repository.seed()
    router = create_admin_router(repository, settings, AuthManager(database, settings))

    def compile_copy(source: Path, output: Path, *_args) -> dict:
        output.write_bytes(source.read_bytes())
        return {"valid": True, "errors": [], "warnings": []}

    monkeypatch.setattr("backend.app.admin_routes.publishing.compile_template", compile_copy)
    publish = next(route.endpoint for route in router.routes if route.path == "/api/v1/admin/publish")
    callback = next(
        route.endpoint for route in router.routes
        if route.path == "/api/v1/admin/onlyoffice/callback/{version_id}"
    )

    published = publish({"note": "发布测试"})
    artifact = Path(published["templateFile"])
    frozen_bytes = artifact.read_bytes()
    workspace = repository.active_workspace()
    assert published["status"] == "PUBLISHED"
    assert artifact.parent.parent.name == "published"
    assert workspace["versionStatus"] == "DRAFT"
    assert workspace["versionId"] != published["id"]
    assert Path(workspace["templateFile"]) != artifact

    Path(workspace["templateFile"]).write_bytes(b"changed draft")
    assert artifact.read_bytes() == frozen_bytes

    file_store = TemplateFileStore(repository, settings.template_path)
    with pytest.raises(ValueError, match="已发布模板不可进入编辑器"):
        file_store.ensure_version_draft(published["id"])

    legacy_path = file_store.draft_dir / "legacy-published.docx"
    legacy_path.write_bytes(frozen_bytes)
    repository.set_template_version_file(published["id"], str(legacy_path))
    assert file_store.migrate_legacy_published_versions() == 1
    migrated = repository.get_template_version(published["id"])
    assert Path(migrated["templateFile"]).parent.parent.name == "published"
    assert Path(migrated["templateFile"]).read_bytes() == frozen_bytes

    repository.create_template({"code": "SECOND", "name": "备用模板"})
    with pytest.raises(ValueError, match="包含已发布或历史版本"):
        repository.delete_template(published["templateId"])

    token = jwt.encode({"status": 2}, settings.onlyoffice_jwt_secret, algorithm="HS256")
    result = asyncio.run(callback(published["id"], FakeCallbackRequest({
        "status": 2, "url": f"{settings.onlyoffice_url}/published.docx",
        "key": "published-key", "token": token,
    })))
    assert result == {"error": 1}
    assert artifact.read_bytes() == frozen_bytes
