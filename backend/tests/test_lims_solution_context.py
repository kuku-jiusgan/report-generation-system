import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.app.admin_routes.rule_catalog import _validate_system_rule
from backend.app.repositories.lims_instances import collection_storage
from backend.app.services.lims_normalizer import normalize_instance
from backend.app.services.rule_admin_defaults import (
    SOLUTION_TABLE_COLUMN_PATTERNS, SOLUTION_TABLE_DEFAULTS,
)
from backend.app.services.lims_direct_rule_migration import migrate_lims_direct_rules
from backend.tests.database_helpers import make_test_database


CALCULATION_PATTERN = r"(?:\([^()（）]*=[^()（）]*\)|（[^()（）]*=[^()（）]*）)"
TABLE_HTML = """<table><tr><th>验证项目</th><th>溶液名称</th><th>配制方法</th></tr>
<tr><td>系统适用性</td><td>系统适用性溶液</td><td>称取2.013mg（2.013-0.000=2.013）（纯度99.67%）</td></tr>
<tr><td>专属性</td><td>专属性溶液</td><td>称取1.996mg（2.013-0.017=1.996）（纯度99.88%）</td></tr>
</table>"""
ROWSPAN_TABLE_HTML = """<table><tr><th>验证项目</th><th>溶液名称</th><th>配制方法</th></tr>
<tr><td rowspan="3">系统适用性</td><td>溶剂</td><td>水-乙腈。</td></tr>
<tr><td>混标贮备液</td><td>量取各单标贮备液并稀释。</td></tr>
<tr><td>系统适用性溶液</td><td>量取混标贮备液并稀释。</td></tr>
<tr><td rowspan="2">专属性</td><td>空白溶液</td><td>使用溶剂。</td></tr>
<tr><td>供试品溶液</td><td>称取供试品并稀释。</td></tr>
</table>"""


def _instance(html: str = TABLE_HTML) -> dict:
    return {
        "instanceId": "SOLUTION-1", "title": "方法验证",
        "richTexts": [{
            "id": "RICH-1", "sectionPath": ["实验设计", "溶液配制"],
            "plainText": "验证项目 溶液名称 配制方法", "html": html,
            "evidence": {"unitId": "RICH-1", "unitType": "RichText"},
        }],
    }


def _fields(*collections: str) -> list[dict]:
    return [{
        "fieldCode": f"{collection}.{leaf}",
        "legacyJsonPath": f"$.{collection}[*].{leaf}",
        "dataType": "richText" if leaf == "preparation" else "string",
        "cardinality": "MANY", "enabled": True,
    } for collection in collections for leaf in ("name", "preparation")]


def _rules(*collections: str, replace_collection: str = "") -> list[dict]:
    rules = []
    for collection in collections:
        defaults = SOLUTION_TABLE_DEFAULTS[collection]
        for leaf in ("name", "preparation"):
            replace = leaf == "preparation" and collection == replace_collection
            config = {
                "extractionType": "HTML_TABLE_COLUMN",
                "sourcePath": SOLUTION_TABLE_COLUMN_PATTERNS[leaf],
                "sectionPattern": r"实验设计.*溶液配制",
                "headerPattern": r"(?=.*验证项目)(?=.*溶液名称)(?=.*配制方法)",
                "rowPattern": defaults["rowPattern"],
            }
            if replace:
                config.update({"replacePattern": CALCULATION_PATTERN, "replaceWith": ""})
            rules.append({
                "fieldCode": f"{collection}.{leaf}", "sourceType": "HTML_TABLE_COLUMN",
                "sourcePath": config["sourcePath"], "sectionPattern": config["sectionPattern"],
                "headerPattern": config["headerPattern"], "config": config,
                "transform": "REGEX_REPLACE" if replace else "TRIM", "enabled": True,
            })
    return rules


