import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .config import Settings
from .database import Database, now_iso


REPORT_SESSION_COOKIE = "report_user_session"
logger = logging.getLogger(__name__)
PERMISSIONS = {
    "ADMIN_ACCESS": "访问系统管理功能",
    "RULES_MANAGE": "管理报告模板与规则",
    "LIMS_FIELDS_MANAGE": "管理 LIMS 标准字段",
    "USERS_MANAGE": "管理用户",
    "PERMISSIONS_MANAGE": "管理角色权限",
    "REPORT_HISTORY_VIEW": "查看全部报告生成历史",
    "REPORT_HISTORY_DOWNLOAD": "下载历史报告文件",
    "REPORT_CREATE": "创建报告",
    "REPORT_EDIT": "编辑本人报告",
    "REPORT_GENERATE": "生成本人报告",
    "REPORT_DOWNLOAD": "下载本人报告",
    "REPORT_ALL_VIEW": "只读查看全部用户报告",
}

ROLE_DEFINITIONS = [
    {"code": "SUPER_ADMIN", "name": "超级管理员", "description": "系统最高管理权限", "immutable": True},
    {"code": "SYSTEM_ADMIN", "name": "系统管理员", "description": "规则、用户及历史管理"},
    {"code": "REPORT_USER", "name": "报告用户", "description": "创建和生成本人报告"},
]

DEFAULT_ROLE_PERMISSIONS = {
    "SUPER_ADMIN": set(PERMISSIONS),
    "SYSTEM_ADMIN": {
        "ADMIN_ACCESS", "RULES_MANAGE", "LIMS_FIELDS_MANAGE", "USERS_MANAGE",
        "REPORT_HISTORY_VIEW", "REPORT_HISTORY_DOWNLOAD", "REPORT_ALL_VIEW",
    },
    "REPORT_USER": {"REPORT_CREATE", "REPORT_EDIT", "REPORT_GENERATE", "REPORT_DOWNLOAD"},
}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


