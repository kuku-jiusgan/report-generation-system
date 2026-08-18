import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from backend.app.config import get_settings
from backend.app.database import Database
from backend.app.services.mapped_docx_generator import build_mapped_docx
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.template_compiler import compile_template


ROOT = Path(__file__).resolve().parents[2]
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class ContentBlockRegressionTest(unittest.TestCase):
    def repository(self, directory: str) -> RuleAdminRepository:
        database = Database(Path(directory) / "rules.db")
        database.initialize()
        repository = RuleAdminRepository(database, ROOT / "mapping" / "template-mapping.json")
        repository.seed()
        return repository

    def test_blocks_are_persisted_with_fields_in_version_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.repository(directory)
            chapter = repository.list_template_chapters()[0]
            block = repository.create_content_block({
                "chapterId": chapter["id"], "title": "测试循环表格", "kind": "REPEATING_TABLE",
                "tableNo": "T99", "sourcePath": "$.columns[*]", "repeatKey": "serialNo",
                "prototypeLocation": "body.T99.dataRow", "dedupKey": "serialNo",
                "sortRule": "name ASC", "emptyBehavior": "KEEP", "mergeRule": "NONE", "enabled": True,
            })
            mapping = repository.create_mapping({
                "chapterId": chapter["id"], "blockId": block["id"],
                "locationId": "body.T99.dataRow.cell1", "sectionCode": "test", "tableNo": "T99",
                "wordLabel": "色谱柱名称", "fieldCode": "columns[].name", "dataType": "string",
                "sourceType": "LIMS", "sourcePath": "$.columns[*].name", "repeatType": "ROW",
                "repeatKey": "serialNo", "mergeRule": "PRESERVE", "fillRule": "TEXT",
                "calculationRule": "", "controlTag": "columns.name.test", "required": False,
                "sourcePending": False, "enabled": True,
            })
            snapshot = repository.snapshot()
            saved = next(item for item in snapshot["contentBlocks"] if item["id"] == block["id"])
            self.assertEqual(saved["sourcePath"], "$.columns[*]")
            self.assertIn(mapping["id"], saved["mappingIds"])
            repository._restore_snapshot(snapshot)
            restored = next(item for item in repository.list_content_blocks() if item["id"] == block["id"])
            self.assertIn(mapping["id"], restored["mappingIds"])

    def test_new_mapping_generates_name_and_all_word_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.repository(directory)
            chapter = next(
                item for item in repository.list_template_chapters() if item["code"] == "7.1"
            )
            block = repository.create_content_block({
                "chapterId": chapter["id"], "title": "试验过程", "kind": "MAPPED_FIELD",
                "tableNo": "", "enabled": True,
            })
            mapping = repository.create_mapping({
                "chapterId": chapter["id"], "blockId": block["id"],
                "locationId": "", "sectionCode": "7.1", "tableNo": "TEXT",
                "wordLabel": "", "fieldCode": "", "dataType": "string",
                "sourceType": "LIMS", "controlTag": "", "enabled": True,
            })
            self.assertEqual(mapping["wordLabel"], "试验过程字段")
            self.assertEqual(mapping["fieldCode"], "report.s7_1.试验过程.试验过程字段")
            self.assertEqual(mapping["controlTag"], "cc.report.s7_1.试验过程.试验过程字段")
            self.assertEqual(
                mapping["locationId"],
                "word.content_control.cc.report.s7_1.试验过程.试验过程字段",
            )

    def test_block_and_field_order_is_persisted_in_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.repository(directory)
            chapters = repository.list_template_chapters()
            blocks = repository.list_content_blocks()
            chapter = next(
                item for item in chapters
                if len([block for block in blocks if block["chapterId"] == item["id"]]) >= 2
            )
            chapter_blocks = [block for block in blocks if block["chapterId"] == chapter["id"]]
            reversed_blocks = [block["id"] for block in reversed(chapter_blocks)]
            repository.reorder_content_blocks(chapter["id"], reversed_blocks)
            self.assertEqual(
                [
                    block["id"] for block in repository.list_content_blocks()
                    if block["chapterId"] == chapter["id"]
                ],
                reversed_blocks,
            )

            field_block = next(block for block in repository.list_content_blocks() if len(block["mappingIds"]) >= 2)
            reversed_fields = list(reversed(field_block["mappingIds"]))
            repository.reorder_block_mappings(field_block["id"], reversed_fields)
            snapshot = repository.snapshot()
            repository._restore_snapshot(snapshot)
            restored = next(
                block for block in repository.list_content_blocks() if block["id"] == field_block["id"]
            )
            self.assertEqual(restored["mappingIds"], reversed_fields)

    def test_column_repeat_block_clones_word_prototype_row(self) -> None:
        settings = get_settings()
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            repository = self.repository(directory)
            snapshot = repository.snapshot()
            compiled = output_dir / "compiled.docx"
            report = compile_template(
                settings.template_path, compiled, snapshot["mappings"], snapshot["tableRules"]
            )
            self.assertTrue(report["valid"], report["errors"][:3])
            records = [
                {"name": f"Column {index}", "specification": f"Spec {index}",
                 "serialNo": f"SN-{index}", "manufacturer": f"Maker {index}", "stationaryPhase": "C18"}
                for index in range(1, 4)
            ]
            output = output_dir / "columns.docx"
            build_mapped_docx(compiled, output, snapshot["mappings"], {"columns": records}, {})
            with ZipFile(output) as archive:
                document = etree.fromstring(archive.read("word/document.xml"))
            rows = document.xpath("./w:body/w:tbl", namespaces=NS)[7].xpath("./w:tr", namespaces=NS)
            row_texts = [
                "|".join(
                    "".join(cell.xpath(".//w:t/text()", namespaces=NS))
                    for cell in row.xpath("./w:tc", namespaces=NS)
                )
                for row in rows
            ]
            generated = [text for text in row_texts if any(f"SN-{index}" in text for index in range(1, 4))]
            self.assertEqual(len(generated), 3)

    def test_repeat_row_preserves_static_text_outside_bound_control(self) -> None:
        settings = get_settings()
        with tempfile.TemporaryDirectory() as directory:
            repository = self.repository(directory)
            snapshot = repository.snapshot()
            compiled = Path(directory) / "compiled.docx"
            report = compile_template(
                settings.template_path, compiled, snapshot["mappings"], snapshot["tableRules"]
            )
            self.assertTrue(report["valid"], report["errors"][:3])
            output = Path(directory) / "samples.docx"
            build_mapped_docx(compiled, output, snapshot["mappings"], {
                "samples": [{
                    "sampleName": "供试品", "batchNo": "B-01", "specification": "1g",
                    "clientName": "测试科技", "remark": "-",
                }],
            }, {})
            with ZipFile(output) as archive:
                document = etree.fromstring(archive.read("word/document.xml"))
            sample_table = document.xpath("./w:body/w:tbl", namespaces=NS)[4]
            generated_text = "".join(sample_table.xpath(".//w:t/text()", namespaces=NS))
            self.assertIn("测试科技（上海）有限公司", generated_text)

    def test_compiler_accepts_an_interactively_bound_content_control(self) -> None:
        settings = get_settings()
        with tempfile.TemporaryDirectory() as directory:
            repository = self.repository(directory)
            snapshot = repository.snapshot()
            first_output = Path(directory) / "first.docx"
            first_report = compile_template(
                settings.template_path, first_output, snapshot["mappings"], snapshot["tableRules"]
            )
            self.assertTrue(first_report["valid"], first_report["errors"][:3])
            mapping = next(
                item for item in snapshot["mappings"]
                if item.get("enabled") and item.get("controlTag")
                and any(success.get("controlTag") == item["controlTag"] for success in first_report["success"])
            )
            rebound = dict(mapping, locationId=f"contentControl.{mapping['controlTag']}")
            second_output = Path(directory) / "second.docx"
            second_report = compile_template(first_output, second_output, [rebound], snapshot["tableRules"])
            self.assertTrue(second_report["valid"], second_report["errors"])
            self.assertEqual(second_report["success"][0]["action"], "existing-content-control")


if __name__ == "__main__":
    unittest.main()
