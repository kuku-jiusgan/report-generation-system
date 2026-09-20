import json
from types import SimpleNamespace

from backend.app.services import ai_service_config


def test_save_preserves_eighty_thousand_output_tokens(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "ai-service.json"
    settings = SimpleNamespace(
        ai_api_key="", ai_base_url="", ai_model="", ai_timeout=60,
        ai_max_tokens=800, ai_thinking_enabled=False,
    )
    monkeypatch.setattr(ai_service_config, "get_settings", lambda: settings)
    monkeypatch.setattr(ai_service_config, "_path", lambda: config_path)

    saved = ai_service_config.save_ai_service_config({
        "baseUrl": "https://example.test", "apiKey": "key", "model": "model",
        "timeout": 60, "maxTokens": 80_000, "thinkingEnabled": True,
    })

    assert saved["maxTokens"] == 80_000
    assert json.loads(config_path.read_text(encoding="utf-8"))["maxTokens"] == 80_000
