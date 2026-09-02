"""ONLYOFFICE 文档服务器回调的公共校验。

回调由 ONLYOFFICE Document Server 进程发起，不携带任何用户会话，
因此安全完全依赖三层校验：JWT 签名（密钥必须配置）、回调文件地址
必须指向已配置的文档服务器（防止 SSRF）、文档 key 必须与签发记录
一致（防止陈旧会话覆盖最新文件）。
"""
import json
import urllib.parse
from typing import Any

import jwt
from fastapi import HTTPException, Request

from .config import Settings


async def verified_callback_payload(request: Request, settings: Settings) -> dict[str, Any]:
    """校验回调签名并返回回调体；未配置 JWT 密钥时拒绝服务。"""
    if not settings.onlyoffice_jwt_secret:
        raise HTTPException(503, "ONLYOFFICE JWT 密钥未配置，请设置 REPORT_ONLYOFFICE_JWT_SECRET")
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(400, "ONLYOFFICE 回调请求体无效") from error
    if not isinstance(payload, dict):
        raise HTTPException(400, "ONLYOFFICE 回调请求体无效")
    token = payload.get("token")
    authorization = request.headers.get("authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if not isinstance(token, str) or not token:
        raise HTTPException(401, "ONLYOFFICE 回调缺少签名")
    try:
        jwt.decode(token, settings.onlyoffice_jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as error:
        raise HTTPException(401, "ONLYOFFICE 回调签名无效") from error
    return payload


def assert_document_server_url(url: Any, settings: Settings) -> None:
    """回调给出的文件下载地址必须指向配置的文档服务器，否则拒绝（防止 SSRF）。"""
    base = urllib.parse.urlparse(settings.onlyoffice_url or "")
    target = urllib.parse.urlparse(str(url or ""))
    if (
        target.scheme not in ("http", "https")
        or not base.netloc
        or target.netloc != base.netloc
    ):
        raise HTTPException(400, "ONLYOFFICE 回调文件地址无效：必须来自已配置的文档服务器")


def callback_status(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("status", 0))
    except (TypeError, ValueError) as error:
        raise HTTPException(400, "ONLYOFFICE 回调 status 无效") from error
