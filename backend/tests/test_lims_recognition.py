import unittest
import tempfile
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from backend.app.config import get_settings
from backend.app.database import Database
from backend.app.services.lims_excel import parse_lims_workbook
from backend.app.services.lims_normalizer import COLLECTION_ORDER, merge_instances, normalize_instance
from backend.app.services.mapped_docx_generator import build_mapped_docx
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.template_compiler import compile_template


ROOT = Path(__file__).resolve().parents[2]
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


class LimsRecognitionRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        files = sorted((ROOT / "data" / "lims").glob("*.xlsx"))
        if not files:
            raise unittest.SkipTest("No imported LIMS workbook is available")
        cls.workbook = files[0]
        cls.primary_ids = ["20251100071", "20251100085"]
        cls.instances = [parse_lims_workbook(cls.workbook, value) for value in cls.primary_ids]

    def test_workbook_inventory_and_validation_sections(self) -> None:
        summary = parse_lims_workbook(self.workbook)
        self.assertEqual(summary["rowCount"], 183)
        self.assertEqual(summary["instanceCount"], 6)
        recognition = merge_instances(self.instances)
        for collection in (
            "samples", "instruments", "columns", "impurity", "validationSummary", "solutions",
            "methodParameters", "systemSuitability", "specificity", "lod", "loq", "linearity",
            "repeatability", "intermediatePrecision", "accuracy", "solutionStability", "sampleResults",
        ):
            self.assertGreater(recognition["recognizedCounts"].get(collection, 0), 0, collection)
        self.assertGreater(recognition["duplicateCount"], 0)
        self.assertGreater(recognition["unresolvedConflictCount"], 0)
        self.assertEqual(recognition["coverage"]["unmatchedTables"], 1)

    def test_conflicts_require_explicit_resolution(self) -> None:
        preview = merge_instances(self.instances)
        resolutions = {item["id"]: item["options"][0]["candidateId"] for item in preview["conflicts"]}
        resolved = merge_instances(self.instances, resolutions)
        self.assertEqual(resolved["unresolvedConflictCount"], 0)
        identities = [(item.get("sampleName"), item.get("batchNo")) for item in resolved["payload"]["samples"]]
        self.assertEqual(len(identities), len(set(identities)))

    def test_cross_project_merge_is_rejected(self) -> None:
        other = dict(self.instances[1])
        other["projectId"] = "OTHER-PROJECT"
        with self.assertRaisesRegex(ValueError, "同一项目"):
            merge_instances([self.instances[0], other])

    def test_normalized_instances_are_persisted_and_reloaded_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "lims.db")
            database.initialize()
            summary = parse_lims_workbook(self.workbook)
            import_id = "test-import"
            database.create_lims_import({
                "id": import_id, "file_name": self.workbook.name, "stored_name": self.workbook.name,
                "size": self.workbook.stat().st_size, "summary": summary, "created_at": "2026-01-01T00:00:00Z",
            })
            for raw in self.instances:
                database.replace_lims_instance(import_id, raw, normalize_instance(raw), COLLECTION_ORDER)
            stored = [database.get_lims_instance_payload(import_id, value) for value in self.primary_ids]
            self.assertTrue(all(stored))
            self.assertGreater(len(database.list_lims_standard_records(import_id, self.primary_ids[0])), 0)
            recognition = merge_instances(stored)  # type: ignore[arg-type]
            self.assertGreater(recognition["recognizedTotal"], 0)
            self.assertEqual(recognition["coverage"]["unmatchedTables"], 1)

    def test_blank_template_removes_example_data_and_fill_writes_lims_values(self) -> None:
        settings = get_settings()
        database = Database(settings.database_path)
        database.initialize()
        repository = RuleAdminRepository(database, ROOT / "mapping" / "template-mapping.json")
        repository.seed()
        snapshot = repository.snapshot()
        compiled = ROOT / ".tmp" / "test-compiled-template.docx"
        report = compile_template(settings.template_path, compiled, snapshot["mappings"], snapshot["tableRules"])
        self.assertTrue(report["valid"], report["errors"])

        report_data = {"template_version": "V1.0", "field_sources": {}, "original_values": {},
                       "source_payloads": {}}
        blank = ROOT / ".tmp" / "test-blank-template.docx"
        build_mapped_docx(compiled, blank, snapshot["mappings"], {}, report_data)
        blank_text = self._document_text(blank)
        for old_value in ("氢氯噻嗪片", "6.439", "乙腈（含0.1%甲酸）"):
            self.assertNotIn(old_value, blank_text)
        self._assert_external_example_objects_removed(blank)

        preview = merge_instances(self.instances)
        resolutions = {item["id"]: item["options"][0]["candidateId"] for item in preview["conflicts"]}
        payload = merge_instances(self.instances, resolutions)["payload"]
        filled = ROOT / ".tmp" / "test-filled-template.docx"
        build_mapped_docx(compiled, filled, snapshot["mappings"], payload, report_data)
        filled_text = self._document_text(filled)
        self.assertIn(payload["samples"][0]["sampleName"], filled_text)
        self.assertIn(payload["instruments"][0]["instrumentName"], filled_text)
        self.assertIn(payload["solutions"][0]["name"], filled_text)
        self._assert_external_example_objects_removed(filled)

    @staticmethod
    def _document_text(path: Path) -> str:
        with ZipFile(path) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        return "\n".join(root.xpath(".//w:t/text()", namespaces=NS))

    def _assert_external_example_objects_removed(self, path: Path) -> None:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            root = etree.fromstring(archive.read("word/document.xml"))
        tables = root.xpath("./w:body/w:tbl", namespaces=NS)
        for table_number in (3, 20, 24):
            objects = tables[table_number - 1].xpath(
                ".//w:drawing | .//w:pict | .//w:object", namespaces=NS
            )
            self.assertEqual(objects, [], f"table {table_number} still contains an external object")
        for old_part in (
            "word/media/image1.emf", "word/media/image2.png", "word/media/image3.png",
            "word/media/image4.png", "word/media/image5.png", "word/embeddings/oleObject1.bin",
        ):
            self.assertNotIn(old_part, names)


if __name__ == "__main__":
    unittest.main()
