import threading
import time
import logging
from typing import Any

from fastapi import APIRouter, Depends

from .auth import AuthManager
from .config import Settings

logger = logging.getLogger(__name__)


def create_onlyoffice_bridge_router(settings: Settings, auth: AuthManager) -> APIRouter:
    router = APIRouter(prefix=f"{settings.api_prefix}/onlyoffice/plugin-bridge")
    commands: dict[str, dict[str, Any]] = {}
    traces: dict[str, list[dict[str, Any]]] = {}
    lock = threading.Lock()

    def prune() -> None:
        cutoff = time.time() - 3600
        stale = [key for key, value in commands.items() if value["storedAt"] < cutoff]
        for key in stale:
            commands.pop(key, None)
            traces.pop(key, None)

    def trace(channel_id: str, stage: str, payload: dict[str, Any]) -> None:
        event = {
            "stage": stage, "at": time.time(),
            "nonce": int(payload.get("nonce") or 0),
            "type": str(payload.get("type") or payload.get("commandType") or ""),
        }
        traces.setdefault(channel_id, []).append(event)
        traces[channel_id] = traces[channel_id][-100:]
        logger.info("ONLYOFFICE bridge channel=%s stage=%s nonce=%s type=%s",
                    channel_id, stage, event["nonce"], event["type"])

    @router.post("/{channel_id}")
    def submit_command(channel_id: str, command: dict[str, Any],
                       _: dict = Depends(auth.either_user)) -> dict[str, bool]:
        with lock:
            prune()
            commands[channel_id] = {**command, "storedAt": time.time()}
            trace(channel_id, "host-submit", command)
        return {"accepted": True}

    @router.get("/{channel_id}")
    def poll_command(channel_id: str, after: int = 0) -> dict[str, Any] | None:
        with lock:
            command = commands.get(channel_id)
            if not command or int(command.get("nonce") or 0) <= after:
                return None
            trace(channel_id, "plugin-poll-deliver", command)
            return {key: value for key, value in command.items() if key != "storedAt"}

    @router.post("/{channel_id}/trace")
    def submit_trace(channel_id: str, event: dict[str, Any]) -> dict[str, bool]:
        with lock:
            prune()
            trace(channel_id, str(event.get("stage") or "unknown"), event)
        return {"accepted": True}

    @router.get("/{channel_id}/trace")
    def list_trace(channel_id: str, _: dict = Depends(auth.either_user)) -> list[dict[str, Any]]:
        with lock:
            prune()
            return list(traces.get(channel_id, []))

    return router
