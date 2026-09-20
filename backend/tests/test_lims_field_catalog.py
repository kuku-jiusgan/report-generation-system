import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.app.admin_routes.rule_catalog import _validate_system_rule
from backend.app.services.lims_configured_extractor import apply_configured_extraction
from backend.app.services.lims_direct_rule_defaults import direct_rule_config
from backend.app.services.lims_direct_rule_migration import migrate_lims_direct_rules
from backend.app.services.lims_normalizer import normalize_instance
from backend.app.services.lims_parser import _body_items
from backend.app.services.lims_rule_schema import lims_rule_metadata, validate_lims_rule_config
from backend.app.services.system_field_rule_invariant import (
    MIGRATION_KEY,
    UNIQUE_INDEX,
    ensure_single_system_field_rule_schema,
)
from backend.tests.database_helpers import make_test_database


TABLE_HTML = """<table><tr><th>验证项目</th><th>名称</th><th>配制方法</th></tr>
<tr><td>系统适用性</td><td>系统适用性溶液</td><td>量取贮备液并稀释</td></tr>
<tr><td>专属性</td><td>空白溶液</td><td>使用溶剂</td></tr></table>"""


def field(
    code: str,
    path: str,
    cardinality: str = "MANY",
    data_type: str = "string",
    output_format: str = "",
) -> dict:
    return {
        "fieldCode": code,
        "legacyJsonPath": path,
        "dataType": data_type,
        "cardinality": cardinality,
        "outputFormat": output_format,
        "defaultValue": "",
        "validationRegex": "",
        "enabled": True,
    }


def rule(code: str, extraction_type: str, **config: object) -> dict:
    return {
        "fieldCode": code,
        "name": "字段直接提取",
        "sourceType": "LIMS",
        "priority": 100,
        "config": {"extractionType": extraction_type, **config},
        "transform": "TRIM",
        "enabled": True,
    }


def rich_instance(html: str = TABLE_HTML) -> dict:
    return {
        "instanceId": "EXP-1",
        "title": "方法验证",
        "project": {"id": "P-1", "name": "项目甲"},
        "richTexts": [{
            "id": "RICH-1",
            "sectionPath": ["实验设计", "溶液配制"],
            "plainText": "最大日剂量：12.5 mg；验证项目 溶液名称 配制方法",
            "html": html,
            "evidence": {"unitId": "RICH-1", "unitType": "RichText"},
        }],
    }


def catalog_field(code: str, collection: str, key: str) -> dict:
    return {
        "fieldCode": code,
        "label": key,
        "groupCode": collection,
        "collectionCode": collection,
        "dataType": "string",
        "cardinality": "MANY",
        "jsonKey": key,
        "legacyJsonPath": f"$.{collection}[*].{key}",
        "description": "",
        "outputFormat": "",
        "defaultValue": "",
        "validationRegex": "",
        "orderNo": 1,
        "enabled": True,
    }


def validator_repository() -> MagicMock:
    repository = MagicMock()
    repository.database.get_lims_field.return_value = {"fieldCode": "custom.value"}
    repository.database.list_system_field_rules.return_value = []
    return repository


def test_lims_rule_api_returns_the_persisted_config_without_expanding_it() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        database.upsert_lims_field(catalog_field("custom.value", "custom", "value"))
        saved = database.save_system_field_rule(rule(
            "custom.value", "INSTANCE_PATH", sourcePath="project.name",
        ))

        rules = database.list_lims_extraction_rules("custom.value")

        assert rules == [saved]
        assert rules[0]["config"] == {
            "extractionType": "INSTANCE_PATH", "sourcePath": "project.name",
        }
        assert "sourcePath" not in rules[0]


def test_structured_unit_body_accepts_a_top_level_standard_object() -> None:
    assert _body_items('{"ext$":{"mtlname":"对照品甲"},"batchNo":"B-001"}', "Standard") == [{
        "ext$": {"mtlname": "对照品甲"}, "batchNo": "B-001",
    }]


