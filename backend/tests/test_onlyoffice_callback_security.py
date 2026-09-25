import asyncio
import io
import json
import threading
import urllib.request
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException

from backend.app.auth import AuthManager
from backend.app.config import Settings
from backend.app.database import Database, now_iso
from backend.app.onlyoffice_callback import is_current_document_key
from backend.app.report_word_api import create_report_word_router
from backend.app.services.onlyoffice_force_save import (
    OnlyOfficeForceSaveError, request_onlyoffice_force_save,
)
SECRET = "test-secret"
REPORT_ID = "rep1"
USER = {"id": "u1", "permissions": ["REPORT_EDIT"], "display_name": "测试"}


class FakeCallbackRequest:
    """ONLYOFFICE 回调端点只需要 request.json() 与 headers。"""

    def __init__(self, body: dict, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    async def json(self) -> dict:
        return self._body


class FakeCommandResponse:
    def __init__(self, payload: object):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _minimal_docx(value: str) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        f'<w:sdt><w:sdtPr><w:tag w:val="report_no"/></w:sdtPr>'
        f'<w:sdtContent><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:sdtContent></w:sdt>'
        "</w:body></w:document>"
    )
    # 固定 zip 时间戳：writestr 默认写入当前时间（DOS 精度 2 秒），
    # 字节级断言会在跨时间边界时偶发失败
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            zipfile.ZipInfo("[Content_Types].xml", date_time=(1980, 1, 1, 0, 0, 0)),
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        archive.writestr(
            zipfile.ZipInfo("word/document.xml", date_time=(1980, 1, 1, 0, 0, 0)),
            document_xml,
        )
    return buffer.getvalue()


def _signed_token(payload: dict, secret: str = SECRET) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


def build_env(tmp_path: Path, secret: str = SECRET):
    """搭建报告 Word 路由 + 本地“文档服务器”静态文件服务。"""
    served_dir = tmp_path / "docserver"
    served_dir.mkdir()
    (served_dir / "final.docx").write_bytes(_minimal_docx("SAVED-EDIT"))
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(served_dir), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    docserver_url = f"http://127.0.0.1:{server.server_address[1]}"

    settings = Settings(
        data_dir=tmp_path / "data",
        template_path=tmp_path / "templates" / "report-template.docx",
        onlyoffice_url=docserver_url,
        public_base_url="http://127.0.0.1:8010",
        onlyoffice_jwt_secret=secret,
    )
    settings.ensure_directories()
    database = Database(settings)
    database.initialize()
    database.create_report({
        "id": REPORT_ID, "title": "测试报告", "status": "EDITING",
        "resolved_data": {
            "template_id": "deleted-template", "template_catalog_version_id": "deleted-version",
            "template_revision": "r1", "report_no": "OLD",
            "field_sources": {"report_no": {"type": "LIMS", "record_id": "source-1"}},
        },
        "created_at": now_iso(), "updated_at": now_iso(),
        "created_by": "u1", "updated_by": "u1",
    })
    working = settings.reports_dir / f"report-{REPORT_ID}-working.docx"
    working.write_bytes(_minimal_docx("ORIGINAL"))

    def required_report(report_id: str) -> dict:
        row = database.get_report(report_id)
        if not row:
            raise HTTPException(404, "报告不存在")
        return row

    def required_owned_report(report_id: str, user: dict) -> dict:
        row = required_report(report_id)
        if row.get("created_by") != user["id"]:
            raise HTTPException(404, "报告不存在")
        return row

    router = create_report_word_router(
        database, settings, AuthManager(database, settings),
        required_report, required_owned_report,
    )
    config_endpoint = next(
        route.endpoint for route in router.routes
        if route.path == "/api/v1/onlyoffice/reports/{report_id}/config"
    )
    callback_endpoint = next(
        route.endpoint for route in router.routes
        if route.path == "/api/v1/onlyoffice/callback/{report_id}"
    )
    force_save_endpoint = next(
        route.endpoint for route in router.routes
        if route.path == "/api/v1/onlyoffice/reports/{report_id}/force-save"
    )
    return {
        "settings": settings, "database": database,
        "working": working, "served_dir": served_dir,
        "config_endpoint": config_endpoint, "callback_endpoint": callback_endpoint,
        "force_save_endpoint": force_save_endpoint,
        "server": server, "docserver_url": docserver_url,
    }


