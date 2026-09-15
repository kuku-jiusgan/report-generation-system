"""测试 AI 生成规则的上下文变量支持选择编组"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ai_field_generator import context_variables, resolve_context_values


def test_context_variables_with_field_code():
    """上下文变量仍支持传统的 fieldCode"""
    config = {
        "contextVariables": [
            {"fieldCode": "sample.name", "mode": "FIRST", "required": True}
        ]
    }
    variables = context_variables(config)
    assert len(variables) == 1
    assert variables[0]["fieldCode"] == "sample.name"


def test_context_variables_with_group_code():
    """上下文变量支持新的 groupCode"""
    config = {
        "contextVariables": [
            {"groupCode": "samples", "required": True}
        ]
    }
    variables = context_variables(config)
    assert len(variables) == 1
    assert variables[0]["groupCode"] == "samples"


def test_context_variables_mixed():
    """上下文变量可以混合使用 fieldCode 和 groupCode"""
    config = {
        "contextVariables": [
            {"fieldCode": "project.name", "mode": "FIRST"},
            {"groupCode": "samples", "required": True},
            {"fieldCode": "instrument.model", "mode": "FIRST"}
        ]
    }
    variables = context_variables(config)
    assert len(variables) == 3
    assert variables[0]["fieldCode"] == "project.name"
    assert variables[1]["groupCode"] == "samples"
    assert variables[2]["fieldCode"] == "instrument.model"


def test_resolve_context_values_with_field():
    """解析字段类型的上下文变量"""
    config = {
        "contextVariables": [
            {"fieldCode": "sample.name", "mode": "FIRST", "required": True, "separator": "、", "suffix": "", "defaultValue": ""}
        ]
    }
    values = {"sample.name": "样品A"}
    resolved, missing = resolve_context_values(config, values)
    assert "sample.name" in resolved
    assert resolved["sample.name"] == "样品A"
    assert len(missing) == 0


def test_resolve_context_values_with_group():
    """解析编组类型的上下文变量，返回 JSON 字符串"""
    config = {
        "contextVariables": [
            {"groupCode": "samples", "required": True, "separator": "、", "suffix": "", "defaultValue": ""}
        ]
    }
    values = {
        "samples": [
            {"sampleName": "样品A", "batchNo": "20240101"},
            {"sampleName": "样品B", "batchNo": "20240102"}
        ]
    }
    resolved, missing = resolve_context_values(config, values)
    assert "samples" in resolved
    assert '"sampleName": "样品A"' in resolved["samples"]
    assert '"batchNo": "20240101"' in resolved["samples"]
    assert len(missing) == 0


def test_resolve_context_values_group_missing():
    """编组数据缺失时使用默认值"""
    config = {
        "contextVariables": [
            {"groupCode": "samples", "required": False, "defaultValue": "无样品数据"}
        ]
    }
    values = {}
    resolved, missing = resolve_context_values(config, values)
    assert resolved["samples"] == "无样品数据"
    assert len(missing) == 0


def test_resolve_context_values_group_required_missing():
    """必填的编组数据缺失时报告缺失"""
    config = {
        "contextVariables": [
            {"groupCode": "samples", "required": True, "defaultValue": ""}
        ]
    }
    values = {}
    resolved, missing = resolve_context_values(config, values)
    assert "samples" in missing


def test_resolve_context_values_mixed():
    """混合解析字段和编组"""
    config = {
        "contextVariables": [
            {"fieldCode": "project.name", "mode": "FIRST", "required": True, "separator": "、", "suffix": "", "defaultValue": ""},
            {"groupCode": "samples", "required": True, "separator": "、", "suffix": "", "defaultValue": ""}
        ]
    }
    values = {
        "project.name": "项目X",
        "samples": [{"sampleName": "样品A"}]
    }
    resolved, missing = resolve_context_values(config, values)
    assert resolved["project.name"] == "项目X"
    assert '"sampleName": "样品A"' in resolved["samples"]
    assert len(missing) == 0


def test_context_variables_backward_compatible():
    """向后兼容旧的 inputFields 格式"""
    config = {
        "inputFields": ["field1", "field2"]
    }
    variables = context_variables(config)
    assert len(variables) == 2
    assert variables[0]["fieldCode"] == "field1"
    assert variables[1]["fieldCode"] == "field2"
