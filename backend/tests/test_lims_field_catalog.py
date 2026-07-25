import tempfile
import unittest
from pathlib import Path

from backend.app.database import Database
from backend.app.services.lims_configured_extractor import apply_configured_extraction


class LimsFieldCatalogTest(unittest.TestCase):
    def test_field_and_extraction_rule_crud(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            field = database.upsert_lims_field({
                "fieldCode": "samples.batchNo", "label": "供试品批号",
                "groupCode": "samples", "collectionCode": "samples",
                "dataType": "string", "cardinality": "MANY",
                "dbTable": "lims_standard_records", "dbColumn": "data_json",
                "jsonKey": "batchNo", "legacyJsonPath": "$.samples[*].batchNo",
                "description": "供试品生产批号", "outputFormat": "",
                "defaultValue": "", "validationRegex": "", "orderNo": 10,
                "enabled": True,
            })
            self.assertEqual(field["description"], "供试品生产批号")
            rule = database.save_lims_extraction_rule({
                "fieldCode": field["fieldCode"], "name": "原始样品批号",
                "sourceType": "RAW_UNIT_FIELD", "sourceUnitType": "Sample",
                "sourcePath": "batchNo", "transform": "TRIM", "priority": 10,
                "config": {}, "enabled": True,
            })
            self.assertEqual(database.list_lims_extraction_rules(field["fieldCode"])[0]["id"], rule["id"])
            self.assertTrue(database.delete_lims_extraction_rule(rule["id"]))
            self.assertTrue(database.delete_lims_field(field["fieldCode"]))

    def test_raw_unit_rule_writes_many_standard_values(self) -> None:
        fields = [{
            "fieldCode": "samples.batchNo", "legacyJsonPath": "$.samples[*].batchNo",
            "dataType": "string", "cardinality": "MANY", "defaultValue": "",
            "validationRegex": "", "enabled": True,
        }]
        rules = [{
            "fieldCode": "samples.batchNo", "sourceType": "RAW_UNIT_FIELD",
            "sourceUnitType": "Sample", "sourcePath": "batchNo", "valuePattern": "",
            "transform": "TRIM", "priority": 10, "enabled": True,
        }]
        instance = {"rawStructured": [
            {"unitType": "Sample", "data": {"batchNo": " A-01 "}},
            {"unitType": "Sample", "data": {"batchNo": "B-02"}},
        ]}
        payload = {"samples": [{"sampleName": "样品一"}, {"sampleName": "样品二"}]}
        apply_configured_extraction(instance, payload, fields, rules)
        self.assertEqual([item["batchNo"] for item in payload["samples"]], ["A-01", "B-02"])

    def test_rich_text_regex_and_output_format(self) -> None:
        fields = [{
            "fieldCode": "project.dailyDose", "legacyJsonPath": "$.project.dailyDose",
            "dataType": "decimal", "cardinality": "ONE", "outputFormat": "2",
            "defaultValue": "", "validationRegex": "", "enabled": True,
        }]
        rules = [{
            "fieldCode": "project.dailyDose", "sourceType": "RICH_TEXT_REGEX",
            "sectionPattern": "实验设计", "valuePattern": r"最大日剂量[:：]\s*([0-9.]+)",
            "transform": "NUMBER", "priority": 10, "enabled": True,
        }]
        instance = {"richTexts": [{"sectionPath": ["实验设计"], "plainText": "最大日剂量：12.5"}]}
        payload = {"project": {}}
        apply_configured_extraction(instance, payload, fields, rules)
        self.assertEqual(payload["project"]["dailyDose"], "12.50")


if __name__ == "__main__":
    unittest.main()
