from typing import Any


def fixed(output: str, sheet: str, row: int, column: int, required: bool = False) -> dict[str, Any]:
    return {"kind": "FIXED", "name": output, "output": output, "sheet": sheet,
            "row": row, "column": column, "required": required, "enabled": True}


def v49_snapshot() -> dict[str, Any]:
    impurity_count = {"sheet": "首页", "row": 8, "column": 2, "required": True}
    impurity_name = {"sheet": "首页", "row": 9, "column": 2, "rowStep": 1, "columnStep": 0}
    return {"code": "WENXIA_VALIDATION_V49", "name": "文霞动态验证计算表 V49", "rules": [
        fixed("project.name", "首页", 3, 2),
        fixed("document.version", "首页", 4, 6),
        {"kind": "REPEAT_BLOCK", "name": "系统适用性", "output": "systemSuitability",
         "sheet": "系统适用性", "count": impurity_count, "maxRepeat": 15,
         "startColumn": 1, "columnStep": 3, "startRow": 3, "rows": {"start": 3, "end": 8},
         "fields": [
             {"name": "impurityName", "mode": "REPEAT_VALUE", "source": impurity_name, "required": True},
             {"name": "sequence", "mode": "INDEX", "base": 1},
             {"name": "retentionTime", "mode": "CELL", "columnOffset": 1},
             {"name": "peakArea", "mode": "CELL", "columnOffset": 2},
         ], "enabled": True},
        {"kind": "REPEAT_BLOCK", "name": "专属性", "output": "specificity",
         "sheet": "专属性", "count": impurity_count, "maxRepeat": 15,
         "startRow": 2, "rowStep": 5, "startColumn": 1, "rows": {"start": 2, "end": 5},
         "fields": [
             {"name": "impurityName", "mode": "REPEAT_VALUE", "source": impurity_name, "required": True},
             {"name": "solutionName", "mode": "CELL", "columnOffset": 1},
             {"name": "retentionTime", "mode": "CELL", "columnOffset": 2},
             {"name": "peakArea", "mode": "CELL", "columnOffset": 3},
         ], "enabled": True},
    ]}
