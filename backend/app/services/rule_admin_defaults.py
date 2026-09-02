"""模板规则库的静态默认值。

这些是首次初始化时写进数据库的种子：分组显示名、集合分类和默认章节目录。
落库之后它们就以可见配置的形式存在，运行时不再读取本模块；
从 rule_admin.py 拆出来是为了让该文件保持在仓库的 600 行上限内。
"""

STANDARD_FIELD_GROUP_NAMES = {
    "accuracySolutions": "准确度溶液",
    "approval": "审批信息",
    "columns": "色谱柱",
    "document": "文档信息",
    "impurity": "杂质信息",
    "instruments": "仪器设备",
    "intermediatePrecisionSolutions": "中间精密度溶液",
    "lodSolutions": "检出限溶液",
    "methodParameters": "方法参数",
    "project": "项目信息",
    "reagents": "试剂",
    "referenceStandards": "对照品",
    "repeatabilitySolutions": "重复性溶液",
    "robustnessSequence": "耐用性序列",
    "robustnessSolutions": "耐用性溶液",
    "robustnessSpecificity": "耐用性专属性",
    "samples": "样品信息",
    "specificity": "专属性结果",
    "specificitySolutions": "专属性溶液",
    "stabilitySolutions": "稳定性溶液",
    "systemSuitability": "系统适用性",
    "systemSuitabilitySolutions": "系统适用性溶液",
    "validationSummary": "验证结果汇总",
}

SOLUTION_VIEW_COLLECTIONS = {
    "accuracySolutions", "intermediatePrecisionSolutions", "lodSolutions",
    "repeatabilitySolutions", "robustnessSolutions", "specificitySolutions",
    "stabilitySolutions", "systemSuitabilitySolutions",
}

STRUCTURED_UNIT_COLLECTIONS = {
    "approval", "columns", "instruments", "reagents", "referenceStandards", "samples",
}

DEFAULT_TEMPLATE_CHAPTERS = [
    ("", "cover", "封面", None, 0),
    ("", "headerFooter", "页眉与页脚", None, 1),
    ("", "1", "概述", 4, 2),
    ("", "2", "目的", 4, 3),
    ("", "3", "参考文件、限度标准", 4, 4),
    ("3", "3.1", "参考文件", 4, 5), ("3", "3.2", "限度", 4, 6), ("3", "3.3", "杂质信息", 4, 7),
    ("", "4", "物料及仪器信息", 5, 8),
    ("4", "4.1", "供试品", 5, 9), ("4", "4.2", "对照品", 5, 10), ("4", "4.3", "仪器", 5, 11),
    ("4", "4.4", "色谱柱", 6, 12), ("4", "4.5", "试剂", 6, 13),
    ("", "5", "结果汇总", 6, 14), ("5", "5.1", "验证结果汇总", 6, 15), ("5", "5.2", "验证结论", 7, 16),
    ("", "6", "分析方法", 8, 17), ("", "7", "验证内容", 9, 18),
    ("7", "7.1", "系统适用性", 9, 19), ("7", "7.2", "专属性", 10, 20),
    ("7", "7.3", "检测限与定量限", 11, 21), ("7", "7.4", "线性与范围", 12, 22),
    ("7", "7.5", "重复性", 14, 23), ("7", "7.6", "中间精密度", 15, 24),
    ("7", "7.7", "准确度", 18, 25), ("7", "7.8", "溶液稳定性", 20, 26), ("7", "7.9", "耐用性", 21, 27),
    ("", "8", "供试品检测", 22, 28), ("8", "8.1", "溶液配制", 22, 29), ("8", "8.2", "试验过程", 22, 30),
    ("8", "8.3", "可接受标准", 22, 31), ("8", "8.4", "结果及结论", 23, 32), ("8", "8.5", "相关图谱", 23, 33),
    ("", "9", "计算公式", 23, 34), ("", "10", "偏差", 24, 35), ("", "11", "附件", 24, 36),
    ("", "12", "变更历史", 25, 37),
]

SEED_PRESERVED_ROW_LABELS = ["RSD", "结论", "平均", "回归方程", "相关系数", "斜率", "截距"]
SEED_CLEAR_OBJECT_TABLES = ("T3", "T20", "T25")
SEED_MATRIX_TABLES = ("T20", "T25")
SEED_MATRIX_LAYOUT = {"rowFields": [], "rowLabels": [], "scalarCells": []}


def seed_physical_table_index(table_no: str) -> int:
    if not table_no.startswith("T") or not table_no[1:].isdigit():
        return 0
    number = int(table_no[1:])
    if 1 <= number <= 23:
        return number
    if number in (24, 37):
        return 0
    if 25 <= number <= 36:
        return number - 1
    if number == 38:
        return 36
    return 0
