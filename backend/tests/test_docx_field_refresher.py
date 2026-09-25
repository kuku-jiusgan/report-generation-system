import subprocess
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from lxml import etree

from backend.app.services.docx_field_refresher import (
    DocxFieldRefreshError,
    _remove_orphan_toc_entries,
    _toc_links,
    refresh_docx_fields,
)


DOCUMENT_XML = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:sdt><w:sdtPr><w:tag w:val="mapped-field"/></w:sdtPr>
      <w:sdtContent><w:p><w:r><w:t>report</w:t></w:r></w:p></w:sdtContent>
    </w:sdt>
    <w:p>
      <w:r><w:fldChar w:fldCharType="begin"/></w:r>
      <w:r><w:instrText> PAGE </w:instrText></w:r>
      <w:r><w:fldChar w:fldCharType="separate"/></w:r>
      <w:r><w:t>999</w:t></w:r>
      <w:r><w:fldChar w:fldCharType="end"/></w:r>
    </w:p>
  </w:body>
</w:document>'''


def _write_docx(path: Path, text: bytes = DOCUMENT_XML) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", text)


def _write_backslash_docx(path: Path, text: bytes = DOCUMENT_XML) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word\\document.xml", text)


def _converted_path(command: list[str]) -> Path:
    return Path(command[-2])


def _running_office():
    process = Mock()
    process.poll.return_value = None
    process.wait.return_value = 0
    return patch(
        "backend.app.services.docx_field_refresher.subprocess.Popen",
        return_value=process,
    )


def test_refresh_replaces_document_only_after_valid_conversion(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    _write_docx(document)
    refreshed_xml = DOCUMENT_XML.replace(b">999<", b">4<")

    def convert(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        _write_docx(_converted_path(command), refreshed_xml)
        return subprocess.CompletedProcess(command, 0, "converted", "")

    with _running_office() as popen, patch(
        "backend.app.services.docx_field_refresher.subprocess.run", side_effect=convert,
    ) as run:
        refresh_docx_fields(document, "custom-office", 45, "custom-python")

    with zipfile.ZipFile(document) as archive:
        merged = archive.read("word/document.xml")
    assert b'w:tag w:val="mapped-field"' in merged
    assert b">report<" in merged
    assert b">4<" in merged
    assert b">999<" not in merged
    office_command = popen.call_args.args[0]
    assert popen.call_args.kwargs["env"]["FONTCONFIG_FILE"].endswith("/fonts.conf")
    worker_command = run.call_args.args[0]
    assert office_command[0] == "custom-office"
    assert worker_command[0] == "custom-python"
    assert worker_command[1].endswith("libreoffice_field_worker.py")
    assert run.call_args.kwargs["timeout"] == 55
    assert any(item.startswith("-env:UserInstallation=file:") for item in office_command)


def test_refresh_accepts_windows_style_docx_member_names(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    _write_backslash_docx(document)
    refreshed_xml = DOCUMENT_XML.replace(b">999<", b">4<")

    def convert(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        _write_docx(_converted_path(command), refreshed_xml)
        return subprocess.CompletedProcess(command, 0, "", "")

    with _running_office(), patch(
        "backend.app.services.docx_field_refresher.subprocess.run", side_effect=convert,
    ):
        refresh_docx_fields(document)

    with zipfile.ZipFile(document) as archive:
        assert b">4<" in archive.read("word/document.xml")


def test_refresh_uses_rendered_toc_and_matching_body(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    original = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:sdt><w:sdtPr><w:tag w:val="mapped-field"/></w:sdtPr>
          <w:sdtContent><w:p><w:r><w:t>report</w:t></w:r></w:p></w:sdtContent>
        </w:sdt>
        <w:p><w:pPr><w:spacing w:line="360"/></w:pPr>
          <w:r><w:fldChar w:fldCharType="begin"/></w:r>
          <w:r><w:instrText> TOC \\o "1-2" </w:instrText></w:r>
          <w:r><w:fldChar w:fldCharType="separate"/></w:r>
          <w:hyperlink w:anchor="_Toc1">
            <w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t>1. 目的</w:t><w:tab/></w:r>
            <w:r><w:fldChar w:fldCharType="begin"/></w:r>
            <w:r><w:instrText> PAGEREF _Toc1 \\h </w:instrText></w:r>
            <w:r><w:fldChar w:fldCharType="separate"/></w:r>
            <w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t>999</w:t></w:r>
            <w:r><w:fldChar w:fldCharType="end"/></w:r>
          </w:hyperlink>
          <w:r><w:fldChar w:fldCharType="end"/></w:r>
        </w:p>
        <w:p><w:bookmarkStart w:id="1" w:name="_Toc1"/><w:r><w:t>目的</w:t></w:r>
          <w:bookmarkEnd w:id="1"/></w:p>
      </w:body>
    </w:document>'''.encode()
    _write_docx(document, original)
    rendered = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:sdt><w:sdtPr><w:tag w:val="mapped-field"/></w:sdtPr>
          <w:sdtContent><w:p><w:r><w:t>report</w:t></w:r></w:p></w:sdtContent>
        </w:sdt>
        <w:sdt><w:sdtPr/><w:sdtContent><w:p>
          <w:r><w:fldChar w:fldCharType="begin"/></w:r>
          <w:r><w:instrText> TOC \\o "1-2" </w:instrText></w:r>
          <w:r><w:fldChar w:fldCharType="separate"/></w:r>
          <w:hyperlink w:anchor="__RefHeading1">
            <w:r><w:t>1. 新标题</w:t><w:tab/><w:t>4</w:t></w:r>
          </w:hyperlink>
          <w:r><w:fldChar w:fldCharType="end"/></w:r>
        </w:p></w:sdtContent></w:sdt>
        <w:p><w:bookmarkStart w:id="2" w:name="__RefHeading1"/>
          <w:bookmarkStart w:id="1" w:name="_Toc1"/><w:r><w:t>新标题</w:t></w:r>
          <w:bookmarkEnd w:id="1"/><w:bookmarkEnd w:id="2"/></w:p>
      </w:body>
    </w:document>'''.encode()

    def convert(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        _write_docx(_converted_path(command), rendered)
        return subprocess.CompletedProcess(command, 0, "converted", "")

    with _running_office(), patch(
        "backend.app.services.docx_field_refresher.subprocess.run", side_effect=convert,
    ):
        refresh_docx_fields(document)

    with zipfile.ZipFile(document) as archive:
        merged = archive.read("word/document.xml")
    assert b'w:tag w:val="mapped-field"' in merged
    assert b">report<" in merged
    assert "新标题" in merged.decode()
    assert "1. 目的" not in merged.decode()
    assert b">4<" in merged
    assert b">999<" not in merged


def test_refresh_removes_orphan_toc_entry() -> None:
    root = etree.fromstring('''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>
        <w:r><w:instrText> TOC \\o "1-2" </w:instrText></w:r>
        <w:r><w:fldChar w:fldCharType="separate"/></w:r>
        <w:hyperlink w:anchor="missing"><w:r><w:t>封面标题36</w:t></w:r></w:hyperlink></w:p>
        <w:p><w:hyperlink w:anchor="valid"><w:r><w:t>概述4</w:t></w:r></w:hyperlink></w:p>
        <w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>
        <w:p><w:bookmarkStart w:id="1" w:name="valid"/><w:r><w:t>概述</w:t></w:r></w:p>
      </w:body></w:document>'''.encode())

    assert _remove_orphan_toc_entries(root)
    assert [link.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}anchor")
            for link in _toc_links(root)] == ["valid"]
    assert "封面标题36" not in "".join(root.xpath(".//w:t/text()", namespaces={
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    }))


def test_refresh_allows_flattened_content_control(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    _write_docx(document)
    rendered = DOCUMENT_XML.replace(b'<w:tag w:val="mapped-field"/>', b'')

    def convert(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        _write_docx(_converted_path(command), rendered)
        return subprocess.CompletedProcess(command, 0, "", "")

    with _running_office(), patch(
        "backend.app.services.docx_field_refresher.subprocess.run", side_effect=convert,
    ):
        refresh_docx_fields(document)
    with zipfile.ZipFile(document) as archive:
        result = archive.read("word/document.xml")
    assert b">report<" in result
    assert b'mapped-field' not in result


def test_refresh_rejects_lost_control_text(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    _write_docx(document)
    original = document.read_bytes()
    rendered = DOCUMENT_XML.replace(b">report<", b">lost<")

    def convert(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        _write_docx(_converted_path(command), rendered)
        return subprocess.CompletedProcess(command, 0, "", "")

    with _running_office(), patch(
        "backend.app.services.docx_field_refresher.subprocess.run", side_effect=convert,
    ):
        with pytest.raises(DocxFieldRefreshError, match="丢失了已填内容"):
            refresh_docx_fields(document)
    assert document.read_bytes() == original


def test_refresh_allows_field_result_change_inside_control(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    field = (b'<w:r><w:t>prefix</w:t></w:r>'
             b'<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
             b'<w:r><w:instrText> SEQ Table </w:instrText></w:r>'
             b'<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
             b'<w:r><w:t>1</w:t></w:r>'
             b'<w:r><w:fldChar w:fldCharType="end"/></w:r>'
             b'<w:r><w:t>suffix</w:t></w:r>')
    original_xml = DOCUMENT_XML.replace(b'<w:r><w:t>report</w:t></w:r>', field)
    _write_docx(document, original_xml)
    rendered = original_xml.replace(b'>1<', b'>2<').replace(b'<w:tag w:val="mapped-field"/>', b'')

    def convert(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        _write_docx(_converted_path(command), rendered)
        return subprocess.CompletedProcess(command, 0, "", "")

    with _running_office(), patch(
        "backend.app.services.docx_field_refresher.subprocess.run", side_effect=convert,
    ):
        refresh_docx_fields(document)
    with zipfile.ZipFile(document) as archive:
        result = archive.read("word/document.xml")
    assert b'>prefix<' in result and b'>suffix<' in result and b'>2<' in result


@pytest.mark.parametrize("returncode, creates_output", [(1, False), (0, False), (0, True)])
def test_refresh_failure_preserves_original(tmp_path: Path, returncode: int,
                                           creates_output: bool) -> None:
    document = tmp_path / "report.docx"
    _write_docx(document)
    original = document.read_bytes()

    def convert(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if creates_output:
            _converted_path(command).write_text("not a docx", encoding="utf-8")
        return subprocess.CompletedProcess(command, returncode, "", "conversion failed")

    with _running_office(), patch(
        "backend.app.services.docx_field_refresher.subprocess.run", side_effect=convert,
    ):
        with pytest.raises(DocxFieldRefreshError, match="LibreOffice"):
            refresh_docx_fields(document)

    assert document.read_bytes() == original


def test_missing_libreoffice_has_clear_error(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    _write_docx(document)
    with patch(
        "backend.app.services.docx_field_refresher.subprocess.Popen",
        side_effect=FileNotFoundError,
    ):
        with pytest.raises(DocxFieldRefreshError, match="找不到可执行文件"):
            refresh_docx_fields(document, "missing-office")


def test_invalid_input_is_rejected_before_starting_libreoffice(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    document.write_text("not a docx", encoding="utf-8")
    with patch("backend.app.services.docx_field_refresher.subprocess.Popen") as popen:
        with pytest.raises(DocxFieldRefreshError, match="不是有效的 DOCX"):
            refresh_docx_fields(document)
    popen.assert_not_called()