def issue_key(env: dict) -> str:
    result = env["config_endpoint"](REPORT_ID, USER)
    key = result["config"]["document"]["key"]
    assert env["database"].get_report(REPORT_ID)["onlyoffice_document_key"] == key
    return key


def test_report_editor_autostarts_toc_plugin(env: dict) -> None:
    config = env["config_endpoint"](REPORT_ID, USER, prepare=True)["config"]
    plugins = config["editorConfig"]["plugins"]
    assert plugins["autostart"] == ["asc.{B75A5F24-8D2C-4E91-A763-6C98B8B80A15}"]
    assert plugins["pluginsData"] == [
        f"{env['settings'].onlyoffice_url}/sdkjs-plugins/"
        "%7BB75A5F24-8D2C-4E91-A763-6C98B8B80A15%7D/config.json?v=26"
    ]
    assert config["editorConfig"]["customization"]["autosave"] is True
    assert jwt.decode(config["token"], SECRET, algorithms=["HS256"])["editorConfig"]["plugins"] == plugins


def post_callback(env: dict, *, status: int = 2, url: str | None = None,
                  key: str = "", token: str = "", userdata: str | None = None):
    """直接调用回调端点；返回 (status_code, body)，HTTPException 转成状态码。"""
    request = FakeCallbackRequest({
        "status": status, "url": url or f"{env['docserver_url']}/final.docx",
        "key": key, "token": token, "userdata": userdata,
    })
    try:
        return 200, asyncio.run(env["callback_endpoint"](REPORT_ID, request))
    except HTTPException as error:
        return int(error.status_code), error.detail


@pytest.fixture()
def env(tmp_path: Path, monkeypatch) -> dict:
    built = build_env(tmp_path)
    direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    monkeypatch.setattr(
        "backend.app.report_word_api.urllib.request.urlopen",
        lambda request, timeout=60: direct_opener.open(request, timeout=timeout),
    )
    yield built
    built["server"].shutdown()


def test_callback_requires_configured_jwt_secret(tmp_path: Path) -> None:
    built = build_env(tmp_path, secret="")
    try:
        status, _ = post_callback(built, key="whatever")
        assert status == 503
    finally:
        built["server"].shutdown()


def test_callback_rejects_missing_or_invalid_token(env: dict) -> None:
    assert post_callback(env)[0] == 401
    assert post_callback(env, token="not-a-jwt")[0] == 401
    forged = _signed_token({"status": 2, "key": "k"}, secret="attacker-secret")
    assert post_callback(env, token=forged)[0] == 401


def test_callback_rejects_url_outside_document_server(env: dict) -> None:
    token = _signed_token({"status": 2, "key": "k"})
    for url in (
        "http://169.254.169.254/latest/meta-data/",
        "http://evil.example.com/final.docx",
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_INFO",
    ):
        status, _ = post_callback(env, url=url, key="k", token=token)
        assert status == 400, url
    assert env["working"].read_bytes() == _minimal_docx("ORIGINAL")


def test_callback_rejects_missing_and_stale_document_key(env: dict) -> None:
    issued = issue_key(env)
    token = _signed_token({"status": 2})

    status, _ = post_callback(env, token=token)
    assert status == 400, "缺少 key 必须拒绝"

    status, body = post_callback(env, key="stale-key", token=token)
    assert status == 200, body
    assert body == {"error": 1}
    assert env["working"].read_bytes() == _minimal_docx("ORIGINAL"), "陈旧 key 不得覆盖工作文件"

    status, body = post_callback(env, key=issued, token=token)
    assert status == 200, body
    assert body == {"error": 0}
    assert env["working"].read_bytes() == _minimal_docx("SAVED-EDIT")
    saved = env["database"].get_report(REPORT_ID)
    assert saved["resolved_data"]["report_no"] == "OLD", "Word 保存不得反写结构化数据"
    assert saved["resolved_data"]["field_sources"]["report_no"]["type"] == "LIMS"


def test_current_document_key_rejects_stale_editor_session() -> None:
    assert is_current_document_key("active-editor-key", "active-editor-key")
    assert not is_current_document_key("active-editor-key", "stale-editor-key")
    assert not is_current_document_key("", "active-editor-key")


