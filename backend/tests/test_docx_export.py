"""导出移除嵌套定位控件，内容、格式、图片和工作文档必须保留。"""

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from lxml import etree

from backend.app.services.docx_export import (
    export_docx_bytes, export_docx_response, write_export_docx,
)
from backend.app.services.docx_language import W_NS

NS = {"w": W_NS}
PARTS = ["word/document.xml", "word/header1.xml", "word/footer1.xml",
         "word/footnotes.xml", "word/endnotes.xml"]


def _template(path: Path) -> bytes:
    xml = f'''<w:document xmlns:w="{W_NS}"><w:body>
      <w:p><w:r><w:t>前文</w:t></w:r>
        <w:sdt><w:sdtPr><w:tag w:val="inline"/><w:lock w:val="sdtLocked"/></w:sdtPr>
          <w:sdtContent><w:r><w:rPr><w:b/></w:rPr><w:t>行内内容</w:t></w:r>
          </w:sdtContent></w:sdt><w:r><w:t>后文</w:t></w:r></w:p>
      <w:sdt><w:sdtPr><w:tag w:val="block"/></w:sdtPr><w:sdtContent>
        <w:tbl><w:tblPr/><w:tr><w:tc><w:tcPr><w:tcW w:w="100"/></w:tcPr>
          <w:sdt><w:sdtPr><w:tag w:val="nested"/></w:sdtPr><w:sdtContent>
            <w:p><w:pPr><w:jc w:val="center"/></w:pPr>
              <w:r><w:t>表格内容</w:t><w:drawing/></w:r></w:p>
          </w:sdtContent></w:sdt></w:tc></w:tr></w:tbl>
      </w:sdtContent></w:sdt>
      <w:sdt><w:sdtPr/><w:sdtContent><w:p/></w:sdtContent></w:sdt>
      <w:sectPr/>
    </w:body></w:document>'''.encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name in PARTS:
            archive.writestr(name, xml)
        archive.writestr("word/media/image1.png", b"image bytes")
        archive.writestr("word/_rels/document.xml.rels", b"relationships")
    return path.read_bytes()


def test_export_preserves_content_and_source(tmp_path: Path) -> None:
    source = tmp_path / "working.docx"
    original = _template(source)
    exported = export_docx_bytes(source)
    assert source.read_bytes() == original
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        for name in PARTS:
            root = etree.fromstring(archive.read(name))
            assert not root.xpath(".//w:sdt | .//w:sdtPr | .//w:sdtContent", namespaces=NS)
            assert root.xpath(".//w:t/text()", namespaces=NS) == ["前文", "行内内容", "后文", "表格内容"]
            assert root.xpath(".//w:rPr/w:b", namespaces=NS)
            assert root.xpath(".//w:tcPr/w:tcW/@w:w", namespaces=NS) == ["100"]
            assert root.xpath(".//w:pPr/w:jc/@w:val", namespaces=NS) == ["center"]
            assert root.xpath(".//w:drawing", namespaces=NS)
            assert len(root.xpath("./w:body/w:p", namespaces=NS)) == 2
        assert archive.read("word/media/image1.png") == b"image bytes"
        assert archive.read("word/_rels/document.xml.rels") == b"relationships"
    # 历史导出文件再次下载时清理必须可重复执行。
    output = tmp_path / "export.docx"
    write_export_docx(source, output)
    assert export_docx_bytes(output) == exported


def test_download_response_has_clean_document(tmp_path: Path) -> None:
    source = tmp_path / "working.docx"
    _template(source)
    response = export_docx_response(source, "中文报告")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert not etree.fromstring(archive.read(PARTS[0])).xpath(".//w:sdt", namespaces=NS)


@pytest.mark.parametrize("content", ["", "<w:sdtContent/><w:sdtContent/>"])
def test_invalid_control_does_not_replace_existing_export(tmp_path: Path, content: str) -> None:
    source, output = tmp_path / "working.docx", tmp_path / "export.docx"
    output.write_bytes(b"existing report")
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(PARTS[0], f'<w:document xmlns:w="{W_NS}"><w:sdt>{content}</w:sdt></w:document>')
    with pytest.raises(ValueError, match="定位控件结构异常"):
        write_export_docx(source, output)
    assert output.read_bytes() == b"existing report"


