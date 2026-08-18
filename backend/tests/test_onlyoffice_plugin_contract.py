import json
from pathlib import Path

from app.auth import AuthManager
from app.config import Settings
from app.database import Database
from app.onlyoffice_bridge_api import create_onlyoffice_bridge_router


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = PROJECT_ROOT / "deploy" / "onlyoffice-plugin"
PLUGIN_SCRIPT = PROJECT_ROOT / "frontend" / "public" / "onlyoffice-template-link" / "link.js"


def test_installed_plugin_manifest_matches_protocol_release() -> None:
    config = json.loads((PLUGIN_DIR / "config.json").read_text(encoding="utf-8"))
    index = (PLUGIN_DIR / "index.html").read_text(encoding="utf-8")
    assert config["version"] == "1.0.15"
    assert config["guid"] == "asc.{B75A5F24-8D2C-4E91-A763-6C98B8B80A15}"
    assert "link.js?v=18" in index
    assert config["serviceUrl"].endswith("/api/v1/onlyoffice/plugin-bridge")


def test_plugin_uses_bidirectional_protocol_without_remote_polling() -> None:
    script = PLUGIN_SCRIPT.read_text(encoding="utf-8")
    assert "protocolVersion: 3" in script
    assert "'select', 'bind', 'unbind'" in script
    assert "hostPort.postMessage(message)" in script
    assert "pollRemoteCommand" not in script
    assert "/api/v1/admin/onlyoffice/command" not in script
    assert "pollServerCommand" in script
    assert "plugin-command-received" in script
    assert "plugin-bind-selection-read" in script


def test_binding_does_not_remove_the_previous_control_before_commit() -> None:
    script = PLUGIN_SCRIPT.read_text(encoding="utf-8")
    bind_body = script.split("function bindSelection", 1)[1].split("function unbindSelection", 1)[0]
    assert "RemoveContentControl" not in bind_body


def test_command_relay_returns_only_newer_commands(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", template_path=tmp_path / "template.docx")
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    router = create_onlyoffice_bridge_router(settings, AuthManager(database, settings))
    submit = next(route.endpoint for route in router.routes if route.path.endswith("/{channel_id}") and "POST" in route.methods)
    poll = next(route.endpoint for route in router.routes if route.path.endswith("/{channel_id}") and "GET" in route.methods)
    list_trace = next(route.endpoint for route in router.routes if route.path.endswith("/{channel_id}/trace") and "GET" in route.methods)
    command = {"source": "report-template-host", "type": "select", "nonce": 42, "tag": "sample.name"}
    assert submit("channel-a", command, {}) == {"accepted": True}
    assert poll("channel-a", 0) == command
    assert poll("channel-a", 42) is None
    assert [event["stage"] for event in list_trace("channel-a", {})] == [
        "host-submit", "plugin-poll-deliver",
    ]
