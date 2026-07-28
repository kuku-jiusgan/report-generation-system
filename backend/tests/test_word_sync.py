import tempfile
import unittest
import zipfile
from pathlib import Path

from app.services.word_sync import read_bound_values


def part(*controls: tuple[str, str]) -> str:
    body = "".join(
        f'<w:sdt><w:sdtPr><w:tag w:val="{tag}"/></w:sdtPr>'
        f'<w:sdtContent><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:sdtContent></w:sdt>'
        for tag, value in controls
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'


class WordSyncTest(unittest.TestCase):
    def test_reads_mapped_repeats_and_uses_header_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/header1.xml", part(("reportHeader.reportNo", "HEADER-001")))
                archive.writestr("word/document.xml", part(
                    ("document.code", "BODY-002"),
                    ("project.name.body", "项目名称"),
                    ("repeat.t1.field1", "甲"),
                    ("repeat.t1.field1", "乙"),
                ))
            mappings = [
                {"controlTag": "reportHeader.reportNo", "fieldCode": "reportHeader.reportNo"},
                {"controlTag": "document.code", "fieldCode": "document.code"},
                {"controlTag": "project.name.body", "fieldCode": "project.name.body"},
                {"controlTag": "repeat.t1.field1", "fieldCode": "approval[].field1"},
            ]
            bound, canonical = read_bound_values(path, mappings)
            self.assertEqual("HEADER-001", canonical["report_no"])
            self.assertEqual("项目名称", canonical["project_name"])
            self.assertEqual(["甲", "乙"], bound["approval[].field1"])


if __name__ == "__main__":
    unittest.main()
