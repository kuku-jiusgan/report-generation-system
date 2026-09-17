from backend.app.services.lims_normalizer import merge_instances, normalize_instance
from backend.app.services.lims_configured_extractor import _table_values


def test_intermediate_precision_instance_owns_solution_rows() -> None:
    instance = {
        "instanceId": "IP-1",
        "title": "中间精密度",
        "richTexts": [{
            "id": "R-1", "sectionPath": ["中间精密度"],
            "plainText": "溶液名称 配制方法",
            "html": "<table><tr><th>序号</th><th>溶液名称</th><th>验证项目</th><th>配制方法</th></tr>"
                     "<tr><td>1</td><td>中间精密度溶液</td><td>中间精密度</td><td>按方案配制</td></tr></table>",
        }],
    }
    result = normalize_instance(instance)
    assert len(result["intermediatePrecisionSolutions"]) == 1
    assert result["systemSuitabilitySolutions"] == []


def test_solution_rule_can_filter_validation_project_row() -> None:
    instance = {"richTexts": [{
        "sectionPath": ["实验设计"],
        "html": "<table><tr><th>验证项目</th><th>溶液名称</th><th>配制方法</th></tr>"
                "<tr><td>中间精密度</td><td>IP</td><td>IP配制</td></tr>"
                "<tr><td>系统适用性</td><td>SS</td><td>SS配制</td></tr></table>",
    }]}
    values = _table_values(instance, {
        "headerPattern": "溶液名称.*配制方法",
        "sourcePath": "溶液名称",
        "rowPattern": "验证项目.*系统适用性",
    })
    assert values == ["SS"]


def test_shared_solution_does_not_enter_validation_project_views() -> None:
    instance = {
        "instanceId": "SHARED-1",
        "title": "试验过程",
        "richTexts": [{
            "id": "R-1", "sectionPath": ["试验过程", "溶液配制"],
            "plainText": "溶液名称 配制方法",
            "html": "<table><tr><th>溶液名称</th><th>配制方法</th></tr>"
                    "<tr><td>空白溶液</td><td>水-乙腈</td></tr></table>",
        }],
    }

    result = normalize_instance(instance)

    assert result["solutions"][0]["validationCode"] == "shared"
    assert result["systemSuitabilitySolutions"] == []
    assert result["specificitySolutions"] == []


def test_custom_sample_test_group_filters_rows_without_hiding_standard_solutions() -> None:
    instance = {
        "instanceId": "SAMPLE-1",
        "title": "试验过程",
        "richTexts": [{
            "id": "R-1", "sectionPath": ["试验过程", "溶液配制"],
            "plainText": "验证项目 溶液名称 配制方法",
            "html": "<table><tr><th>验证项目</th><th>溶液名称</th><th>配制方法</th></tr>"
                    "<tr><td>供试品检测</td><td>供试品溶液</td><td>取样品配制</td></tr>"
                    "<tr><td>系统适用性</td><td>系统适用性溶液</td><td>取对照品配制</td></tr></table>",
        }],
    }
    groups = [{
        "groupCode": "custom_1789633006443",
        "cardinality": "MANY",
        "enabled": True,
        "sourceMappings": [{
            "sourceType": "LIMS",
            "sectionPattern": "(?:实|试)验过程.*溶液配制",
            "headerPattern": "(?=.*验证项目)(?=.*溶液名称)(?=.*配制方法)",
            "rowPattern": r"(?:^|\|)验证项目=供试品检测(?:\||$)",
            "columnMappings": [
                {"fieldCode": "sample_test.field_001", "columnPattern": "^溶液名称$"},
                {"fieldCode": "sample_test.field_002", "columnPattern": "^配制方法$"},
            ],
        }],
    }]

    result = normalize_instance(instance, groups=groups)

    assert [(item["field_001"], item["field_002"])
            for item in result["custom_1789633006443"]] == [("供试品溶液", "取样品配制")]
    assert len(result["solutions"]) == 2
    assert [item["name"] for item in result["systemSuitabilitySolutions"]] == ["系统适用性溶液"]

    merged = merge_instances([result], groups=groups, normalized=True)["payload"]
    assert merged["custom_1789633006443"][0]["field_001"] == "供试品溶液"
