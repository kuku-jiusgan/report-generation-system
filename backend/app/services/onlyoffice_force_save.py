import json
import time
import urllib.request
from pathlib import Path

import jwt


class OnlyOfficeForceSaveError(RuntimeError):
    pass


def request_onlyoffice_force_save(
    onlyoffice_url: str,
    jwt_secret: str,
    document_key: str,
    userdata: str,
    timeout_seconds: float = 15,
) -> bool:
    if not document_key:
        raise OnlyOfficeForceSaveError("ONLYOFFICE 文档 key 为空")
    command: dict[str, str] = {"c": "forcesave", "key": document_key, "userdata": userdata}
    command["token"] = jwt.encode(command, jwt_secret, algorithm="HS256")
    request = urllib.request.Request(
        f"{onlyoffice_url.rstrip('/')}/coauthoring/CommandService.ashx",
        data=json.dumps(command).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise TypeError("ONLYOFFICE 强制保存响应结构无效")
        error_code = int(result.get("error", -1))
    except (OSError, TypeError, ValueError) as error:
        raise OnlyOfficeForceSaveError(f"ONLYOFFICE 强制保存请求失败：{error}") from error
    if error_code == 4:
        return False
    if error_code != 0:
        raise OnlyOfficeForceSaveError(f"ONLYOFFICE 强制保存失败，错误码：{error_code}")
    return True


def wait_for_file_update(
    path: Path,
    previous_mtime_ns: int,
    timeout_seconds: float = 20,
    poll_interval_seconds: float = 0.25,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_mtime_ns > previous_mtime_ns:
            return
        time.sleep(poll_interval_seconds)
    raise TimeoutError("ONLYOFFICE 保存回调超时")
