"""模板设计器的内容块配置必须驱动字段映射，后端不得按 sourcePath 猜测循环。"""

from backend.app.services.template_block_rules import apply_template_block_rules


GROUPS = [
    {"groupCode": "systemSuitability", "fields": [
        {"fieldCode": "systemSuitability.impurityName"},
        {"fieldCode": "systemSuitability.retentionTime"},
    ]},
    {"groupCode": "systemSuitabilitySolutions", "fields": [
        {"fieldCode": "systemSuitabilitySolutions.name"},
    ]},
]

CATALOG = [
    {"fieldCode": "systemSuitability.impurityName", "dataType": "string", "outputFormat": ""},
]


def _snapshot(**block: object) -> dict:
    return {
        "mappings": [
            {"standardFieldCode": "systemSuitability.impurityName", "tableNo": "TEXT",
             "repeatType": "NONE", "sourcePath": "$.systemSuitability[*].impurityName"},
            {"standardFieldCode": "systemSuitability.retentionTime", "tableNo": "TEXT",
             "repeatType": "NONE", "sourcePath": "$.systemSuitability[*].retentionTime"},
            {"standardFieldCode": "systemSuitabilitySolutions.name", "tableNo": "TEXT",
             "repeatType": "NONE", "sourcePath": "$.systemSuitabilitySolutions[*].name"},
        ],
        "templateBlocks": [{
            "standardGroupCode": "systemSuitability", "kind": "MATRIX",
            "tableNo": "GROUP:systemSuitability", "sourcePath": "$.systemSuitability",
            "emptyBehavior": "KEEP", "mergeRule": "NONE", "enabled": True, **block,
        }],
    }


def _by_field(mappings: list[dict]) -> dict[str, dict]:
    return {item["standardFieldCode"]: item for item in mappings}


def test_matrix_block_drives_table_number_and_repeat_type() -> None:
    mappings = _by_field(apply_template_block_rules(_snapshot(), GROUPS, CATALOG))

    for code in ("systemSuitability.impurityName", "systemSuitability.retentionTime"):
        assert mappings[code]["tableNo"] == "GROUP:systemSuitability"
        assert mappings[code]["repeatType"] == "ROW"
        assert mappings[code]["contentBlockKind"] == "MATRIX"
        # 编组的数据集合写成 $.xxx，落到映射上必须是循环路径写法
        assert mappings[code]["blockSourcePath"] == "$.systemSuitability[*]"


def test_group_without_a_configured_block_is_left_alone() -> None:
    mappings = _by_field(apply_template_block_rules(_snapshot(), GROUPS, CATALOG))
    solution = mappings["systemSuitabilitySolutions.name"]

    assert solution["repeatType"] == "NONE"
    assert solution["tableNo"] == "TEXT"
    assert "contentBlockKind" not in solution


def test_disabled_block_does_not_change_mappings() -> None:
    mappings = _by_field(apply_template_block_rules(_snapshot(enabled=False), GROUPS, CATALOG))

    assert mappings["systemSuitability.impurityName"]["repeatType"] == "NONE"


def test_table_repeat_block_also_marks_row_mappings() -> None:
    snapshot = _snapshot(kind="TABLE_REPEAT")
    mappings = _by_field(apply_template_block_rules(snapshot, GROUPS, CATALOG))

    assert mappings["systemSuitability.impurityName"]["repeatType"] == "ROW"
    assert mappings["systemSuitability.impurityName"]["contentBlockKind"] == "TABLE_REPEAT"


def test_field_catalog_metadata_is_attached() -> None:
    mappings = _by_field(apply_template_block_rules(_snapshot(), GROUPS, CATALOG))

    assert mappings["systemSuitability.impurityName"]["standardFieldDataType"] == "string"
    assert "standardFieldDataType" not in mappings["systemSuitability.retentionTime"]