def test_repeated_autosaves_keep_working_with_same_key(env: dict) -> None:
    issued = issue_key(env)
    token = _signed_token({"status": 2})
    original_data = env["database"].get_report(REPORT_ID)["resolved_data"]

    # 文档 key 在整个编辑会话中保持不变，而每次保存后文件内容都会变化：
    # 校验必须对照签发记录，而不是与保存后的内容重新比较，
    # 否则第一次自动保存之后所有保存都会被误判为陈旧会话而丢弃
    for round_no in (1, 2, 3):
        (env["served_dir"] / "final.docx").write_bytes(_minimal_docx(f"SAVED-{round_no}"))
        status, body = post_callback(env, key=issued, token=token)
        assert status == 200, body
        assert body == {"error": 0}
        assert env["working"].read_bytes() == _minimal_docx(f"SAVED-{round_no}")
    assert env["database"].get_report(REPORT_ID)["word_edit_locked"] == 1
    assert env["database"].get_report(REPORT_ID)["resolved_data"] == original_data
    assert env["database"].list_versions(REPORT_ID) == []
    assert env["database"].list_changes(REPORT_ID) == []


def test_callback_does_not_require_the_source_template(env: dict) -> None:
    issued = issue_key(env)
    token = _signed_token({"status": 2})

    # 报告里仅保留已删除模板的来源标识，保存仍必须成功。
    status, body = post_callback(env, key=issued, token=token)
    assert status == 200, body
    assert body == {"error": 0}
    assert env["working"].read_bytes() == _minimal_docx("SAVED-EDIT")


def test_callback_rejects_invalid_docx_without_replacing_working_file(env: dict) -> None:
    issued = issue_key(env)
    token = _signed_token({"status": 2})
    original = env["working"].read_bytes()
    (env["served_dir"] / "final.docx").write_bytes(b"not-a-docx")

    status, body = post_callback(env, key=issued, token=token)

    assert status == 502
    assert "DOCX" in str(body)
    assert env["working"].read_bytes() == original


def test_config_requires_an_existing_generated_working_file(env: dict) -> None:
    env["working"].unlink()
    with pytest.raises(HTTPException, match="请先重新生成报告") as error:
        env["config_endpoint"](REPORT_ID, USER)
    assert error.value.status_code == 409


def test_config_issued_key_is_persisted(env: dict) -> None:
    result = env["config_endpoint"](REPORT_ID, USER)
    config = result["config"]
    key = config["document"]["key"]
    # key 形如 {report_id}-{工作文件内容哈希前 16 位}
    assert key.startswith(f"{REPORT_ID}-")
    assert len(key) == len(REPORT_ID) + 1 + 16
    assert key == env["database"].get_report(REPORT_ID)["onlyoffice_document_key"]
    assert config["editorConfig"]["callbackUrl"].endswith(f"/onlyoffice/callback/{REPORT_ID}")
    assert config["editorConfig"]["plugins"]["autostart"] == [
        "asc.{B75A5F24-8D2C-4E91-A763-6C98B8B80A15}"
    ]
    assert config["editorConfig"]["customization"]["goback"] == {
        "requestClose": True, "text": "返回报告大厅",
    }
    assert config["token"]


def test_prepare_config_keeps_autosave_enabled(env: dict) -> None:
    config = env["config_endpoint"](REPORT_ID, USER, True)["config"]
    assert config["editorConfig"]["customization"]["autosave"] is True
    assert env["config_endpoint"](REPORT_ID, USER)["config"]["editorConfig"]["customization"]["autosave"] is True


def test_toc_refresh_callback_does_not_lock_report(env: dict) -> None:
    issued = issue_key(env)
    status, body = post_callback(
        env, status=6, key=issued, token=_signed_token({"status": 6}),
        userdata=f"toc-refresh:{REPORT_ID}",
    )
    assert status == 200, body
    assert env["working"].read_bytes() == _minimal_docx("SAVED-EDIT")
    assert env["database"].get_report(REPORT_ID)["word_edit_locked"] == 0


