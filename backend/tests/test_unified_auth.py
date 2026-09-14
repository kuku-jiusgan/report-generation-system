import copy
import hashlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.app.auth import AuthManager, REPORT_SESSION_COOKIE, create_auth_router


class AuthDatabaseStub:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.sessions: dict[str, str] = {}
        self.permissions = {
            "SUPER_ADMIN": {"ADMIN_ACCESS", "RULES_MANAGE"},
            "REPORT_USER": {"REPORT_EDIT"},
        }

    def add_user(self, user: dict) -> None:
        self.users[user["id"]] = user

    def get_user(self, user_id: str) -> dict | None:
        user = self.users.get(user_id)
        return copy.deepcopy(user) if user else None

    def get_user_by_username(self, username: str) -> dict | None:
        return next((copy.deepcopy(user) for user in self.users.values()
                     if user["username"].lower() == username.lower()), None)

    def update_user(self, user_id: str, **changes: object) -> dict:
        self.users[user_id].update(changes)
        return copy.deepcopy(self.users[user_id])

    def create_session(self, token_hash: str, user_id: str, _: str) -> None:
        self.sessions[token_hash] = user_id

    def get_session_user(self, token_hash: str) -> dict | None:
        user_id = self.sessions.get(token_hash)
        return self.get_user(user_id) if user_id else None

    def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    def role_permissions(self, role_code: str) -> set[str]:
        return set(self.permissions[role_code])


def create_auth() -> tuple[AuthManager, AuthDatabaseStub]:
    settings = SimpleNamespace(api_prefix="/api/v1", session_hours=8, secure_cookies=False)
    database = AuthDatabaseStub()
    auth = AuthManager(database, settings)
    for user_id, username, role_code in (
        ("admin", "administrator", "SUPER_ADMIN"),
        ("reporter", "reporter", "REPORT_USER"),
    ):
        database.add_user({
            "id": user_id,
            "username": username,
            "display_name": username,
            "password_hash": auth.hash_password("Password@123"),
            "role_code": role_code,
            "enabled": 1,
            "must_change_password": 0,
        })
    return auth, database


def test_login_uses_single_application_session() -> None:
    auth, _ = create_auth()
    app = FastAPI()
    app.include_router(create_auth_router(auth))

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={
            "username": "reporter",
            "password": "Password@123",
        })
        assert response.status_code == 200
        assert response.json()["username"] == "reporter"
        assert REPORT_SESSION_COOKIE in response.cookies
        assert "report_admin_session" not in response.cookies
        assert client.get("/api/v1/auth/me").json()["username"] == "reporter"


def test_admin_guard_uses_application_session_and_enforces_module_permissions() -> None:
    auth, database = create_auth()
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/admin/overview", "headers": []})

    admin_token, _ = auth.issue_session("admin")
    assert auth.admin_route_guard(request, admin_token)["id"] == "admin"

    report_token, _ = auth.issue_session("reporter")
    with pytest.raises(HTTPException) as error:
        auth.admin_route_guard(request, report_token)
    assert error.value.status_code == 403
    assert hashlib.sha256(report_token.encode()).hexdigest() in database.sessions