def test_structured_unit_body_rejects_unparseable_content() -> None:
    with pytest.raises(ValueError, match="UNITBODY 不是有效 JSON 对象"):
        _body_items("not-json", "Standard")


def test_repository_rejects_a_second_rule_for_the_same_field() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        database.upsert_lims_field(catalog_field("custom.single", "custom", "single"))
        saved = database.save_system_field_rule(rule(
            "custom.single", "INSTANCE_PATH", sourcePath="project.name",
        ))

        with pytest.raises(ValueError, match="已有提取规则"):
            database.save_system_field_rule(rule(
                "custom.single", "INSTANCE_PATH", sourcePath="document.code",
            ))

        updated = database.save_system_field_rule({
            **saved, "config": {"extractionType": "INSTANCE_PATH", "sourcePath": "document.code"},
        }, saved["id"])
        assert updated["id"] == saved["id"]
        assert database.list_system_field_rules("custom.single") == [updated]


def test_single_rule_migration_keeps_latest_rule_and_creates_unique_index() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        database.upsert_lims_field(catalog_field("custom.migrated", "custom", "migrated"))
        with database.connect() as connection:
            connection.execute(f"ALTER TABLE system_field_rules DROP INDEX {UNIQUE_INDEX}")
            connection.execute("DELETE FROM app_migrations WHERE `key`=%s", (MIGRATION_KEY,))
            values = (
                "custom.migrated", "旧规则", "EXCEL", 100, "{}", "TRIM", 1,
                "2026-09-18T00:00:00+00:00",
            )
            connection.execute(
                """INSERT INTO system_field_rules(field_code,name,source_type,priority,config,
                   transform,enabled,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", values,
            )
            latest = connection.execute(
                """INSERT INTO system_field_rules(field_code,name,source_type,priority,config,
                   transform,enabled,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                (*values[:1], "新规则", "LIMS", *values[3:-1], "2026-09-19T00:00:00+00:00"),
            ).lastrowid

        result = ensure_single_system_field_rule_schema(database)

        rules = database.list_system_field_rules("custom.migrated")
        with database.connect() as connection:
            index = connection.execute(
                """SELECT non_unique AS is_non_unique FROM information_schema.statistics
                   WHERE table_schema=DATABASE() AND table_name='system_field_rules'
                     AND index_name=%s""", (UNIQUE_INDEX,),
            ).fetchone()
        assert result == {"removed": 1}
        assert len(rules) == 1
        assert rules[0]["id"] == latest
        assert rules[0]["sourceType"] == "LIMS"
        assert int(index["is_non_unique"]) == 0


def test_instance_path_reads_only_configuration_inside_config() -> None:
    fields = [field("project.name", "$.project.name", "ONE")]
    configured = rule("project.name", "INSTANCE_PATH", sourcePath="project.name")
    configured["sourcePath"] = "document.code"

    payload = normalize_instance(rich_instance(), fields, [configured])

    assert payload["project"]["name"] == "项目甲"


def test_raw_unit_field_uses_candidate_paths_and_preserves_evidence() -> None:
    fields = [field("samples.batchNo", "$.samples[*].batchNo")]
    rules = [rule(
        "samples.batchNo", "RAW_UNIT_FIELD", sourceUnitType="Sample",
        sourcePath="batchNo", sourcePaths=["missing", "batchNo"],
    )]
    instance = {
        "instanceId": "EXP-1",
        "rawStructured": [{
            "unitType": "Sample", "data": {"batchNo": " B-001 "},
            "evidence": {"unitId": "UNIT-1"},
        }],
    }

    payload = normalize_instance(instance, fields, rules)

    assert payload["samples"][0]["batchNo"] == "B-001"
    assert payload["samples"][0]["evidence"]["unitId"] == "UNIT-1"


def test_rich_text_regex_extracts_and_formats_a_number() -> None:
    fields = [field("project.dailyDose", "$.project.dailyDose", "ONE", "decimal", "2")]
    rules = [rule(
        "project.dailyDose", "RICH_TEXT_REGEX", sectionPattern="实验设计",
        valuePattern=r"最大日剂量[:：]\s*([0-9.]+)",
    )]
    rules[0]["transform"] = "NUMBER"

    payload = normalize_instance(rich_instance(), fields, rules)

    assert payload["project"]["dailyDose"] == "12.50"


def test_rows_mode_can_read_the_last_column_and_filter_rows() -> None:
    fields = [field("solutions.preparation", "$.solutions[*].preparation")]
    rules = [rule(
        "solutions.preparation", "HTML_TABLE_COLUMN", recordMode="ROWS",
        headerRows=1, sourceColumnIndex=-1, sectionPattern="溶液配制",
        headerPattern="配制方法", rowPattern="系统适用性",
    )]

    payload = normalize_instance(rich_instance(), fields, rules)

    assert payload["solutions"][0]["preparation"] == "量取贮备液并稀释"
    assert payload["solutions"][0]["evidence"]["tableIndex"] == 1


@pytest.mark.parametrize("headers", [("项目", "参数"), ("分析方法", "HPLC")])
def test_method_parameter_field3_ignores_two_column_tables(headers: tuple[str, str]) -> None:
    instance = {
        "instanceId": "EXP-1",
        "richTexts": [{
            "id": "RICH-1", "sectionPath": ["仪器方法"],
            "html": f"<table><tr><th>{headers[0]}</th><th>{headers[1]}</th></tr>"
                    "<tr><td>色谱柱</td><td>ACE C18</td></tr></table>",
        }],
    }
    fields = [
        catalog_field(f"methodParameters.{key}", "methodParameters", key)
        for key in ("field1", "field2", "field3")
    ]
    rules = [
        rule(f"methodParameters.{key}", "HTML_TABLE_COLUMN", **direct_rule_config("methodParameters", key))
        for key in ("field1", "field2", "field3")
    ]

    payload = normalize_instance(instance, fields, rules)

    assert payload["methodParameters"][0]["field1"] == "色谱柱"
    assert payload["methodParameters"][0]["field2"] == "ACE C18"
    assert "field3" not in payload["methodParameters"][0]


def test_columns_mode_reads_a_configured_row_across_columns() -> None:
    html = """<table><tr><th>项目</th><th>样品1</th><th>样品2</th></tr>
    <tr><td>保留时间</td><td>5.1</td><td>5.2</td></tr></table>"""
    fields = [field("results.retentionTime", "$.results[*].retentionTime")]
    rules = [rule(
        "results.retentionTime", "HTML_TABLE_COLUMN", recordMode="COLUMNS",
        sourcePath="^保留时间$", rowLabelColumn=0, dataStartColumn=1,
        sectionPattern="溶液配制", headerPattern="样品1",
    )]

    payload = normalize_instance(rich_instance(html), fields, rules)

    assert [item["retentionTime"] for item in payload["results"]] == ["5.1", "5.2"]


def test_matrix_mode_can_build_a_value_from_header_and_cell() -> None:
    html = """<table><tr><th>No.</th><th>NDMA</th><th>NDMA</th></tr>
    <tr><th></th><th>保留时间</th><th>峰面积</th></tr>
    <tr><td>1</td><td>5.9</td><td>100</td></tr></table>"""
    fields = [field("systemSuitability.sequence", "$.systemSuitability[*].sequence")]
    rules = [rule(
        "systemSuitability.sequence", "HTML_TABLE_COLUMN", recordMode="MATRIX",
        headerRows=2, dataStartRow=2, dataStartColumn=1, columnStride=2,
        valueColumnIndex=0, valueTemplate="{header}-{value}",
        headerValuePattern=r"^([^|]+)", sectionPattern="溶液配制",
        headerPattern=r"No\..*保留时间.*峰面积",
    )]

    payload = normalize_instance(rich_instance(html), fields, rules)

    assert payload["systemSuitability"][0]["sequence"] == "NDMA-1"


def test_matrix_mode_fixed_value_row_emits_one_header_value_per_column() -> None:
    html = """<table><tr><th>No.</th><th colspan="2">测试1</th><th colspan="2">测试2</th>
    <th colspan="2">测试3</th></tr>
    <tr><th></th><th>保留时间</th><th>峰面积</th><th>保留时间</th><th>峰面积</th>
    <th>保留时间</th><th>峰面积</th></tr>
    <tr><td>1</td><td>5.9</td><td>100</td><td>6.1</td><td>110</td><td>6.3</td><td>120</td></tr>
    <tr><td>2</td><td>5.8</td><td>101</td><td>6.0</td><td>111</td><td>6.2</td><td>121</td></tr>
    <tr><td>3</td><td>5.7</td><td>102</td><td>5.9</td><td>112</td><td>6.1</td><td>122</td></tr>
    <tr><td>4</td><td>5.6</td><td>103</td><td>5.8</td><td>113</td><td>6.0</td><td>123</td></tr>
    <tr><td>5</td><td>5.5</td><td>104</td><td>5.7</td><td>114</td><td>5.9</td><td>124</td></tr></table>"""
    fields = [field("systemSuitability.impurityName", "$.systemSuitability[*].impurityName")]
    rules = [rule(
        "systemSuitability.impurityName", "HTML_TABLE_COLUMN", recordMode="MATRIX",
        headerRows=2, dataStartRow=2, dataStartColumn=1, columnStride=2,
        valueRowIndex=0, sectionPattern="溶液配制",
        headerPattern=r"No\..*保留时间.*峰面积",
    )]

    payload = normalize_instance(rich_instance(html), fields, rules)

    assert [item["impurityName"] for item in payload["systemSuitability"]] == [
        "测试1", "测试2", "测试3",
    ]


def test_disabled_or_section_mismatched_rules_do_not_write_values() -> None:
    fields = [field("solutions.name", "$.solutions[*].name")]
    disabled = rule(
        "solutions.name", "HTML_TABLE_COLUMN", sourcePath="^名称$",
        sectionPattern="溶液配制",
    )
    disabled["enabled"] = False
    mismatched = rule(
        "solutions.name", "HTML_TABLE_COLUMN", sourcePath="^名称$",
        sectionPattern="不存在的章节",
    )

    assert "solutions" not in normalize_instance(rich_instance(), fields, [disabled])
    assert "solutions" not in normalize_instance(rich_instance(), fields, [mismatched])


def test_invalid_rule_regex_fails_fast() -> None:
    fields = [field("solutions.name", "$.solutions[*].name")]
    rules = [rule(
        "solutions.name", "HTML_TABLE_COLUMN", sourcePath="^名称$", sectionPattern="[",
    )]

    with pytest.raises(ValueError, match="正则无效"):
        normalize_instance(rich_instance(), fields, rules)


@pytest.mark.parametrize("extraction_type", ["NORMALIZED_PATH", "HTML_TABLE_GRID", ""])
def test_rule_validation_rejects_retired_lims_extraction_types(extraction_type: str) -> None:
    item = rule("custom.value", extraction_type, sourcePath="value")

    with pytest.raises(HTTPException, match="LIMS 提取方式必须直接读取"):
        _validate_system_rule(validator_repository(), item)


def test_rule_validation_accepts_all_direct_lims_extraction_types() -> None:
    configs = [
        rule("custom.value", "INSTANCE_PATH", sourcePath="project.name"),
        rule("custom.value", "RAW_UNIT_FIELD", sourceUnitType="Sample", sourcePath="batchNo"),
        rule("custom.value", "RICH_TEXT_REGEX", sectionPattern="实验设计"),
        rule("custom.value", "HTML_TABLE_COLUMN", sourcePath="^名称$"),
    ]

    for item in configs:
        assert _validate_system_rule(validator_repository(), item)["config"] == item["config"]


def test_lims_rule_metadata_exposes_every_runtime_configuration_field() -> None:
    metadata = lims_rule_metadata()
    assert metadata["sourceType"] == "LIMS"
    assert [item["value"] for item in metadata["extractionTypes"]] == [
        "INSTANCE_PATH", "RAW_UNIT_FIELD", "RICH_TEXT_REGEX", "HTML_TABLE_COLUMN",
    ]
    editable_keys = {
        field["key"]
        for extraction_type in metadata["extractionTypes"]
        for group in extraction_type["groups"]
        for field in group["fields"]
    }
    editable_keys.update(
        field["key"]
        for group in metadata["transformGroups"]
        for field in group["fields"]
    )
    runtime_keys = {
        "columnPattern", "columnStride", "dataStartColumn", "dataStartRow",
        "excludeRowPattern", "headerPattern", "headerRows", "headerValuePattern",
        "replacePattern", "replaceWith", "rowLabelColumn", "rowPattern", "rowStride",
        "sectionPattern", "sourceColumnIndex", "sourcePath", "sourcePaths",
        "sourceRowIndex", "sourceUnitType", "valueColumnIndex", "valueColumnOffset",
        "valuePattern", "valueRowIndex", "valueRowOffset", "valueTemplate",
    }
    assert runtime_keys <= editable_keys


def test_lims_rule_schema_validates_visible_integer_and_regex_inputs() -> None:
    assert validate_lims_rule_config({
        "extractionType": "INSTANCE_PATH", "sourcePath": "items[",
    }, "TRIM")["sourcePath"] == "items["
    with pytest.raises(ValueError, match="headerRows 必须是整数"):
        validate_lims_rule_config({
            "extractionType": "HTML_TABLE_COLUMN", "sourcePath": "名称", "headerRows": "一",
        }, "TRIM")
    with pytest.raises(ValueError, match="sectionPattern 正则无效"):
        validate_lims_rule_config({
            "extractionType": "RICH_TEXT_REGEX", "sectionPattern": "[",
        }, "TRIM")
    with pytest.raises(ValueError, match="正则替换必须配置替换正则"):
        validate_lims_rule_config({
            "extractionType": "INSTANCE_PATH", "sourcePath": "project.name",
        }, "REGEX_REPLACE")


def test_unified_migration_converts_legacy_rule_once_and_does_not_recreate_deleted_rule() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        field_code = "systemSuitability.peakArea"
        database.upsert_lims_field(catalog_field(field_code, "systemSuitability", "peakArea"))
        legacy = database.save_system_field_rule({
            "fieldCode": field_code,
            "name": "旧标准集合读取",
            "sourceType": "LIMS",
            "priority": 100,
            "config": {
                "extractionType": "NORMALIZED_PATH",
                "sourcePath": "$.systemSuitability[*].peakArea",
                "parser": "HTML_TABLE_GRID",
                "parserProfile": "SYSTEM_SUITABILITY_MATRIX",
            },
            "transform": "TRIM",
            "enabled": True,
        })

        first = migrate_lims_direct_rules(database)
        migrated = database.list_lims_extraction_rules(field_code)[0]
        database.delete_system_field_rule(migrated["id"])
        second = migrate_lims_direct_rules(database)

        assert first["migrated"] == 1
        assert migrated["id"] == legacy["id"]
        assert migrated["config"]["extractionType"] == "HTML_TABLE_COLUMN"
        assert "parser" not in migrated["config"]
        assert "parserProfile" not in migrated["config"]
        assert second == {"migrated": 0, "groupMappings": 0, "created": 0, "removed": 0}
        assert database.list_lims_extraction_rules(field_code) == []


def test_extractor_ignores_retired_top_level_configuration() -> None:
    fields = [field("project.name", "$.project.name", "ONE")]
    configured = rule("project.name", "INSTANCE_PATH", sourcePath="project.name")
    configured.update({
        "extractionType": "RICH_TEXT_REGEX",
        "sectionPattern": "不存在",
        "sourcePath": "document.code",
    })
    payload: dict = {}

    apply_configured_extraction(rich_instance(), payload, fields, [configured])

    assert payload["project"]["name"] == "项目甲"
