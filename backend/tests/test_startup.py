import asyncio

import pytest
from fastapi import HTTPException

from backend.app import main


def test_lifespan_only_yields_without_initialization(monkeypatch):
    """Application startup must not mutate files, schema, auth or report ownership."""
    calls = []
    monkeypatch.setattr(type(main.settings), "ensure_directories", lambda _settings: calls.append("directories"))
    monkeypatch.setattr(main.database, "initialize", lambda: calls.append("database"))
    monkeypatch.setattr(main.auth, "bootstrap", lambda: calls.append("auth"))

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())
    assert calls == []


def test_report_list_scope_enforces_cross_user_permission(monkeypatch):
    owner_filters = []
    monkeypatch.setattr(main.database, "list_reports", lambda owner_id=None: owner_filters.append(owner_id) or [])

    report_user = {"id": "reporter", "permissions": {"REPORT_EDIT"}}
    assert main.list_reports("mine", report_user) == []
    assert owner_filters == ["reporter"]

    with pytest.raises(HTTPException) as error:
        main.list_reports("all", report_user)
    assert error.value.status_code == 403
    assert owner_filters == ["reporter"]

    admin = {"id": "admin", "permissions": {"REPORT_ALL_VIEW"}}
    assert main.list_reports("all", admin) == []
    assert owner_filters == ["reporter", None]
