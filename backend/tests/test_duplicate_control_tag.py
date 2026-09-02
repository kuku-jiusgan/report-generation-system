"""重复 controlTag 必须显式报错并拦截发布，而不是当作统计信息放过。"""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.app.services.template_compiler import compile_template

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(body_xml: str) -> bytes:
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body_xml}</w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _mapping(field_code: str, tag: str, location: str) -> dict:
    return {
        "locationId": location, "controlTag": tag, "fieldCode": field_code,
        "wordLabel": field_code, "enabled": True, "sourcePending": False,
        "fillRule": "TEXT",
    }


class DuplicateControlTagTest(unittest.TestCase):
    def compile(self, body_xml: str, mappings: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "template.docx"
            source.write_bytes(_docx(body_xml))
            return compile_template(source, Path(directory) / "out.docx", mappings, [])

    def test_duplicate_tag_in_document_is_error(self) -> None:
        body = (
            '<w:sdt><w:sdtPr><w:tag w:val="doc.dup"/></w:sdtPr><w:sdtContent><w:p/></w:sdtContent></w:sdt>'
            '<w:sdt><w:sdtPr><w:tag w:val="doc.dup"/></w:sdtPr><w:sdtContent><w:p/></w:sdtContent></w:sdt>'
        )
        report = self.compile(body, [_mapping("field.a", "doc.dup", "word.content_control.doc.dup")])
        errors = [item for item in report["errors"] if item["code"] == "DUPLICATE_CONTROL_TAG"]
        self.assertTrue(errors, "同名控件在文档中出现两次必须报错")
        self.assertIn("doc.dup", errors[0]["message"])
        self.assertFalse(report["valid"])

    def test_same_tag_bound_to_multiple_fields_is_error(self) -> None:
        report = self.compile(
            "<w:p/>",
            [
                _mapping("field.a", "map.dup", "word.content_control.map.dup.a"),
                _mapping("field.b", "map.dup", "word.content_control.map.dup.b"),
            ],
        )
        errors = [item for item in report["errors"] if item["code"] == "DUPLICATE_CONTROL_TAG"]
        self.assertTrue(errors, "两个字段绑定同一个 tag 必须报错")
        self.assertIn("map.dup", errors[0]["message"])
        self.assertIn("field.a", errors[0]["message"])
        self.assertIn("field.b", errors[0]["message"])
        self.assertFalse(report["valid"])

    def test_unique_tags_still_pass(self) -> None:
        body = '<w:sdt><w:sdtPr><w:tag w:val="only.tag"/></w:sdtPr><w:sdtContent><w:p/></w:sdtContent></w:sdt>'
        report = self.compile(body, [_mapping("field.a", "only.tag", "word.content_control.only.tag")])
        self.assertEqual([], [item for item in report["errors"] if item["code"] == "DUPLICATE_CONTROL_TAG"])
        self.assertTrue(report["valid"])
