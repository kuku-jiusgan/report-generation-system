"""表格布局规则必须完全来自设计器配置，后端不得再内置表号特例。"""

import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree

from backend.app.database import Database
from backend.app.database_designer_migrations import SEED_MATRIX_LAYOUT
from backend.app.services.mapped_docx_generator import build_mapped_docx
from backend.app.services.table_layout_rules import TableLayoutRules
from backend.app.services.template_compiler import compile_template


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _repeat_template(path: Path) -> None:
    """两列一行的循环表：首行表头，第二行是带控件的原型行，第三行是结论汇总行。"""
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    for index, cells in enumerate((("名称", "编号"), ("", ""), ("结论", ""))):
        row = etree.SubElement(table, W + "tr")
        if index == 1:
            etree.SubElement(row, W + "bookmarkStart", {W + "id": "2000", W + "name": "repeat_t1_row"})
        for column, text in enumerate(cells):
            cell = etree.SubElement(row, W + "tc")
            if index == 1:
                sdt = etree.SubElement(cell, W + "sdt")
                properties = etree.SubElement(sdt, W + "sdtPr")
                etree.SubElement(properties, W + "tag", {W + "val": f"repeat.t1.field{column + 1}"})
                content = etree.SubElement(sdt, W + "sdtContent")
                cell = content
            paragraph = etree.SubElement(cell, W + "p")
            run = etree.SubElement(paragraph, W + "r")
            etree.SubElement(run, W + "t").text = text
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True,
        ))


def _mappings(**block: object) -> list[dict]:
    base = {"enabled": True, "repeatType": "ROW", "tableNo": "T1", "sourceType": "LIMS", **block}
    return [
        {**base, "controlTag": "repeat.t1.field1", "fieldCode": "demo.name",
         "wordLabel": "名称", "sourcePath": "$.demo[*].name"},
        {**base, "controlTag": "repeat.t1.field2", "fieldCode": "demo.code",
         "wordLabel": "编号", "sourcePath": "$.demo[*].code"},
    ]


def _rows(path: Path) -> list[list[str]]:
    root = etree.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    return [["".join(cell.xpath(".//w:t/text()", namespaces=NS))
             for cell in row.xpath("./w:tc", namespaces=NS)]
            for row in root.xpath(".//w:tbl/w:tr", namespaces=NS)]


class TableLayoutRulesTest(unittest.TestCase):
    def test_missing_rule_yields_no_implicit_defaults(self) -> None:
        layout = TableLayoutRules([])
        self.assertEqual(0, layout.physical_index("T1"))
        self.assertEqual((), layout.preserved_row_labels("T1"))
        self.assertFalse(layout.is_matrix("T1"))
        self.assertIsNone(layout.matrix_layout("T1"))

    def test_invalid_matrix_layout_json_is_reported_as_missing(self) -> None:
        layout = TableLayoutRules([{"tableNo": "T1", "mode": "MATRIX", "matrixLayout": "{不是JSON"}])
        self.assertTrue(layout.is_matrix("T1"))
        self.assertIsNone(layout.matrix_layout("T1"))


class RepeatRowConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.template = Path(self.directory.name) / "template.docx"
        self.output = Path(self.directory.name) / "out.docx"
        _repeat_template(self.template)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_block_source_path_drives_the_collection(self) -> None:
        """内容块的循环数据集合就是唯一来源，不存在后台改道表。"""
        mappings = _mappings(blockSourcePath="$.demo[*]", contentBlockKind="REPEATING_TABLE")
        payload = {"demo": [{"name": "甲", "code": "A-1"}, {"name": "乙", "code": "A-2"}]}
        report: dict = {}

        build_mapped_docx(self.template, self.output, mappings, payload, report,
                          [{"tableNo": "T1", "mode": "ROW_REPEAT", "enabled": True}])

        rows = _rows(self.output)
        self.assertEqual(["甲", "A-1"], rows[1])
        self.assertEqual(["乙", "A-2"], rows[2])
        self.assertEqual([], report.get("warnings", []))

    def test_preserved_row_labels_come_from_the_table_rule(self) -> None:
        mappings = _mappings(blockSourcePath="$.demo[*]", contentBlockKind="REPEATING_TABLE")
        payload = {"demo": [{"name": "甲", "code": "A-1"}]}

        build_mapped_docx(self.template, self.output, mappings, payload, {},
                          [{"tableNo": "T1", "mode": "ROW_REPEAT", "enabled": True,
                            "preservedRowLabels": ["结论"]}])

        self.assertEqual(["结论", ""], _rows(self.output)[-1])

    def test_summary_row_is_dropped_when_label_not_configured(self) -> None:
        mappings = _mappings(blockSourcePath="$.demo[*]", contentBlockKind="REPEATING_TABLE")
        payload = {"demo": [{"name": "甲", "code": "A-1"}]}

        build_mapped_docx(self.template, self.output, mappings, payload, {},
                          [{"tableNo": "T1", "mode": "ROW_REPEAT", "enabled": True,
                            "preservedRowLabels": []}])

        self.assertEqual(2, len(_rows(self.output)))

    def test_matrix_without_layout_keeps_template_content_and_warns(self) -> None:
        """用户选择“只警告不拦截”：配置不全时保留 Word 原文，并写出可见警告。"""
        mappings = _mappings(blockSourcePath="$.demo[*]", contentBlockKind="MATRIX")
        report: dict = {}

        build_mapped_docx(self.template, self.output, mappings, {"demo": []}, report,
                          [{"tableNo": "T1", "mode": "MATRIX", "enabled": True, "matrixLayout": ""}])

        self.assertEqual(["结论", ""], _rows(self.output)[-1], "原有汇总行必须保留")
        self.assertTrue(any("矩阵版式" in item for item in report["warnings"]))

    def test_field_pointing_at_another_collection_is_skipped_with_warning(self) -> None:
        mappings = _mappings(blockSourcePath="$.demo[*]", contentBlockKind="REPEATING_TABLE")
        mappings[1]["sourcePath"] = "$.other[*].code"
        report: dict = {}

        build_mapped_docx(self.template, self.output, mappings, {"demo": [{"name": "甲", "code": "A-1"}]},
                          report, [{"tableNo": "T1", "mode": "ROW_REPEAT", "enabled": True}])

        self.assertEqual("甲", _rows(self.output)[1][0])
        self.assertTrue(any("与本表的数据集合" in item for item in report["warnings"]))


class CompileAuditTest(unittest.TestCase):
    def test_compile_warns_about_missing_layout_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "template.docx"
            _repeat_template(template)
            mappings = _mappings(blockSourcePath="$.demo[*]", locationId="body.T1.dataRow.cell1")
            report = compile_template(template, Path(directory) / "compiled.docx", mappings,
                                      [{"tableNo": "T1", "mode": "MATRIX", "enabled": True,
                                        "physicalTableIndex": 0, "matrixLayout": ""}])

            codes = {item.get("code") for item in report["warnings"]}
            self.assertIn("PHYSICAL_TABLE_INDEX_MISSING", codes)
            self.assertIn("MATRIX_LAYOUT_MISSING", codes)


class MigrationSeedTest(unittest.TestCase):
    def test_existing_table_rules_get_visible_layout_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seed.db"
            database = Database(path)
            database.initialize()
            with database.connect() as connection:
                connection.execute(
                    "INSERT INTO admin_table_rules(table_no,section_code,mode,updated_at) "
                    "VALUES('T20','7.4.linearity','MATRIX','now')"
                )
                connection.execute("DELETE FROM app_migrations")
            Database(path).initialize()

            with sqlite3.connect(path) as connection:
                connection.row_factory = sqlite3.Row
                row = dict(connection.execute(
                    "SELECT * FROM admin_table_rules WHERE table_no='T20'"
                ).fetchone())

            self.assertEqual(20, row["physical_table_index"])
            self.assertTrue(row["clear_embedded_objects"])
            self.assertIn("结论", row["preserved_row_labels"])
            layout = TableLayoutRules([{"tableNo": "T20", "matrixLayout": row["matrix_layout"]}])
            self.assertEqual(SEED_MATRIX_LAYOUT, layout.matrix_layout("T20"))


if __name__ == "__main__":
    unittest.main()