def test_each_solution_collection_is_extracted_by_its_own_field_rules() -> None:
    collections = ("systemSuitabilitySolutions", "specificitySolutions")

    result = normalize_instance(_instance(), _fields(*collections), _rules(*collections))

    assert "solutions" not in result
    assert result["systemSuitabilitySolutions"][0]["name"] == "系统适用性溶液"
    assert result["specificitySolutions"][0]["name"] == "专属性溶液"
    assert len(result["systemSuitabilitySolutions"]) == 1
    assert len(result["specificitySolutions"]) == 1


def test_solution_rules_expand_rowspan_before_filtering_rows() -> None:
    collections = ("systemSuitabilitySolutions", "specificitySolutions")

    result = normalize_instance(
        _instance(ROWSPAN_TABLE_HTML), _fields(*collections), _rules(*collections),
    )

    assert [item["name"] for item in result["systemSuitabilitySolutions"]] == [
        "溶剂", "混标贮备液", "系统适用性溶液",
    ]
    assert [item["preparation"] for item in result["systemSuitabilitySolutions"]] == [
        "水-乙腈。", "量取各单标贮备液并稀释。", "量取混标贮备液并稀释。",
    ]
    assert [item["name"] for item in result["specificitySolutions"]] == [
        "空白溶液", "供试品溶液",
    ]


def test_regex_replace_only_changes_the_configured_preparation_field() -> None:
    collections = ("systemSuitabilitySolutions", "specificitySolutions")

    result = normalize_instance(
        _instance(), _fields(*collections),
        _rules(*collections, replace_collection="systemSuitabilitySolutions"),
    )

    assert result["systemSuitabilitySolutions"][0]["preparation"] == "称取2.013mg（纯度99.67%）"
    assert result["specificitySolutions"][0]["preparation"] == (
        "称取1.996mg（2.013-0.017=1.996）（纯度99.88%）"
    )


def test_direct_solution_records_keep_lims_table_evidence() -> None:
    collection = "systemSuitabilitySolutions"

    result = normalize_instance(_instance(), _fields(collection), _rules(collection))

    evidence = result[collection][0]["evidence"]
    assert evidence["instanceId"] == "SOLUTION-1"
    assert evidence["richTextId"] == "RICH-1"
    assert evidence["tableIndex"] == 1
    assert evidence["unitId"] == "RICH-1"


def test_solution_collection_is_a_normal_many_record_collection() -> None:
    assert collection_storage("specificitySolutions", "MANY") == (
        "lims_standard_records", "data_json",
    )


def test_html_table_column_rule_requires_a_column_pattern() -> None:
    repository = MagicMock()
    repository.database.get_lims_field.return_value = {
        "fieldCode": "systemSuitabilitySolutions.preparation",
    }
    repository.database.list_system_field_rules.return_value = []
    rule = {
        "fieldCode": "systemSuitabilitySolutions.preparation", "name": "系统适用性溶液配制",
        "sourceType": "LIMS", "transform": "TRIM", "enabled": True,
        "config": {"extractionType": "HTML_TABLE_COLUMN"},
    }

    with pytest.raises(HTTPException, match="必须配置取值列标题正则"):
        _validate_system_rule(repository, rule)


def test_regex_replace_rule_requires_valid_replacement_config() -> None:
    repository = MagicMock()
    repository.database.get_lims_field.return_value = {
        "fieldCode": "systemSuitabilitySolutions.preparation",
    }
    repository.database.list_system_field_rules.return_value = []
    base_rule = {
        "fieldCode": "systemSuitabilitySolutions.preparation", "name": "清理称量计算",
        "sourceType": "LIMS", "transform": "REGEX_REPLACE", "enabled": True,
        "config": {"extractionType": "HTML_TABLE_COLUMN", "sourcePath": "^配制方法$"},
    }

    with pytest.raises(HTTPException, match="必须配置替换正则"):
        _validate_system_rule(repository, base_rule)
    with pytest.raises(HTTPException, match="replacePattern 正则无效"):
        _validate_system_rule(repository, {
            **base_rule, "config": {**base_rule["config"], "replacePattern": "["},
        })


