"""Excel 标准字段的结果落位路径。

编组字段的标准数据路径由字段目录/编组契约生成，Excel 规则里的同名配置
只是历史存储字段，不能覆盖已经变更的编组结构。
"""

from typing import Any


def excel_target_path(field: dict[str, Any], configured_path: Any = None) -> str:
    """返回 Excel 结果应写入/读取的标准路径。

    已归属正式编组的字段使用字段目录生成的路径；未归属编组的字段仍允许
    使用规则中的自定义目标，以兼容历史的扁平字段规则。
    """
    configured = str(configured_path or "").strip()
    canonical = str(field.get("legacyJsonPath") or "").strip()
    group_code = str(field.get("groupCode") or "").strip()
    if canonical and group_code and group_code != "未分类":
        return canonical
    return configured or canonical or str(field.get("fieldCode") or "")