def test_word_export_uses_existing_working_file_and_history_download_is_clean(
    tmp_path: Path, monkeypatch,
) -> None:
    from backend.app import main

    source = tmp_path / "report-r1-working.docx"
    original = _template(source)
    item = {"id": "r1", "title": "报告", "resolved_data": {}}
    database = Mock()
    database.update_report.return_value = item
    database.create_version.return_value = {"id": "v1"}
    render = Mock(side_effect=AssertionError("导出不应重新生成 Word"))
    monkeypatch.setattr(main, "database", database)
    monkeypatch.setattr(main, "settings", SimpleNamespace(reports_dir=tmp_path))
    monkeypatch.setattr(main, "required_owned_report", lambda *_: item)
    monkeypatch.setattr(main, "render_report_word", render)
    monkeypatch.setattr(main, "report_response", lambda value: value)
    main.export_report_word("r1", {"id": "u1"})
    render.assert_not_called()
    database.create_version.assert_called_once_with("r1", {}, "导出 Word")
    output_name = database.update_generation.call_args.kwargs["output_name"]
    with zipfile.ZipFile(tmp_path / output_name) as archive:
        assert not etree.fromstring(archive.read(PARTS[0])).xpath(".//w:sdt", namespaces=NS)
    assert source.read_bytes() == original
    # 旧历史文档同样在下载时清理，不修改历史原件。
    database.get_generation.return_value = {
        "generated_by": "u1", "status": "SUCCESS", "output_name": source.name, "title": "报告",
    }
    response = main.download_generation("g1", {"id": "u1"})
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert not etree.fromstring(archive.read(PARTS[0])).xpath(".//w:sdt", namespaces=NS)
    assert source.read_bytes() == original


def test_word_export_requires_existing_working_file(tmp_path: Path, monkeypatch) -> None:
    from backend.app import main

    item = {"id": "r1", "title": "报告", "resolved_data": {}}
    database = Mock()
    monkeypatch.setattr(main, "database", database)
    monkeypatch.setattr(main, "settings", SimpleNamespace(reports_dir=tmp_path))
    monkeypatch.setattr(main, "required_owned_report", lambda *_: item)

    with pytest.raises(HTTPException) as caught:
        main.export_report_word("r1", {"id": "u1"})

    assert caught.value.status_code == 409
    assert "请先重新生成报告" in str(caught.value.detail)
    database.create_version.assert_not_called()


def test_batch_word_export_does_not_regenerate_missing_working_file(
    tmp_path: Path, monkeypatch,
) -> None:
    from backend.app import main

    item = {"id": "r1", "title": "报告", "resolved_data": {}}
    render = Mock(side_effect=AssertionError("导出不应重新生成 Word"))
    monkeypatch.setattr(main, "settings", SimpleNamespace(reports_dir=tmp_path))
    monkeypatch.setattr(main, "required_owned_report", lambda *_: item)
    monkeypatch.setattr(main, "render_report_word", render)

    with pytest.raises(HTTPException) as caught:
        main.batch_export_reports({"report_ids": ["r1"]}, {"id": "u1"})

    assert caught.value.status_code == 409
    assert "请先重新生成报告" in str(caught.value.detail)
    render.assert_not_called()


def test_user_download_and_editor_both_hide_content_controls(tmp_path: Path) -> None:
    import jwt
    from backend.app.report_word_api import create_report_word_router

    source = tmp_path / "report-r1-working.docx"
    original = _template(source)
    settings = SimpleNamespace(api_prefix="/api", reports_dir=tmp_path, onlyoffice_jwt_secret="test-secret")
    auth = Mock()
    item = {"id": "r1", "title": "报告", "created_by": "u1", "output_name": source.name}
    router = create_report_word_router(
        Mock(), settings, auth, lambda _: item, Mock(),
    )
    download = next(route.endpoint for route in router.routes if route.path.endswith("/file"))
    response = download("r1", user={"id": "u1", "permissions": ["REPORT_DOWNLOAD"]})
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert not etree.fromstring(archive.read(PARTS[0])).xpath(".//w:sdt", namespaces=NS)
    token = jwt.encode({"purpose": "report-file", "reportId": "r1"}, settings.onlyoffice_jwt_secret)
    editor_response = download("r1", document_token=token, user=None)
    with zipfile.ZipFile(io.BytesIO(editor_response.body)) as archive:
        assert not etree.fromstring(archive.read(PARTS[0])).xpath(".//w:sdt", namespaces=NS)
    assert source.read_bytes() == original