def test_unified_migration_preserves_direct_rule_configuration() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        for collection in SOLUTION_TABLE_DEFAULTS:
            for leaf in SOLUTION_TABLE_COLUMN_PATTERNS:
                database.upsert_lims_field({
                    "fieldCode": f"{collection}.{leaf}", "label": leaf,
                    "groupCode": collection, "collectionCode": collection,
                    "dataType": "string", "cardinality": "MANY", "jsonKey": leaf,
                    "legacyJsonPath": f"$.{collection}[*].{leaf}", "enabled": True,
                })
        database.save_system_field_rule({
            "fieldCode": "systemSuitabilitySolutions.preparation", "name": "清理称量计算",
            "sourceType": "LIMS", "transform": "REGEX_REPLACE", "enabled": True,
            "config": {
                "extractionType": "NORMALIZED_PATH",
                "sourcePath": "$.systemSuitabilitySolutions[*].preparation",
                "derivedFromCollection": "solutions", "replacePattern": CALCULATION_PATTERN,
                "replaceWith": "",
            },
        })
        database.save_system_field_rule({
            "fieldCode": "specificitySolutions.preparation", "name": "自定义专属性溶液列",
            "sourceType": "LIMS", "transform": "TRIM", "enabled": True,
            "config": {
                "extractionType": "HTML_TABLE_COLUMN", "sourcePath": r"^具体配制步骤$",
                "sectionPattern": r"专属性.*溶液", "headerPattern": r"具体配制步骤",
                "rowPattern": r"验证项目=专属性", "valuePattern": r"^(.+)$",
            },
        })

        first = migrate_lims_direct_rules(database)
        second = migrate_lims_direct_rules(database)

        rule = database.list_system_field_rules("systemSuitabilitySolutions.preparation")[0]
        assert first["migrated"] >= 1
        assert second == {"migrated": 0, "groupMappings": 0, "created": 0, "removed": 0}
        assert rule["transform"] == "REGEX_REPLACE"
        assert rule["config"]["extractionType"] == "HTML_TABLE_COLUMN"
        assert rule["config"]["sourcePath"] == SOLUTION_TABLE_COLUMN_PATTERNS["preparation"]
        assert rule["config"]["replacePattern"] == CALCULATION_PATTERN
        assert "derivedFromCollection" not in rule["config"]
        custom = database.list_system_field_rules("specificitySolutions.preparation")[0]
        assert custom["config"]["sourcePath"] == r"^具体配制步骤$"
        assert custom["config"]["sectionPattern"] == r"专属性.*溶液"
        assert custom["config"]["headerPattern"] == r"具体配制步骤"
        assert custom["config"]["rowPattern"] == r"验证项目=专属性"
        assert custom["config"]["valuePattern"] == r"^(.+)$"
        assert database.get_lims_field("systemSuitabilitySolutions.preparation") is not None


def test_unified_migration_removes_deprecated_parser_keys_from_direct_rule() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = make_test_database(Path(directory))
        field_code = "systemSuitabilitySolutions.preparation"
        database.upsert_lims_field({
            "fieldCode": field_code, "label": "系统适用性溶液配置",
            "groupCode": "systemSuitabilitySolutions",
            "collectionCode": "systemSuitabilitySolutions",
            "dataType": "richText", "cardinality": "MANY", "jsonKey": "preparation",
            "legacyJsonPath": "$.systemSuitabilitySolutions[*].preparation", "enabled": True,
        })
        database.save_system_field_rule({
            "fieldCode": field_code, "name": "直接读取溶液配置表格列",
            "sourceType": "LIMS", "transform": "TRIM", "enabled": True,
            "config": {
                "extractionType": "HTML_TABLE_COLUMN", "sourcePath": "^配制方法$",
                "parser": "NORMALIZED_JSON", "inputField": "UNITBODY",
                "outputCollection": "systemSuitabilitySolutions",
                "outputField": "preparation",
            },
        })

        migrate_lims_direct_rules(database)

        config = database.list_system_field_rules(field_code)[0]["config"]
        assert config["extractionType"] == "HTML_TABLE_COLUMN"
        assert config["sourcePath"] == "^配制方法$"
        assert "parser" not in config
        assert "inputField" not in config
        assert "outputCollection" not in config
        assert "outputField" not in config