class AuthManager:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings
        self._permission_migration_checked = False

    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        iterations = 600_000
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"

    @staticmethod
    def verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt, expected = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
            ).hex()
            return hmac.compare_digest(actual, expected)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def public_user(user: dict[str, Any], permissions: set[str]) -> dict[str, Any]:
        return {
            "id": user["id"], "username": user["username"], "displayName": user["display_name"],
            "roleCode": user["role_code"], "enabled": bool(user["enabled"]),
            "mustChangePassword": bool(user["must_change_password"]),
            "permissions": sorted(permissions), "createdAt": user.get("created_at"),
            "updatedAt": user.get("updated_at"), "lastLoginAt": user.get("last_login_at"),
        }

    def bootstrap(self) -> str | None:
        self.database.seed_roles(ROLE_DEFINITIONS, DEFAULT_ROLE_PERMISSIONS)
        self._migrate_report_all_view_permission()
        if self.database.count_users():
            users = self.database.list_users()
            owner = next((user for user in users if user["role_code"] == "SUPER_ADMIN"), users[0])
            return str(owner["id"])
        username = self.settings.bootstrap_admin_username.strip()
        password = self.settings.bootstrap_admin_password
        if not username or not password:
            raise RuntimeError(
                "首次启动必须设置 REPORT_BOOTSTRAP_ADMIN_USERNAME 和 REPORT_BOOTSTRAP_ADMIN_PASSWORD"
            )
        if len(password) < 8:
            raise RuntimeError("REPORT_BOOTSTRAP_ADMIN_PASSWORD 至少需要 8 个字符")
        user = self.database.create_user({
            "id": uuid.uuid4().hex, "username": username, "display_name": "超级管理员",
            "password_hash": self.hash_password(password), "role_code": "SUPER_ADMIN",
            "must_change_password": True,
        })
        return str(user["id"])

    def _migrate_report_all_view_permission(self) -> None:
        if self._permission_migration_checked:
            return
        migration_key = "grant-report-all-view-to-admins-v1"
        if self.database.migration_applied(migration_key):
            self._permission_migration_checked = True
            return
        self.database.add_role_permissions("SUPER_ADMIN", {"REPORT_ALL_VIEW"})
        self.database.add_role_permissions("SYSTEM_ADMIN", {"REPORT_ALL_VIEW"})
        self.database.mark_migration_applied(migration_key)
        self._permission_migration_checked = True
        logger.info("管理员跨用户报告只读权限迁移完成")

    def permissions_for(self, user: dict[str, Any]) -> set[str]:
        self._migrate_report_all_view_permission()
        return self.database.role_permissions(user["role_code"])

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        user = self.database.get_user_by_username(username.strip())
        if not user or not user["enabled"] or not self.verify_password(password, user["password_hash"]):
            return None
        self.database.update_user(user["id"], last_login_at=now_iso())
        return self.database.get_user(user["id"])

    def issue_session(self, user_id: str) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(hours=self.settings.session_hours)
        self.database.create_session(hashlib.sha256(token.encode()).hexdigest(), user_id, expires.isoformat())
        return token, expires

    def session_user(self, session: str | None) -> dict[str, Any]:
        if not session:
            raise HTTPException(401, "请先登录")
        user = self.database.get_session_user(hashlib.sha256(session.encode()).hexdigest())
        if not user:
            raise HTTPException(401, "登录已失效，请重新登录")
        user["permissions"] = self.permissions_for(user)
        return user

    def current_user(self, session: str | None = Cookie(default=None, alias=REPORT_SESSION_COOKIE)) -> dict[str, Any]:
        return self.session_user(session)

    def optional_user(self, session: str | None = Cookie(default=None, alias=REPORT_SESSION_COOKIE)) -> dict[str, Any] | None:
        if not session:
            return None
        user = self.database.get_session_user(hashlib.sha256(session.encode()).hexdigest())
        if user:
            user["permissions"] = self.permissions_for(user)
        return user

    def require(self, permission: str) -> Callable[..., dict[str, Any]]:
        def dependency(user: dict[str, Any] = Depends(self.current_user)) -> dict[str, Any]:
            if permission not in user["permissions"]:
                raise HTTPException(403, "没有执行此操作的权限")
            if user["must_change_password"]:
                raise HTTPException(403, "首次登录后必须先修改密码")
            return user
        return dependency

    def require_any(self, *permissions: str) -> Callable[..., dict[str, Any]]:
        def dependency(user: dict[str, Any] = Depends(self.current_user)) -> dict[str, Any]:
            if not set(permissions).intersection(user["permissions"]):
                raise HTTPException(403, "没有执行此操作的权限")
            if user["must_change_password"]:
                raise HTTPException(403, "首次登录后必须先修改密码")
            return user
        return dependency

    def admin_route_guard(self, request: Request,
                          session: str | None = Cookie(default=None, alias=REPORT_SESSION_COOKIE)) -> dict[str, Any]:
        # ONLYOFFICE fetches the document and posts save callbacks from the
        # Document Server process, so those requests cannot carry the browser
        # application-session cookie.  The endpoints themselves validate a signed
        # ONLYOFFICE JWT; keep the rest of the admin API behind the session
        # guard.
        path = request.url.path
        integration_prefix = f"{self.settings.api_prefix}/admin"
        if (
            path.startswith(f"{integration_prefix}/template/file/")
            or path.startswith(f"{integration_prefix}/onlyoffice/callback/")
        ):
            return {"integration": "onlyoffice"}
        user = self.session_user(session)
        if user["must_change_password"]:
            raise HTTPException(403, "首次登录后必须先修改密码")
        required = "LIMS_FIELDS_MANAGE" if any(
            marker in path for marker in ("standard-field", "extraction-rule", "data-source", "lims-recognition")
        ) else "RULES_MANAGE"
        if "ADMIN_ACCESS" not in user["permissions"] or required not in user["permissions"]:
            raise HTTPException(403, "没有访问此后台模块的权限")
        return user

    def logout(self, session: str | None) -> None:
        if session:
            self.database.delete_session(hashlib.sha256(session.encode()).hexdigest())


def create_auth_router(auth: AuthManager) -> APIRouter:
    router = APIRouter(prefix=f"{auth.settings.api_prefix}/auth", tags=["身份认证"])

    @router.post("/login")
    def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
        user = auth.authenticate(payload.username, payload.password)
        if not user:
            raise HTTPException(401, "用户名或密码错误")
        token, expires = auth.issue_session(user["id"])
        response.set_cookie(
            REPORT_SESSION_COOKIE, token, httponly=True, samesite="lax",
            secure=auth.settings.secure_cookies, expires=expires, path="/",
        )
        return auth.public_user(user, auth.permissions_for(user))

    @router.post("/logout")
    def logout(response: Response,
               session: str | None = Cookie(default=None, alias=REPORT_SESSION_COOKIE)) -> dict[str, bool]:
        auth.logout(session)
        response.delete_cookie(REPORT_SESSION_COOKIE, path="/")
        return {"ok": True}

    @router.get("/me")
    def me(session: str | None = Cookie(default=None, alias=REPORT_SESSION_COOKIE)) -> dict[str, Any]:
        user = auth.session_user(session)
        return auth.public_user(user, user["permissions"])

    @router.post("/change-password")
    def change_password(payload: ChangePasswordRequest,
                        session: str | None = Cookie(default=None, alias=REPORT_SESSION_COOKIE)) -> dict[str, Any]:
        user = auth.session_user(session)
        if not auth.verify_password(payload.current_password, user["password_hash"]):
            raise HTTPException(422, "当前密码不正确")
        auth.database.update_user(
            user["id"], password_hash=auth.hash_password(payload.new_password), must_change_password=0
        )
        refreshed = auth.database.get_user(user["id"])
        return auth.public_user(refreshed, auth.permissions_for(refreshed))

    return router
