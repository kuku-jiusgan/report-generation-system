import json
import os
from pathlib import Path
from typing import Any

from ..config import get_settings


def _path() -> Path:
    return get_settings().data_dir / "ai-service.json"


def load_ai_service_config(include_secret: bool = False) -> dict[str, Any]:
    settings = get_settings()
    stored: dict[str, Any] = {}
    path = _path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            stored = {}
    api_key = str(stored.get("apiKey") or settings.ai_api_key)
    result = {
        "baseUrl": str(stored.get("baseUrl") or settings.ai_base_url),
        "model": str(stored.get("model") or settings.ai_model),
        "timeout": float(stored.get("timeout") or settings.ai_timeout),
        "apiKeyConfigured": bool(api_key),
        "apiKeyMasked": f"{api_key[:3]}***{api_key[-3:]}" if len(api_key) >= 8 else ("******" if api_key else ""),
    }
    if include_secret:
        result["apiKey"] = api_key
    return result


def save_ai_service_config(item: dict[str, Any]) -> dict[str, Any]:
    current = load_ai_service_config(True)
    api_key = str(item.get("apiKey") or current.get("apiKey") or "")
    payload = {
        "baseUrl": str(item.get("baseUrl") or "").strip().rstrip("/"),
        "apiKey": api_key, "model": str(item.get("model") or "").strip(),
        "timeout": max(5.0, min(float(item.get("timeout") or 60), 300.0)),
    }
    path = _path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
    return load_ai_service_config(False)
