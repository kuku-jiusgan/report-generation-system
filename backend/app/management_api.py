import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .auth import AuthManager, PERMISSIONS
from .config import Settings
from .database import Database


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=256)
    role_code: str


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    role_code: str | None = None
    enabled: bool | None = None


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class UpdatePermissionsRequest(BaseModel):
    permissions: list[str]


def create_management_router(database: Database, settings: Settings, auth: AuthManager) -> APIRouter:
    router = APIRouter(prefix=f"{settings.api_prefix}/admin", tags=["后台管理系统"])

    def ensure_user_manageable(actor: dict[str, Any], target_role: str) -> None:
        if actor["role_code"] != "SUPER_ADMIN" and target_role != "REPORT_USER":
            raise HTTPException(403, "系统管理员只能管理报告用户")

    @router.get("/users")
    def list_users(query: str = "", actor: dict[str, Any] = Depends(auth.require("USERS_MANAGE", "admin"))) -> list[dict[str, Any]]:
        items = database.list_users(query)
        return [auth.public_user(item, database.role_permissions(item["role_code"])) for item in items]

    @router.post("/users")
    def create_user(payload: CreateUserRequest,
                    actor: dict[str, Any] = Depends(auth.require("USERS_MANAGE", "admin"))) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", payload.username):
            raise HTTPException(422, "用户名只能包含字母、数字、点、下划线和短横线")
        if payload.role_code not in {role["code"] for role in database.list_roles()}:
            raise HTTPException(422, "角色不存在")
        ensure_user_manageable(actor, payload.role_code)
        if database.get_user_by_username(payload.username):
            raise HTTPException(409, "用户名已存在")
        item = database.create_user({
            "id": uuid.uuid4().hex, "username": payload.username, "display_name": payload.display_name,
            "password_hash": auth.hash_password(payload.password), "role_code": payload.role_code,
            "must_change_password": True,
        })
        return auth.public_user(item, database.role_permissions(item["role_code"]))

    @router.put("/users/{user_id}")
    def update_user(user_id: str, payload: UpdateUserRequest,
                    actor: dict[str, Any] = Depends(auth.require("USERS_MANAGE", "admin"))) -> dict[str, Any]:
        target = database.get_user(user_id)
        if not target:
            raise HTTPException(404, "用户不存在")
        ensure_user_manageable(actor, target["role_code"])
        next_role = payload.role_code or target["role_code"]
        ensure_user_manageable(actor, next_role)
        if target["role_code"] == "SUPER_ADMIN" and payload.enabled is False:
            raise HTTPException(422, "不能停用超级管理员")
        changes = payload.model_dump(exclude_none=True)
        mapped = {"display_name": changes.get("display_name"), "role_code": changes.get("role_code")}
        if "enabled" in changes:
            mapped["enabled"] = int(changes["enabled"])
        item = database.update_user(user_id, **{key: value for key, value in mapped.items() if value is not None})
        if payload.enabled is False or next_role != target["role_code"]:
            database.delete_user_sessions(user_id)
        return auth.public_user(item, database.role_permissions(item["role_code"]))

    @router.post("/users/{user_id}/reset-password")
    def reset_password(user_id: str, payload: ResetPasswordRequest,
                       actor: dict[str, Any] = Depends(auth.require("USERS_MANAGE", "admin"))) -> dict[str, bool]:
        target = database.get_user(user_id)
        if not target:
            raise HTTPException(404, "用户不存在")
        ensure_user_manageable(actor, target["role_code"])
        database.update_user(
            user_id, password_hash=auth.hash_password(payload.password), must_change_password=1
        )
        database.delete_user_sessions(user_id)
        return {"ok": True}

    @router.get("/roles")
    def list_roles(actor: dict[str, Any] = Depends(auth.require("ADMIN_ACCESS", "admin"))) -> dict[str, Any]:
        return {"permissions": [{"code": code, "name": name} for code, name in PERMISSIONS.items()],
                "roles": database.list_roles()}

    @router.put("/roles/{role_code}/permissions")
    def update_role_permissions(role_code: str, payload: UpdatePermissionsRequest,
                                actor: dict[str, Any] = Depends(auth.require("PERMISSIONS_MANAGE", "admin"))) -> dict[str, Any]:
        if actor["role_code"] != "SUPER_ADMIN":
            raise HTTPException(403, "只有超级管理员可以修改角色权限")
        if role_code == "SUPER_ADMIN":
            raise HTTPException(422, "超级管理员权限不可修改")
        if role_code not in {role["code"] for role in database.list_roles()}:
            raise HTTPException(404, "角色不存在")
        requested = set(payload.permissions)
        unknown = requested - set(PERMISSIONS)
        if unknown:
            raise HTTPException(422, f"未知权限：{', '.join(sorted(unknown))}")
        database.replace_role_permissions(role_code, requested)
        database.delete_user_sessions_for_role(role_code)
        return next(role for role in database.list_roles() if role["code"] == role_code)

    @router.get("/report-history")
    def report_history(query: str = "", status: str = "", user_id: str = "", date_from: str = "",
                       date_to: str = "", page: int = 1, page_size: int = 20,
                       actor: dict[str, Any] = Depends(auth.require("REPORT_HISTORY_VIEW", "admin"))) -> dict[str, Any]:
        return database.list_generations(query, status, user_id, date_from, date_to,
                                         max(1, page), min(100, max(1, page_size)))

    @router.get("/report-history/{generation_id}")
    def report_history_detail(generation_id: str,
                              actor: dict[str, Any] = Depends(auth.require("REPORT_HISTORY_VIEW", "admin"))) -> dict[str, Any]:
        item = database.get_generation(generation_id)
        if not item:
            raise HTTPException(404, "生成记录不存在")
        return item

    @router.get("/report-history/{generation_id}/file")
    def download_history_file(generation_id: str,
                              actor: dict[str, Any] = Depends(auth.require("REPORT_HISTORY_DOWNLOAD", "admin"))) -> FileResponse:
        item = database.get_generation(generation_id)
        if not item or not item.get("output_name"):
            raise HTTPException(404, "历史文件不存在")
        path = (settings.reports_dir / Path(item["output_name"]).name).resolve()
        if not path.exists() or path.parent != settings.reports_dir.resolve():
            raise HTTPException(404, "历史文件不存在")
        report_no = item.get("resolved_data", {}).get("report_no") or item["title"]
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            filename=f"{report_no}-{generation_id[:8]}.docx")

    return router