def test_force_save_waits_for_working_file_update(env: dict, monkeypatch) -> None:
    issued = issue_key(env)
    captured: dict[str, str] = {}

    def request_save(url: str, secret: str, key: str, userdata: str) -> bool:
        captured.update(url=url, secret=secret, key=key, userdata=userdata)
        env["working"].write_bytes(_minimal_docx("FORCED-SAVE"))
        return True

    monkeypatch.setattr("backend.app.report_word_api.request_onlyoffice_force_save", request_save)
    result = env["force_save_endpoint"](REPORT_ID, USER)

    assert result == {"saved": True, "reportId": REPORT_ID}
    assert captured == {
        "url": env["settings"].onlyoffice_url,
        "secret": SECRET,
        "key": issued,
        "userdata": REPORT_ID,
    }


def test_toc_refresh_force_save_uses_distinct_userdata(env: dict, monkeypatch) -> None:
    issue_key(env)
    captured = {}

    def request_save(url: str, secret: str, key: str, userdata: str) -> bool:
        captured["userdata"] = userdata
        env["working"].write_bytes(_minimal_docx("TOC-REFRESHED"))
        return True

    monkeypatch.setattr("backend.app.report_word_api.request_onlyoffice_force_save", request_save)
    assert env["force_save_endpoint"](REPORT_ID, USER, True)["saved"] is True
    assert captured["userdata"] == f"toc-refresh:{REPORT_ID}"


def test_toc_refresh_rejects_no_saved_changes(env: dict, monkeypatch) -> None:
    issue_key(env)
    monkeypatch.setattr(
        "backend.app.report_word_api.request_onlyoffice_force_save", lambda *_args: False,
    )
    assert env["force_save_endpoint"](REPORT_ID, USER, True) == {
        "saved": False, "reportId": REPORT_ID,
    }


def test_toc_refresh_rejects_unchanged_saved_file(env: dict, monkeypatch) -> None:
    issue_key(env)

    def request_save(*_args) -> bool:
        env["working"].write_bytes(env["working"].read_bytes())
        return True

    monkeypatch.setattr("backend.app.report_word_api.request_onlyoffice_force_save", request_save)
    assert env["force_save_endpoint"](REPORT_ID, USER, True) == {
        "saved": False, "reportId": REPORT_ID,
    }


def test_force_save_allows_return_when_document_has_no_changes(env: dict, monkeypatch) -> None:
    issue_key(env)
    monkeypatch.setattr(
        "backend.app.report_word_api.request_onlyoffice_force_save", lambda *_args: False,
    )

    assert env["force_save_endpoint"](REPORT_ID, USER) == {
        "saved": False, "reportId": REPORT_ID,
    }


def test_force_save_requires_an_editor_session(env: dict) -> None:
    with pytest.raises(HTTPException, match="编辑器会话不存在") as error:
        env["force_save_endpoint"](REPORT_ID, USER)
    assert error.value.status_code == 409


@pytest.mark.parametrize(("error_code", "expected"), [(0, True), (4, False)])
def test_force_save_command_uses_current_document_key(
    monkeypatch, error_code: int, expected: bool,
) -> None:
    captured: dict[str, object] = {}

    def urlopen(request, timeout: float):
        captured.update(url=request.full_url, timeout=timeout, body=json.loads(request.data))
        return FakeCommandResponse({"error": error_code})

    monkeypatch.setattr(
        "backend.app.services.onlyoffice_force_save.urllib.request.urlopen", urlopen,
    )

    assert request_onlyoffice_force_save(
        "http://onlyoffice.test/", SECRET, "current-key", REPORT_ID,
    ) is expected
    assert captured["url"] == "http://onlyoffice.test/coauthoring/CommandService.ashx"
    command = captured["body"]
    assert command["c"] == "forcesave"
    assert command["key"] == "current-key"
    assert command["userdata"] == REPORT_ID
    assert jwt.decode(command["token"], SECRET, algorithms=["HS256"])["key"] == "current-key"


def test_force_save_command_rejects_malformed_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.onlyoffice_force_save.urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeCommandResponse([]),
    )
    with pytest.raises(OnlyOfficeForceSaveError, match="响应结构无效"):
        request_onlyoffice_force_save("http://onlyoffice.test", SECRET, "current-key", REPORT_ID)
