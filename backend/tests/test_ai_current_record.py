"""测试 AI 生成字段的 CURRENT_RECORD 模式（按记录生成）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ai_field_generator import (
    needs_per_record_generation,
    resolve_context_values,
    context_variables,
)


def test_needs_per_record_generation_true():
    """配置了 CURRENT_RECORD 模式时返回 True"""
    config = {
        "contextVariables": [
            {"fieldCode": "limit.impurityName", "mode": "CURRENT_RECORD", "required": True}
        ]
    }
    assert needs_per_record_generation(config) is True


def test_needs_per_record_generation_false():
    """没有 CURRENT_RECORD 模式时返回 False"""
    config = {
        "contextVariables": [
            {"fieldCode": "project.name", "mode": "FIRST", "required": True}
        ]
    }
    assert needs_per_record_generation(config) is False


def test_resolve_context_values_current_record():
    """CURRENT_RECORD 模式从当前记录读取字段值"""
    config = {
        "contextVariables": [
            {
                "fieldCode": "limit.impurityName",
                "mode": "CURRENT_RECORD",
                "required": True,
                "defaultValue": ""
            },
            {
                "fieldCode": "limit.detectionLimit",
                "mode": "CURRENT_RECORD",
                "required": True,
                "defaultValue": ""
            }
        ]
    }

    # 模拟当前记录
    current_record = {
        "impurityName": "杂质A",
        "detectionLimit": "0.05%",
        "quantitationLimit": "0.15%"
    }

    values = {}  # 全局值可以为空
    resolved, missing = resolve_context_values(config, values, current_record)

    assert "limit.impurityName" in resolved
    assert resolved["limit.impurityName"] == "杂质A"
    assert "limit.detectionLimit" in resolved
    assert resolved["limit.detectionLimit"] == "0.05%"
    assert len(missing) == 0


def test_resolve_context_values_current_record_missing():
    """CURRENT_RECORD 模式没有当前记录上下文时标记缺失"""
    config = {
        "contextVariables": [
            {"fieldCode": "limit.impurityName", "mode": "CURRENT_RECORD", "required": True, "defaultValue": ""}
        ]
    }

    values = {}
    resolved, missing = resolve_context_values(config, values, current_record=None)

    assert "limit.impurityName" in missing


def test_resolve_context_values_mixed_modes():
    """混合使用 CURRENT_RECORD 和其他模式"""
    config = {
        "contextVariables": [
            {"fieldCode": "project.name", "mode": "FIRST", "required": True, "separator": "、", "suffix": "", "defaultValue": ""},
            {"fieldCode": "limit.impurityName", "mode": "CURRENT_RECORD", "required": True, "defaultValue": ""},
            {"groupCode": "samples", "required": False, "defaultValue": ""}
        ]
    }

    current_record = {"impurityName": "杂质A"}
    values = {
        "project.name": "项目X",
        "samples": [{"sampleName": "样品1"}]
    }

    resolved, missing = resolve_context_values(config, values, current_record)

    assert resolved["project.name"] == "项目X"
    assert resolved["limit.impurityName"] == "杂质A"
    assert '"sampleName"' in resolved["samples"]
    assert len(missing) == 0


def test_context_variables_with_current_record_mode():
    """context_variables 函数接受 CURRENT_RECORD 模式"""
    config = {
        "contextVariables": [
            {"fieldCode": "limit.impurityName", "mode": "CURRENT_RECORD"}
        ]
    }

    variables = context_variables(config)
    assert len(variables) == 1
    assert variables[0]["fieldCode"] == "limit.impurityName"
    assert variables[0].get("mode") == "CURRENT_RECORD"


def test_resolve_context_values_current_record_with_nested_data():
    """CURRENT_RECORD 模式处理嵌套数据（序列化为JSON）"""
    config = {
        "contextVariables": [
            {"fieldCode": "limit.detectionResults", "mode": "CURRENT_RECORD", "required": True, "defaultValue": ""}
        ]
    }

    current_record = {
        "impurityName": "杂质A",
        "detectionResults": [
            {"concentration": "0.05%", "result": "合格"},
            {"concentration": "0.10%", "result": "合格"}
        ]
    }

    values = {}
    resolved, missing = resolve_context_values(config, values, current_record)

    assert "limit.detectionResults" in resolved
    # 嵌套数据应该被序列化为JSON
    assert '"concentration"' in resolved["limit.detectionResults"]
    assert '"0.05%"' in resolved["limit.detectionResults"]
    assert len(missing) == 0


def test_resolve_context_values_current_record_group_uses_record_object():
    """仅配置 groupCode 时，CURRENT_RECORD 使用整条编组记录作为上下文。"""
    config = {
        "contextVariables": [
            {"groupCode": "dingliangxianjieguo", "mode": "CURRENT_RECORD", "required": True}
        ]
    }
    current_record = {
        "field_046": "测试1",
        "summary": {"field_017": 1.7},
        "injections": [{"field_015": 83.32}],
    }

    resolved, missing = resolve_context_values(config, {}, current_record)

    assert '"field_046": "测试1"' in resolved["dingliangxianjieguo"]
    assert '"field_017": 1.7' in resolved["dingliangxianjieguo"]
    assert len(missing) == 0


if __name__ == "__main__":
    print("运行 CURRENT_RECORD 模式测试...")
    test_needs_per_record_generation_true()
    print("✓ 测试1: 检测需要按记录生成")

    test_needs_per_record_generation_false()
    print("✓ 测试2: 检测不需要按记录生成")

    test_resolve_context_values_current_record()
    print("✓ 测试3: 从当前记录读取字段值")

    test_resolve_context_values_current_record_missing()
    print("✓ 测试4: 缺少当前记录上下文")

    test_resolve_context_values_mixed_modes()
    print("✓ 测试5: 混合使用不同模式")

    test_context_variables_with_current_record_mode()
    print("✓ 测试6: context_variables 接受 CURRENT_RECORD")

    test_resolve_context_values_current_record_with_nested_data()
    print("✓ 测试7: 处理嵌套数据")

    print("\n所有测试通过 ✓")
