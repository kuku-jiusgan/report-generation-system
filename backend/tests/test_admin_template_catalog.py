from pathlib import Path

from backend.app.admin_api import create_admin_router
from backend.app.auth import AuthManager
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.services.rule_admin import RuleAdminRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_template_versions_keep_independent_rule_snapshots(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.db")
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
    database = Database(settings.database_path)
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
    assert plugin_url.endswith("config.json?v=18")
    assert not any("/onlyoffice/plugin/" in route.path for route in router.routes)
    assert not any(route.path.endswith("/onlyoffice/command") for route in router.routes)

    result = delete_endpoint(second["id"])
    assert result["deleted"] is True
    assert not second_file.exists()
    assert all(item["id"] != second["id"] for item in repository.list_templates())
