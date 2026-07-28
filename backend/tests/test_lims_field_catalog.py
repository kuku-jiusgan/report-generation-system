import tempfile
import unittest
from pathlib import Path

from backend.app.database import Database
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.lims_configured_extractor import apply_configured_extraction
from backend.app.services.lims_normalizer import normalize_instance


class LimsFieldCatalogTest(unittest.TestCase):
    def test_catalog_uses_live_report_chapter_hierarchy_and_mapping_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            repository = RuleAdminRepository(database, Path(directory) / "unused.json")
            parent_a = repository.create_template_chapter({
                "code": "4", "title": "物料及仪器信息", "orderNo": 4,
            })
            parent_b = repository.create_template_chapter({
                "code": "7", "title": "验证内容", "orderNo": 7,
            })
            child = repository.create_template_chapter({
                "parentId": parent_a["id"], "code": "4.3", "title": "仪器", "orderNo": 3,
            })
            database.upsert_lims_field({
                "fieldCode": "instruments.instrumentName", "label": "仪器名称",
                "groupCode": "仪器信息", "collectionCode": "instruments",
                "dataType": "string", "cardinality": "MANY",
                "dbTable": "lims_standard_records", "dbColumn": "data_json",
                "jsonKey": "instrumentName", "legacyJsonPath": "$.instruments[*].instrumentName",
                "description": "", "outputFormat": "", "defaultValue": "",
                "validationRegex": "", "orderNo": 1, "enabled": True,
            })
            repository.create_mapping({
                "chapterId": child["id"], "standardFieldCode": "instruments.instrumentName",
                "wordLabel": "仪器名称", "fieldCode": "instrument.name",
                "sectionCode": "4.3", "tableNo": "TEXT", "dataType": "string",
                "sourceType": "LIMS", "sourcePath": "$.instruments[*].instrumentName",
                "repeatType": "NONE", "mergeRule": "PRESERVE", "fillRule": "TEXT",
                "enabled": True,
            })

            initial = repository.standard_field_catalog()
            self.assertEqual(initial["chapters"][0]["children"][0]["title"], "仪器")
            self.assertEqual(
                initial["chapters"][0]["children"][0]["fields"][0]["fieldCode"],
                "instruments.instrumentName",
            )

            repository.update_template_chapter(child["id"], {
                "parentId": parent_b["id"], "title": "仪器与设备", "orderNo": 1,
            })
            updated = repository.standard_field_catalog()
            validation_chapter = next(item for item in updated["chapters"] if item["code"] == "7")
            self.assertEqual(validation_chapter["children"][0]["title"], "仪器与设备")
            self.assertEqual(validation_chapter["children"][0]["fields"][0]["label"], "仪器名称")

    def test_field_source_always_returns_all_items_for_unit_id_as_array(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            imported = database.create_lims_import({
                "id": "import-rich", "file_name": "lims.xlsx", "stored_name": "lims.xlsx",
                "size": 10, "summary": {}, "created_at": "2026-01-01T00:00:00",
            })
            database.replace_lims_instance(
                imported["id"],
                {"instanceId": "EXP-RICH", "title": "富文本实验", "rawStructured": [],
                 "richTexts": [{"id": "UNIT-RICH", "plainText": "目标表格", "html": "<table></table>",
                                 "evidence": {"unitId": "UNIT-RICH", "unitType": "RichText"}}]},
                {"project": {}, "document": {}, "methodParameters": [{
                    "field1": "流速", "field2": "1.0 mL/min",
                    "evidence": {"unitId": "UNIT-RICH", "richTextId": "UNIT-RICH", "tableIndex": 1},
                }]},
                ["methodParameters"],
            )
            record = database.list_lims_standard_records(imported["id"], "EXP-RICH")[0]
            source = database.get_lims_field_source(
                {"fieldCode": "methodParameters.field1", "collectionCode": "methodParameters"},
                imported["id"], "EXP-RICH", record["recordKey"],
            )
            self.assertEqual(source["matchedBy"], "unitId")
            self.assertEqual(source["matchedValue"], "UNIT-RICH")
            self.assertIsInstance(source["source"], list)
            self.assertEqual(len(source["source"]), 1)
            self.assertEqual(source["source"][0]["plainText"], "目标表格")
            parsed_source = database.get_lims_field_instance_source(
                {"fieldCode": "methodParameters.field1", "collectionCode": "methodParameters",
                 "jsonKey": "field1"},
                imported["id"], "EXP-RICH",
            )
            parsed_item = parsed_source["source"]["unitGroups"][0]["sourceItems"][0]
            self.assertEqual(parsed_item["type"], "PARSED_HTML_TABLE")
            self.assertEqual(parsed_item["parsedItems"][0]["value"], "流速")
            self.assertNotIn("plainText", parsed_item)
            self.assertNotIn("html", parsed_item)

    def test_html_table_parser_profile_is_controlled_by_extraction_rule(self) -> None:
        instance = {
            "instanceId": "EXP-TABLE", "title": "方法验证", "project": {}, "document": {},
            "richTexts": [{
                "id": "RICH-1", "sectionPath": ["实验结果", "原始数据与处理结果"],
                "html": """<table><tr><th>No.</th><th>NDMA</th><th>NDMA</th></tr>
                           <tr><th></th><th>保留时间</th><th>峰面积</th></tr>
                           <tr><td>1</td><td>5.9</td><td>100</td></tr></table>""",
                "plainText": "No. NDMA 保留时间 峰面积",
                "evidence": {"unitId": "RICH-1"},
            }],
        }
        rule = {"enabled": False, "config": {
            "parser": "HTML_TABLE_GRID", "parserProfile": "SYSTEM_SUITABILITY_MATRIX",
        }}
        disabled = normalize_instance(instance, extraction_rules=[rule])
        self.assertEqual(disabled["systemSuitability"], [])
        rule["enabled"] = True
        rule["headerPattern"] = "不会匹配的表头"
        mismatched = normalize_instance(instance, extraction_rules=[rule])
        self.assertEqual(mismatched["systemSuitability"], [])
        rule["sectionPattern"] = r"实验结果.*原始数据与处理结果"
        rule["headerPattern"] = r"No\.? .*保留时间.*峰面积".replace(" ", "")
        enabled = normalize_instance(instance, extraction_rules=[rule])
        self.assertEqual(enabled["systemSuitability"][0]["sequence"], "NDMA-1")

    def test_seed_localizes_display_group_without_changing_collection_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            database.upsert_lims_field({
                "fieldCode": "samples.batchNo", "label": "供试品批号",
                "groupCode": "samples", "collectionCode": "samples",
                "dataType": "string", "cardinality": "MANY",
                "dbTable": "lims_standard_records", "dbColumn": "data_json",
                "jsonKey": "batchNo", "legacyJsonPath": "$.samples[*].batchNo",
                "description": "", "outputFormat": "", "defaultValue": "",
                "validationRegex": "", "orderNo": 10, "enabled": True,
            })

            repository = RuleAdminRepository(database, Path(directory) / "unused.json")
            repository._localize_standard_field_groups()

            field = database.get_lims_field("samples.batchNo")
            self.assertEqual(field["groupCode"], "样品信息")
            self.assertEqual(field["collectionCode"], "samples")

    def test_generated_rule_records_upstream_html_parser_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            database.upsert_lims_field({
                "fieldCode": "systemSuitability.peakArea", "label": "峰面积",
                "groupCode": "系统适用性", "collectionCode": "systemSuitability",
                "dataType": "decimal", "cardinality": "MANY",
                "dbTable": "lims_standard_records", "dbColumn": "data_json",
                "jsonKey": "peakArea", "legacyJsonPath": "$.systemSuitability[*].peakArea",
                "description": "", "outputFormat": "", "defaultValue": "",
                "validationRegex": "", "orderNo": 1, "enabled": True,
            })
            database.save_lims_extraction_rule({
                "fieldCode": "systemSuitability.peakArea", "name": "已有标准数据路径",
                "sourceType": "NORMALIZED_PATH", "sourcePath": "$.systemSuitability[*].peakArea",
                "transform": "TRIM", "priority": 100, "config": {}, "enabled": True,
            })
            repository = RuleAdminRepository(database, Path(directory) / "unused.json")
            repository._annotate_lims_extraction_rules()
            rule = database.list_lims_extraction_rules("systemSuitability.peakArea")[0]
            self.assertEqual(rule["name"], "HTML 表格解析 → 标准字段")
            self.assertEqual(rule["config"]["parser"], "HTML_TABLE_GRID")
            self.assertEqual(rule["config"]["parserProfile"], "SYSTEM_SUITABILITY_MATRIX")
            self.assertEqual(rule["config"]["inputField"], "UNITBODY")
            self.assertEqual(rule["config"]["outputField"], "peakArea")
            self.assertIn("保留时间", rule["headerPattern"])

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

    def test_preview_field_returns_recent_standard_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "preview.db")
            database.initialize()
            imported = database.create_lims_import({
                "id": "import-1", "file_name": "lims.xlsx", "stored_name": "lims.xlsx",
                "size": 100, "summary": {}, "created_at": "2026-07-25T08:00:00+00:00",
            })
            database.replace_lims_instance(
                imported["id"],
                {"instanceId": "EXP-1", "title": "亚硝胺验证", "rawStructured": [{
                    "unitType": "Sample", "data": {"sampleName": "供试品A", "batchNo": "B-001"},
                    "evidence": {"unitId": "UNIT-1", "unitType": "Sample"},
                }, {
                    "unitType": "Sample", "data": {"sampleName": "供试品B", "batchNo": "B-002"},
                    "evidence": {"unitId": "UNIT-1", "unitType": "Sample"},
                }], "richTexts": [{"id": "RICH-OTHER", "plainText": "不应返回"}]},
                {"project": {"name": "项目甲"}, "document": {}, "samples": [
                    {"sampleName": "供试品A", "batchNo": "B-001",
                     "evidence": {"unitId": "UNIT-1", "sectionPath": ["实验材料"]}},
                    {"sampleName": "供试品B", "batchNo": "B-002",
                     "evidence": {"unitId": "UNIT-1", "sectionPath": ["实验材料"]}},
                ]},
                ["samples"],
            )
            preview = database.preview_lims_field({
                "fieldCode": "samples.batchNo", "collectionCode": "samples",
                "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "batchNo",
            })
            self.assertEqual(preview["total"], 1)
            self.assertEqual(preview["recognizedTotal"], 2)
            self.assertEqual(preview["items"][0]["value"], ["B-001", "B-002"])
            self.assertEqual(len(preview["items"][0]["recordKeys"]), 2)
            self.assertEqual(preview["items"][0]["fileName"], "lims.xlsx")
            source = database.get_lims_field_source(
                {"fieldCode": "samples.batchNo", "collectionCode": "samples"},
                imported["id"], "EXP-1", preview["items"][0]["recordKey"],
            )
            self.assertEqual(source["matchedBy"], "unitId")
            self.assertEqual(source["matchedValue"], "UNIT-1")
            self.assertEqual(len(source["source"]), 2)
            self.assertEqual(source["source"][0]["data"]["batchNo"], "B-001")
            self.assertEqual(source["source"][1]["data"]["batchNo"], "B-002")
            self.assertNotIn("richTexts", source["source"][0])
            instance_source = database.get_lims_field_instance_source(
                {"fieldCode": "samples.batchNo", "collectionCode": "samples", "jsonKey": "batchNo"},
                imported["id"], "EXP-1",
            )
            self.assertEqual(instance_source["matchedBy"], "instanceId+unitId")
            self.assertEqual(instance_source["source"]["recognizedTotal"], 2)
            self.assertEqual(len(instance_source["source"]["unitGroups"]), 1)
            self.assertEqual(instance_source["source"]["unitGroups"][0]["unitId"], "UNIT-1")
            self.assertEqual(len(instance_source["source"]["unitGroups"][0]["recognizedItems"]), 2)
            self.assertEqual(len(instance_source["source"]["unitGroups"][0]["sourceItems"]), 2)

    def test_preview_deduplicates_reimported_lims_instance_and_keeps_latest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "preview.db")
            database.initialize()
            for import_id, created_at, batch_no in (
                ("import-old", "2026-07-25T08:00:00+00:00", "OLD-001"),
                ("import-new", "2026-07-26T08:00:00+00:00", "NEW-001"),
            ):
                database.create_lims_import({
                    "id": import_id, "file_name": "lims.xlsx", "stored_name": "lims.xlsx",
                    "size": 100, "summary": {}, "created_at": created_at,
                })
                database.replace_lims_instance(
                    import_id,
                    {"instanceId": "EXP-SAME", "title": "重复导入实验", "rawStructured": [{
                        "unitType": "Sample", "data": {"batchNo": batch_no},
                        "evidence": {"unitId": "UNIT-SAME", "unitType": "Sample"},
                    }]},
                    {"project": {}, "document": {}, "samples": [{
                        "batchNo": batch_no, "evidence": {"unitId": "UNIT-SAME"},
                    }]},
                    ["samples"],
                )
            preview = database.preview_lims_field({
                "fieldCode": "samples.batchNo", "collectionCode": "samples",
                "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "batchNo",
            })
            self.assertEqual(preview["total"], 1)
            self.assertEqual(preview["recognizedTotal"], 1)
            self.assertEqual(preview["items"][0]["importId"], "import-new")
            self.assertEqual(preview["items"][0]["value"], ["NEW-001"])
            filtered = database.preview_lims_field({
                "fieldCode": "samples.batchNo", "collectionCode": "samples",
                "dbTable": "lims_standard_records", "dbColumn": "data_json", "jsonKey": "batchNo",
            }, instance_ids=["NOT-SELECTED"])
            self.assertEqual(filtered["total"], 0)
            self.assertEqual(filtered["recognizedTotal"], 0)
            self.assertEqual(len(filtered["options"]), 1)


if __name__ == "__main__":
    unittest.main()
