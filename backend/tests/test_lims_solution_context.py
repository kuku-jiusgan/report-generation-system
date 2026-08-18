from backend.app.services.lims_normalizer import normalize_instance
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
