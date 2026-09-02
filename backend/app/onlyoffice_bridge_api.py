import threading
import time
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .auth import AuthManager
from .config import Settings

logger = logging.getLogger(__name__)

# 插件运行在文档服务器 iframe 里，跨域拿不到用户会话，只能凭 channel 标识访问
# poll/trace，因此这两个端点保持免鉴权（channel 由插件生成，含约 52 位随机量）。
# 代价是必须限制资源：否则用海量伪造 channel 就能打爆内存和日志。
MAX_CHANNELS = 8192
MAX_CHANNEL_ID_LENGTH = 200
TTL_SECONDS = 3600
MAX_TRACE_EVENTS = 100


def _clean(value: Any, limit: int = 64) -> str:
    """日志字段只保留可见字符，防止用换行/控制字符注入日志。"""
    return "".join(ch for ch in str(value) if ch.isprintable())[:limit]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class BridgeStore:
    """ONLYOFFICE 插件命令/trace 的内存存储：按 TTL 与通道总数双上限回收。"""

    def __init__(self, max_channels: int = MAX_CHANNELS, ttl: float = TTL_SECONDS) -> None:
        self.commands: dict[str, dict[str, Any]] = {}
        self.traces: dict[str, list[dict[str, Any]]] = {}
        self.last_seen: dict[str, float] = {}
        self.max_channels = max_channels
        self.ttl = ttl
        self.lock = threading.Lock()

    def _validate(self, channel_id: str) -> None:
        if not channel_id or len(channel_id) > MAX_CHANNEL_ID_LENGTH:
            raise HTTPException(422, "channel 标识无效")

    def _drop(self, channel_id: str) -> None:
        self.last_seen.pop(channel_id, None)
        self.commands.pop(channel_id, None)
        self.traces.pop(channel_id, None)

    def _evict(self, now: float) -> None:
        # 先按 TTL 清理，再按最旧优先裁剪到上限，保证内存有界。
        for channel_id in [key for key, seen in self.last_seen.items() if now - seen > self.ttl]:
            self._drop(channel_id)
        if len(self.last_seen) > self.max_channels:
            for channel_id, _ in sorted(self.last_seen.items(), key=lambda item: item[1]):
                if len(self.last_seen) <= self.max_channels:
                    break
                self._drop(channel_id)

    def submit(self, channel_id: str, command: dict[str, Any]) -> None:
        self._validate(channel_id)
        with self.lock:
            self.commands[channel_id] = {**command, "storedAt": time.time()}
            self._record(channel_id, "host-submit", command)
            self._evict(time.time())

    def poll(self, channel_id: str, after: int = 0) -> dict[str, Any] | None:
        self._validate(channel_id)
        with self.lock:
            # 只刷新已知通道；未知 channel 不得借此创建存储项
            if channel_id in self.last_seen:
                self.last_seen[channel_id] = time.time()
            command = self.commands.get(channel_id)
            if not command or _safe_int(command.get("nonce")) <= after:
                return None
            self._record(channel_id, "plugin-poll-deliver", command)
            return {key: value for key, value in command.items() if key != "storedAt"}

    def record_trace(self, channel_id: str, event: dict[str, Any]) -> None:
        self._validate(channel_id)
        with self.lock:
            self._record(channel_id, str(event.get("stage") or "unknown"), event)
            self._evict(time.time())

    def list_traces(self, channel_id: str) -> list[dict[str, Any]]:
        self._validate(channel_id)
        with self.lock:
            self._evict(time.time())
            return list(self.traces.get(channel_id, []))

    def _record(self, channel_id: str, stage: str, payload: dict[str, Any]) -> None:
        events = self.traces.setdefault(channel_id, [])
        events.append({
            "stage": _clean(stage), "at": time.time(),
            "nonce": _safe_int(payload.get("nonce")),
            "type": _clean(payload.get("type") or payload.get("commandType") or ""),
        })
        del events[:-MAX_TRACE_EVENTS]
        self.last_seen[channel_id] = time.time()
        logger.info("ONLYOFFICE bridge channel=%s stage=%s nonce=%s type=%s",
                    _clean(channel_id, MAX_CHANNEL_ID_LENGTH),
                    events[-1]["stage"], events[-1]["nonce"], events[-1]["type"])


def create_onlyoffice_bridge_router(settings: Settings, auth: AuthManager) -> APIRouter:
    router = APIRouter(prefix=f"{settings.api_prefix}/onlyoffice/plugin-bridge")
    store = BridgeStore()

    @router.post("/{channel_id}")
    def submit_command(channel_id: str, command: dict[str, Any],
                       _: dict = Depends(auth.either_user)) -> dict[str, bool]:
        store.submit(channel_id, command)
        return {"accepted": True}

    @router.get("/{channel_id}")
    def poll_command(channel_id: str, after: int = 0) -> dict[str, Any] | None:
        return store.poll(channel_id, after)

    @router.post("/{channel_id}/trace")
    def submit_trace(channel_id: str, event: dict[str, Any]) -> dict[str, bool]:
        store.record_trace(channel_id, event)
        return {"accepted": True}

    @router.get("/{channel_id}/trace")
    def list_trace(channel_id: str, _: dict = Depends(auth.either_user)) -> list[dict[str, Any]]:
        return store.list_traces(channel_id)

    return router
