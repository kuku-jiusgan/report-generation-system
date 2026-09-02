import asyncio
import io
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException

from backend.app.auth import AuthManager
from backend.app.config import Settings
from backend.app.database import Database, now_iso
from backend.app.report_word_api import create_report_word_router
from backend.app.services.rule_admin import RuleAdminRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
    state = {"revision": "r1"}
    database = Database(settings.database_path)
    database.initialize()
    database.create_report({
        "id": REPORT_ID, "title": "测试报告", "status": "EDITING",
        "resolved_data": {"template_revision": state["revision"], "report_no": "OLD"},
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

    def runtime_template_and_mappings():
        return settings.template_path, [], [], {"template_revision": state["revision"]}

    rendered: list[str] = []

    def render_report_word(item: dict, data: dict, payload: dict | None = None,
                           output_suffix: str = "") -> str:
        # 与 main.render_report_word 一致：重渲染会把新模板元数据写回 data
        *_, template_meta = runtime_template_and_mappings()
        data.update(template_meta)
        rendered.append(item["id"])
        name = f"report-{item['id']}-working.docx"
        (settings.reports_dir / name).write_bytes(_minimal_docx("RENDERED"))
        return name

    router = create_report_word_router(
        database, settings, AuthManager(database, settings),
        RuleAdminRepository(database, PROJECT_ROOT / "mapping" / "template-mapping.json"),
        required_report, required_owned_report,
        runtime_template_and_mappings, render_report_word,
        lambda item: None, lambda snapshot: [],
    )
    config_endpoint = next(
        route.endpoint for route in router.routes
        if route.path == "/api/v1/onlyoffice/reports/{report_id}/config"
    )
    callback_endpoint = next(
        route.endpoint for route in router.routes
        if route.path == "/api/v1/onlyoffice/callback/{report_id}"
    )
    return {
        "settings": settings, "database": database,
        "working": working, "served_dir": served_dir,
        "config_endpoint": config_endpoint, "callback_endpoint": callback_endpoint,
        "rendered": rendered, "server": server, "docserver_url": docserver_url,
        "set_revision": lambda value: state.update(revision=value),
    }


def issue_key(env: dict) -> str:
    result = env["config_endpoint"](REPORT_ID, USER)
    key = result["config"]["document"]["key"]
    assert env["database"].get_report(REPORT_ID)["onlyoffice_document_key"] == key
    return key


def post_callback(env: dict, *, status: int = 2, url: str | None = None,
                  key: str = "", token: str = ""):
    """直接调用回调端点；返回 (status_code, body)，HTTPException 转成状态码。"""
    request = FakeCallbackRequest({
        "status": status, "url": url or f"{env['docserver_url']}/final.docx",
        "key": key, "token": token,
    })
    try:
        return 200, asyncio.run(env["callback_endpoint"](REPORT_ID, request))
    except HTTPException as error:
        return int(error.status_code), error.detail


@pytest.fixture()
def env(tmp_path: Path) -> dict:
    built = build_env(tmp_path)
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
    assert status == 200
    assert body == {"error": 1}
    assert env["working"].read_bytes() == _minimal_docx("ORIGINAL"), "陈旧 key 不得覆盖工作文件"

    status, body = post_callback(env, key=issued, token=token)
    assert status == 200
    assert body == {"error": 0}
    assert env["working"].read_bytes() == _minimal_docx("SAVED-EDIT")


def test_repeated_autosaves_keep_working_with_same_key(env: dict) -> None:
    issued = issue_key(env)
    token = _signed_token({"status": 2})

    # 文档 key 在整个编辑会话中保持不变，而每次保存后文件内容都会变化：
    # 校验必须对照签发记录，而不是与保存后的内容重新比较，
    # 否则第一次自动保存之后所有保存都会被误判为陈旧会话而丢弃
    for round_no in (1, 2, 3):
        (env["served_dir"] / "final.docx").write_bytes(_minimal_docx(f"SAVED-{round_no}"))
        status, body = post_callback(env, key=issued, token=token)
        assert status == 200
        assert body == {"error": 0}
        assert env["working"].read_bytes() == _minimal_docx(f"SAVED-{round_no}")
    assert env["database"].get_report(REPORT_ID)["word_edit_locked"] == 1
    assert any(version["note"] == "ONLYOFFICE 自动保存"
               for version in env["database"].list_versions(REPORT_ID))


def test_template_change_invalidates_open_session(env: dict) -> None:
    issued = issue_key(env)
    token = _signed_token({"status": 2})

    # 模板发布新版本后，未保存的旧编辑会话不得覆盖新渲染结果
    env["set_revision"]("r2")
    status, body = post_callback(env, key=issued, token=token)
    assert status == 200
    assert body == {"error": 1}
    assert env["rendered"] == [REPORT_ID], "检测到模板变更时必须重渲染"
    assert env["working"].read_bytes() == _minimal_docx("RENDERED"), "陈旧会话不得覆盖新渲染"

    # 重新打开编辑器（新会话）后可以正常保存
    fresh_key = issue_key(env)
    assert fresh_key != issued
    status, body = post_callback(env, key=fresh_key, token=token)
    assert status == 200
    assert body == {"error": 0}
    assert env["working"].read_bytes() == _minimal_docx("SAVED-EDIT")


def test_config_issued_key_is_persisted(env: dict) -> None:
    result = env["config_endpoint"](REPORT_ID, USER)
    config = result["config"]
    key = config["document"]["key"]
    # key 形如 {report_id}-{工作文件内容哈希前 16 位}
    assert key.startswith(f"{REPORT_ID}-")
    assert len(key) == len(REPORT_ID) + 1 + 16
    assert key == env["database"].get_report(REPORT_ID)["onlyoffice_document_key"]
    assert config["editorConfig"]["callbackUrl"].endswith(f"/onlyoffice/callback/{REPORT_ID}")
    assert config["token"]
