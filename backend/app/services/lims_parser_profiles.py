HTML_TABLE_PARSER_PROFILES = {
    "impurity": (
        "IMPURITY_LIMIT_TABLE",
        r"(%s:实|试)验设计|参考文件|限度",
        r"(%s=.*(%s:杂质名称|名称))(%s=.*CAS(%s:号|编号|No\.%s)%s)(%s=.*(%s:杂质)%s限度)",
    ),
    "validationSummary": (
        "VALIDATION_SUMMARY_TABLE",
        r"(%s:实|试)验设计|验证(%s:项目|内容)|(%s:可)%s接受标准",
        r"(%s=.*(%s:验证|试验|检验)%s项目|验证内容|项目名称)(%s=.*(%s:可)%s接受标准|接收标准|验收标准|判定标准|Acceptance\s*Criteria)",
    ),
    "limit": (
        "LIMIT_CALCULATION_TABLE",
        r"(%s:实|试)验设计|杂质信息|限度计算",
        r"(%s=.*(%s:杂质)%s名称)(%s=.*(%s:AI值|每日允许摄入量))(%s=.*最大日剂量)(%s=.*杂质限度)(%s=.*(%s:API浓度|供试品溶液中\s*API浓度))(%s=.*(%s:杂质)%s限度浓度)",
    ),
    "methodParameters": ("METHOD_PARAMETER_TABLE", r"仪器方法|分析方法", r"项目.*参数|分析方法"),
    "systemSuitability": (
        "SYSTEM_SUITABILITY_MATRIX",
        r"(%s:实|试)验结果.*系统适用性(%s:结果)%s",
        r"No\.%s.*保留时间.*峰面积",
    ),
    "specificity": (
        "SPECIFICITY_RESULT_TABLE", r"实验结果.*原始数据与处理结果",
        r"杂质名称.*溶液名称.*保留时间.*峰面积",
    ),
    "robustnessSpecificity": (
        "ROBUSTNESS_SPECIFICITY_TABLE", r"实验结果.*原始数据与处理结果", r"溶液名称.*色谱柱1.*色谱柱2",
    ),
    "robustnessSequence": (
        "ROBUSTNESS_SEQUENCE_TABLE", r"实验设计|实验结果", r"溶液.*进样针数.*接受标准",
    ),
}

HTML_TABLE_LEGACY_DEFAULTS = {
    "impurity": (r"实验设计|参考文件|限度", r"杂质名称.*CAS.*限度"),
    "systemSuitability": (
        r"实验结果.*原始数据与处理结果", r"No\.%s.*保留时间.*峰面积",
    ),
}
