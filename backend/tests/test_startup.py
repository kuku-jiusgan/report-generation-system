import asyncio

from backend.app import main


def test_lifespan_only_yields_without_initialization(monkeypatch):
    """Application startup must not mutate files, schema, auth or report ownership."""
    calls = []
    monkeypatch.setattr(type(main.settings), "ensure_directories", lambda _settings: calls.append("directories"))
    monkeypatch.setattr(main.database, "initialize", lambda: calls.append("database"))
    monkeypatch.setattr(main.auth, "bootstrap", lambda: calls.append("auth"))
    monkeypatch.setattr(main.database, "backfill_report_ownership", lambda _: calls.append("ownership"))

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())
    assert calls == []
