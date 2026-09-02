import tempfile
import unittest
from pathlib import Path

from backend.app.database import Database
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.lims_configured_extractor import apply_configured_extraction
from backend.app.services.lims_normalizer import normalize_instance
from backend.app.services.lims_catalog_defaults import ensure_lims_catalog_defaults


class LimsFieldCatalogTest(unittest.TestCase):
    def test_lims_parser_rules_come_from_admin_system_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            database.upsert_lims_field({
                "fieldCode": "systemSuitability.sequence", "label": "No.",
                "groupCode": "系统适用性结果", "collectionCode": "systemSuitability",
                "dataType": "string", "cardinality": "MANY",
                "dbTable": "lims_standard_records", "dbColumn": "data_json",
                "jsonKey": "sequence", "legacyJsonPath": "$.systemSuitability[*].sequence",
                "description": "", "outputFormat": "", "defaultValue": "",
                "validationRegex": "", "orderNo": 1, "enabled": True,
            })
            database.save_system_field_rule({
                "fieldCode": "systemSuitability.sequence", "name": "后台规则", "sourceType": "LIMS",
                "priority": 100, "config": {
                    "extractionType": "NORMALIZED_PATH",
                    "sourcePath": "$.systemSuitability[*].sequence",
                    "sectionPattern": r"(?:实|试)验结果.*系统适用性(?:结果)?",
                }, "enabled": True,
            })

            rules = database.list_lims_parser_rules("systemSuitability.sequence")

            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["name"], "后台规则")
            self.assertEqual(rules[0]["sectionPattern"], r"(?:实|试)验结果.*系统适用性(?:结果)?")

    def test_report_source_catalog_exposes_canonical_binding_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            repository = RuleAdminRepository(database, Path(directory) / "unused.json")
            chapter = repository.create_template_chapter({
                "code": "1", "title": "封面", "orderNo": 1,
            })
            repository.create_mapping({
                "chapterId": chapter["id"], "wordLabel": "文件编号",
                "fieldCode": "document.code", "sourceType": "LIMS",
                "sourcePath": "$.document.code", "reportBindingCode": "report_no",
                "enabled": True,
            })

            catalog = repository.report_source_catalog()

            field = catalog["chapters"][0]["fields"][0]
            self.assertEqual(field["fieldCode"], "document.code")
            self.assertEqual(field["bindingCode"], "report_no")

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
                "id": "import-rich", "file_name": "Oracle 查询：XM-RICH", "stored_name": "",
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

    def test_system_suitability_accepts_named_result_section_and_skips_summary_rows(self) -> None:
        instance = {
            "instanceId": "EXP-SYSTEM", "title": "方法验证", "project": {}, "document": {},
            "richTexts": [{
                "id": "RICH-SYSTEM", "sectionPath": ["实验结果", "系统适用性"],
                "html": """<table><tr><th>No.</th><th>NDMA</th><th>NDMA</th></tr>
                    <tr><th></th><th>保留时间</th><th>峰面积</th></tr>
                    <tr><td>1</td><td>3.987</td><td>96717</td></tr>
                    <tr><td>RSD（%）</td><td>0.2</td><td>1.2</td></tr>
                    <tr><td>结论</td><td colspan="2">符合规定</td></tr></table>""",
                "plainText": "No. NDMA 保留时间 峰面积",
                "evidence": {"unitId": "RICH-SYSTEM"},
            }],
        }
        rule = {
            "enabled": True,
            "sectionPattern": r"(?:实|试)验结果.*系统适用性(?:结果)?",
            "headerPattern": r"No\.?.*保留时间.*峰面积",
            "config": {"parser": "HTML_TABLE_GRID", "parserProfile": "SYSTEM_SUITABILITY_MATRIX"},
        }

        result = normalize_instance(instance, extraction_rules=[rule])

        self.assertEqual(len(result["systemSuitability"]), 1)
        self.assertEqual(result["systemSuitability"][0]["sequence"], "NDMA-1")

    def test_impurity_table_uses_semantic_columns_and_preserves_structure_image(self) -> None:
        instance = {
            "instanceId": "EXP-IMPURITY", "title": "方法开发", "project": {}, "document": {},
            "richTexts": [{
                "id": "RICH-IMPURITY", "sectionPath": ["试验设计"],
                "html": """<table><tr><th>No.</th><th>名称</th><th>限度（ppm）</th>
                    <th>结构式</th><th>CAS号</th></tr><tr><td>1</td><td>N-亚硝基氢氯噻嗪</td>
                    <td>≤ 60 ppm</td><td><img src="/files/structure.png"></td>
                    <td>63779-86-2</td></tr></table>""",
                "plainText": "名称 限度 结构式 CAS号", "evidence": {"unitId": "RICH-IMPURITY"},
            }],
        }
        rule = {
            "enabled": True, "sectionPattern": r"(?:实|试)验设计|参考文件|限度",
            "headerPattern": r"(?=.*(?:杂质名称|名称))(?=.*CAS)(?=.*(?:杂质)?限度)",
            "config": {"parser": "HTML_TABLE_GRID", "parserProfile": "IMPURITY_LIMIT_TABLE"},
        }

        result = normalize_instance(instance, extraction_rules=[rule])

        self.assertEqual(result["impurity"][0]["impurityName"], "N-亚硝基氢氯噻嗪")
        self.assertEqual(result["impurity"][0]["field2"], "63779-86-2")
        self.assertEqual(result["impurity"][0]["field3"], "/files/structure.png")
        self.assertEqual(result["impurity"][0]["field4"], "≤ 60 ppm")

    def test_validation_summary_accepts_header_variants_and_reordered_columns(self) -> None:
        instance = {
            "instanceId": "EXP-CRITERIA", "title": "方法验证", "project": {}, "document": {},
            "richTexts": [{
                "id": "RICH-CRITERIA", "sectionPath": ["试验设计"],
                "html": """<table><tr><th>可接受标准</th><th>检验项目</th></tr>
                    <tr><td>峰面积 RSD 应不大于 20%</td><td>系统适用性</td></tr></table>""",
                "plainText": "可接受标准 检验项目", "evidence": {"unitId": "RICH-CRITERIA"},
            }],
        }
        rule = {
            "enabled": True, "sectionPattern": r"(?:实|试)验设计|验证(?:项目|内容)|(?:可)?接受标准",
            "headerPattern": r"(?=.*(?:验证|试验|检验)?项目)(?=.*(?:可)?接受标准)",
            "config": {"parser": "HTML_TABLE_GRID", "parserProfile": "VALIDATION_SUMMARY_TABLE"},
        }

        result = normalize_instance(instance, extraction_rules=[rule])

        self.assertEqual(result["validationSummary"][0]["field1"], "系统适用性")
        self.assertEqual(result["validationSummary"][0]["acceptanceCriteria"], "峰面积 RSD 应不大于 20%")

    def test_limit_calculation_table_extracts_six_semantic_columns(self) -> None:
        instance = {
            "instanceId": "EXP-LIMIT", "title": "方法验证", "project": {}, "document": {},
            "richTexts": [{
                "id": "RICH-LIMIT", "sectionPath": ["实验设计"],
                "html": """<table><tr><th>杂质限度浓度 (ng/ml)</th><th>杂质名称</th>
                    <th>供试品溶液中 API 浓度 (mg/ml)</th><th>最大日剂量 (mg/day)</th>
                    <th>AI值 (ng/day)</th><th>杂质限度 (ppm)</th></tr><tr><td>30</td>
                    <td>N-亚硝基氢氯噻嗪</td><td>0.5</td><td>25（以API计）</td><td>1500</td><td>60</td>
                    </tr></table>""", "plainText": "限度计算列表", "evidence": {"unitId": "RICH-LIMIT"},
            }],
        }
        rule = {
            "enabled": True, "sectionPattern": r"(?:实|试)验设计|杂质信息|限度计算",
            "headerPattern": r"(?=.*杂质名称)(?=.*AI值)(?=.*最大日剂量)(?=.*杂质限度)(?=.*API\s*浓度)(?=.*限度浓度)",
            "config": {"parser": "HTML_TABLE_GRID", "parserProfile": "LIMIT_CALCULATION_TABLE"},
        }

        item = normalize_instance(instance, extraction_rules=[rule])["limit"][0]

        self.assertEqual(item["impurityName"], "N-亚硝基氢氯噻嗪")
        self.assertEqual([item[f"field{index}"] for index in range(2, 7)],
                         ["1500", "25（以API计）", "60", "0.5", "30"])

    def test_validation_summary_defaults_create_fields_and_parser_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "catalog.db")
            database.initialize()
            repository = RuleAdminRepository(database, Path(directory) / "unused.json")
            chapter = repository.create_template_chapter({
                "code": "5.1", "title": "验证结果汇总", "orderNo": 1,
            })
            repository.create_mapping({
                "chapterId": chapter["id"], "locationId": "body.T10.dataRow.cell1",
                "sectionCode": "5.validationSummary", "tableNo": "T10", "wordLabel": "验证项目",
                "fieldCode": "validationSummary[].field1", "dataType": "string",
                "sourceType": "CALCULATED", "sourcePath": "$.validationSummary[*].field1",
                "repeatType": "ROW", "calculationRule": "DOMAIN_FORMULA", "enabled": True,
            })
            ensure_lims_catalog_defaults(database)
            repository._annotate_lims_rules()

            fields = {item["fieldCode"]: item for item in database.list_lims_fields()}
            self.assertEqual(fields["validationSummary.field1"]["label"], "验证项目")
            self.assertEqual(
                fields["validationSummary.acceptanceCriteria"]["label"], "接受标准",
            )
            rules = database.list_lims_parser_rules("validationSummary.field1")
            self.assertEqual(rules[0]["config"]["parserProfile"], "VALIDATION_SUMMARY_TABLE")
            self.assertIn("试", rules[0]["sectionPattern"])
            mapping = repository.list_mappings()[0]
            self.assertEqual(mapping["sourceType"], "LIMS")
            self.assertEqual(mapping["standardFieldCode"], "validationSummary.field1")
            catalog = repository.standard_field_catalog()
            self.assertEqual(catalog["chapters"][0]["fields"][0]["label"], "验证项目")

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
            database.save_system_field_rule({
                "fieldCode": "systemSuitability.peakArea", "name": "已有标准数据路径",
                "sourceType": "LIMS", "transform": "TRIM", "priority": 100,
                "config": {"extractionType": "NORMALIZED_PATH",
                           "sourcePath": "$.systemSuitability[*].peakArea"}, "enabled": True,
            })
            repository = RuleAdminRepository(database, Path(directory) / "unused.json")
            repository._annotate_lims_rules()
            rule = database.list_lims_parser_rules("systemSuitability.peakArea")[0]
            self.assertEqual(rule["name"], "HTML 表格解析 → 标准字段")
            self.assertEqual(rule["config"]["parser"], "HTML_TABLE_GRID")
            self.assertEqual(rule["config"]["parserProfile"], "SYSTEM_SUITABILITY_MATRIX")
            self.assertEqual(rule["config"]["inputField"], "UNITBODY")
            self.assertEqual(rule["config"]["outputField"], "peakArea")
            self.assertIn("保留时间", rule["headerPattern"])

    def test_field_and_system_rule_crud(self) -> None:
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
            rule = database.save_system_field_rule({
                "fieldCode": field["fieldCode"], "name": "原始样品批号",
                "sourceType": "LIMS", "transform": "TRIM", "priority": 10,
                "config": {"extractionType": "RAW_UNIT_FIELD", "sourceUnitType": "Sample",
                           "sourcePath": "batchNo"}, "enabled": True,
            })
            self.assertEqual(database.list_system_field_rules(field["fieldCode"])[0]["id"], rule["id"])
            self.assertTrue(database.delete_system_field_rule(rule["id"]))
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
                "id": "import-1", "file_name": "Oracle 查询：XM-1", "stored_name": "",
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
            self.assertEqual(preview["items"][0]["fileName"], "Oracle 查询：XM-1")
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

    def test_workbench_payload_is_rebuilt_from_persisted_standard_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "workbench.db")
            database.initialize()
            database.create_lims_import({
                "id": "import-1", "file_name": "Oracle 查询：P1", "stored_name": "",
                "size": 0, "summary": {}, "created_at": "2026-07-25T08:00:00+00:00",
            })
            database.replace_lims_instance(
                "import-1",
                {"instanceId": "EXP-1", "projectId": "P1", "title": "实验一",
                 "rawStructured": [{"unitType": "Sample", "data": {"batchNo": "RAW"}}]},
                {"project": {"id": "P1", "name": "项目一"}, "document": {"code": "D1"},
                 "samples": [{"batchNo": "RULE-VALUE", "evidence": {"unitId": "U1"}}]},
                ["samples"],
            )

            payload = database.get_lims_normalized_payload("import-1", "EXP-1")

            self.assertEqual(payload["samples"][0]["batchNo"], "RULE-VALUE")
            self.assertEqual(payload["samples"][0]["evidence"]["unitId"], "U1")
            self.assertNotIn("rawStructured", payload)

    def test_preview_deduplicates_reimported_lims_instance_and_keeps_latest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "preview.db")
            database.initialize()
            for import_id, created_at, batch_no in (
                ("import-old", "2026-07-25T08:00:00+00:00", "OLD-001"),
                ("import-new", "2026-07-26T08:00:00+00:00", "NEW-001"),
            ):
                database.create_lims_import({
                    "id": import_id, "file_name": f"Oracle 查询：{import_id}", "stored_name": "",
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
