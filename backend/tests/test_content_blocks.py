import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from backend.app.config import get_settings
from backend.app.services.mapped_docx_generator import build_mapped_docx
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.template_compiler import compile_template
from backend.app.services.docx_repeat_rows import fill_repeat_rows
from backend.app.services.table_layout_rules import TableLayoutRules
from backend.tests.database_helpers import make_test_database


ROOT = Path(__file__).resolve().parents[2]
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class ContentBlockRegressionTest(unittest.TestCase):
    def repository(self, directory: str) -> RuleAdminRepository:
        database = make_test_database(Path(directory))
        database.initialize()
        repository = RuleAdminRepository(database, ROOT / "mapping" / "template-mapping.json")
        repository.seed()
        return repository

    def test_blocks_are_persisted_with_fields_in_version_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.repository(directory)
            chapter = next(item for item in repository.list_template_chapters() if item["code"] == "4.4")
            block = repository.save_template_block(repository.active_workspace()["versionId"], {
                "chapterId": chapter["id"], "standardGroupCode": "columns", "title": "色谱柱信息",
                "kind": "REPEATING_TABLE", "tableNo": "T99", "sourcePath": "$.columns",
                "repeatKey": "name", "prototypeLocation": "body.T99.dataRow", "dedupKey": "name",
                "sortRule": "name ASC", "emptyBehavior": "KEEP", "mergeRule": "NONE", "enabled": True,
            })
            snapshot = repository.snapshot()
            saved = next(item for item in snapshot["templateBlocks"]
                         if item["standardGroupCode"] == block["standardGroupCode"])
            self.assertEqual(saved["sourcePath"], "$.columns")
            repository._restore_snapshot(snapshot, repository.active_workspace()["versionId"])
            restored = next(item for item in repository.list_template_blocks(
                repository.active_workspace()["versionId"]
            ) if item["standardGroupCode"] == "columns")
            self.assertEqual(restored["repeatKey"], "name")

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
            active = repository.active_workspace()
            chapter = next(item for item in repository.list_template_chapters() if item["code"] == "4.1")
            repository.save_template_block(active["versionId"], {
                "chapterId": chapter["id"], "standardGroupCode": "samples",
                "title": "样品信息", "orderNo": 7, "enabled": True,
            })
            snapshot = repository.snapshot()
            repository._restore_snapshot(snapshot, active["versionId"])
            restored = next(item for item in repository.list_template_blocks(active["versionId"])
                            if item["standardGroupCode"] == "samples")
            self.assertEqual(restored["orderNo"], 7)

    def test_column_repeat_block_clones_word_prototype_row(self) -> None:
        settings = get_settings()
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            repository = self.repository(directory)
            snapshot = repository.snapshot()
            column_paths = {
                "columns[].field1": "$.columns[*].name",
                "columns[].field2": "$.columns[*].injections[*].specification",
                "columns[].serialNo": "$.columns[*].injections[*].serialNo",
                "columns[].manufacturer": "$.columns[*].injections[*].manufacturer",
                "columns[].field5": "$.columns[*].injections[*].stationaryPhase",
            }
            mappings = [
                {**item, "groupItemPath": "$.columns[*]", "sourcePath": column_paths[item["fieldCode"]],
                 "sourcePending": False}
                for item in snapshot["mappings"] if item.get("tableNo") == "T8"
            ]
            self.assertEqual(len(mappings), 5)
            compiled = output_dir / "compiled.docx"
            report = compile_template(
                settings.template_path, compiled, mappings, snapshot["tableRules"]
            )
            self.assertTrue(report["valid"], report["errors"][:3])
            records = [
                {"name": f"Column {index}",
                 "injections": [{"specification": f"Spec {index}",
                                 "serialNo": f"SN-{index}",
                                 "manufacturer": f"Maker {index}",
                                 "stationaryPhase": "C18"}]}
                for index in range(1, 4)
            ]
            output = output_dir / "columns.docx"
            build_mapped_docx(compiled, output, mappings, {"columns": records}, {}, snapshot["tableRules"])
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
            sample_paths = {
                "samples[].sampleName": "$.samples[*].injections[*].sampleName",
                "samples[].batchNo": "$.samples[*].batchNo",
                "samples[].field3": "$.samples[*].injections[*].field3",
                "samples[].field4": "$.samples[*].injections[*].clientName",
                "samples[].field5": "$.samples[*].injections[*].remark",
            }
            mappings = [
                {**item, "groupItemPath": "$.samples[*]", "sourcePath": sample_paths[item["fieldCode"]],
                 "sourcePending": False}
                for item in snapshot["mappings"] if item.get("tableNo") == "T5"
            ]
            compiled = Path(directory) / "compiled.docx"
            report = compile_template(
                settings.template_path, compiled, mappings, snapshot["tableRules"]
            )
            self.assertTrue(report["valid"], report["errors"][:3])
            output = Path(directory) / "samples.docx"
            build_mapped_docx(compiled, output, mappings, {
                "samples": [{
                    "batchNo": "B-01", "injections": [{
                        "sampleName": "供试品", "field3": "1g",
                        "clientName": "测试科技（上海）有限公司", "remark": "-",
                    }],
                }],
            }, {}, snapshot["tableRules"])
            with ZipFile(output) as archive:
                document = etree.fromstring(archive.read("word/document.xml"))
            sample_table = document.xpath("./w:body/w:tbl", namespaces=NS)[4]
            generated_text = "".join(sample_table.xpath(".//w:t/text()", namespaces=NS))
            self.assertIn("测试科技（上海）有限公司", generated_text)

    def test_flat_detail_collection_expands_rows(self) -> None:
        document = etree.fromstring(f'''<w:document xmlns:w="{NS['w']}"><w:body>
          <w:tbl><w:tr><w:bookmarkStart w:id="1" w:name="repeat_t17_row"/>
            <w:tc><w:sdt><w:sdtPr><w:tag w:val="lod.name"/></w:sdtPr>
              <w:sdtContent><w:p><w:r><w:t>原型</w:t></w:r></w:p></w:sdtContent></w:sdt></w:tc>
          </w:tr></w:tbl></w:body></w:document>''')
        mappings = [{
            "enabled": True, "repeatType": "ROW", "tableNo": "T17",
            "blockSourcePath": "$.jiancexian[*]", "sourcePath": "$.jiancexian[*].name",
            "controlTag": "lod.name", "fieldCode": "lod[].name",
        }]
        fill_repeat_rows(document, mappings, {"jiancexian": [{"name": "杂质A"}, {"name": "杂质B"}]},
                         {}, {}, TableLayoutRules([]), lambda *_args: None)
        rows = document.xpath(".//w:tbl/w:tr", namespaces=NS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            ["".join(row.xpath(".//w:t/text()", namespaces=NS)) for row in rows],
            ["杂质A", "杂质B"],
        )

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

    def test_table_repeat_groups_records_and_clones_only_the_table(self) -> None:
        document = etree.fromstring(f'''<w:document xmlns:w="{NS['w']}"><w:body>
          <w:p><w:r><w:t>统一接受标准</w:t></w:r></w:p>
          <w:tbl><w:tr><w:bookmarkStart w:id="1" w:name="repeat_t99_row"/>
            <w:tc><w:sdt><w:sdtPr><w:tag w:val="result.name"/></w:sdtPr>
              <w:sdtContent><w:p><w:r><w:t>原型</w:t></w:r></w:p></w:sdtContent></w:sdt></w:tc>
          </w:tr></w:tbl></w:body></w:document>''')
        mappings = [{
            "enabled": True, "repeatType": "ROW", "tableNo": "T99",
            "blockSourcePath": "$.results[*]", "sourcePath": "$.results[*].value",
            "controlTag": "result.name", "fieldCode": "results[].value",
        }]
        rules = TableLayoutRules([{
            "tableNo": "T99", "mode": "TABLE_REPEAT", "groupKey": "impurityName",
            "innerMode": "ROW_REPEAT", "preservedRowLabels": [],
        }])
        warnings = []
        fill_repeat_rows(document, mappings, {"results": [
            {"impurityName": "杂质A", "value": "A-1"},
            {"impurityName": "杂质A", "value": "A-2"},
            {"impurityName": "杂质B", "value": "B-1"},
        ]}, {}, {}, rules, lambda *args: warnings.append(args))
        tables = document.xpath("./w:body/w:tbl", namespaces=NS)
        self.assertEqual(len(tables), 2)
        self.assertIn("A-1", "".join(tables[0].xpath(".//w:t/text()", namespaces=NS)))
        self.assertIn("A-2", "".join(tables[0].xpath(".//w:t/text()", namespaces=NS)))
        self.assertNotIn("B-1", "".join(tables[0].xpath(".//w:t/text()", namespaces=NS)))
        self.assertIn("B-1", "".join(tables[1].xpath(".//w:t/text()", namespaces=NS)))
        children = document.xpath("./w:body/*", namespaces=NS)
        word_tag = f"{{{NS['w']}}}"
        self.assertEqual(
            [item.tag for item in children],
            [word_tag + "p", word_tag + "tbl", word_tag + "p", word_tag + "tbl"],
        )
        self.assertEqual(children[2].xpath(".//w:t/text()", namespaces=NS), [])
        self.assertFalse(warnings)

    def test_table_repeat_clones_adjacent_bound_group_heading(self) -> None:
        document = etree.fromstring(f'''<w:document xmlns:w="{NS['w']}"><w:body>
          <w:sdt><w:sdtPr><w:tag w:val="result.impurity"/></w:sdtPr><w:sdtContent>
            <w:p><w:r><w:t>原型标题</w:t></w:r></w:p>
          </w:sdtContent></w:sdt>
          <w:tbl><w:tr><w:bookmarkStart w:id="1" w:name="repeat_t99_row"/>
            <w:tc><w:sdt><w:sdtPr><w:tag w:val="result.value"/></w:sdtPr>
              <w:sdtContent><w:p><w:r><w:t>原型数据</w:t></w:r></w:p></w:sdtContent></w:sdt></w:tc>
          </w:tr></w:tbl></w:body></w:document>''')
        mappings = [
            {
                "enabled": True, "repeatType": "ROW", "tableNo": "T99",
                "groupItemPath": "$.results[*]", "sourcePath": "$.results[*].impurityName",
                "controlTag": "result.impurity", "fieldCode": "results[].impurityName",
            },
            {
                "enabled": True, "repeatType": "ROW", "tableNo": "T99",
                "groupItemPath": "$.results[*]", "sourcePath": "$.results[*].value",
                "controlTag": "result.value", "fieldCode": "results[].value",
            },
        ]
        rules = TableLayoutRules([{
            "tableNo": "T99", "mode": "TABLE_REPEAT", "groupKey": "impurityName",
            "innerMode": "ROW_REPEAT", "preservedRowLabels": [],
        }])
        warnings = []
        fill_repeat_rows(document, mappings, {"results": [
            {"impurityName": "杂质A", "value": "A-1"},
            {"impurityName": "杂质A", "value": "A-2"},
            {"impurityName": "杂质B", "value": "B-1"},
        ]}, {}, {}, rules, lambda *args: warnings.append(args))
        children = document.xpath("./w:body/*", namespaces=NS)
        word_tag = f"{{{NS['w']}}}"
        self.assertEqual(
            [item.tag for item in children],
            [word_tag + "sdt", word_tag + "tbl", word_tag + "p",
             word_tag + "sdt", word_tag + "tbl"],
        )
        self.assertEqual("".join(children[0].xpath(".//w:t/text()", namespaces=NS)), "杂质A")
        self.assertIn("A-2", "".join(children[1].xpath(".//w:t/text()", namespaces=NS)))
        self.assertEqual(children[2].xpath(".//w:t/text()", namespaces=NS), [])
        self.assertEqual("".join(children[3].xpath(".//w:t/text()", namespaces=NS)), "杂质B")
        self.assertIn("B-1", "".join(children[4].xpath(".//w:t/text()", namespaces=NS)))
        self.assertFalse(warnings)


if __name__ == "__main__":
    unittest.main()
