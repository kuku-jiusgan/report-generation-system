CHAPTER_TITLES = {
    "cover": "封面、审批与目录", "3": "3 实验设计", "4": "4 实验材料",
    "5": "5 验证项目与接受标准", "6": "6 仪器方法", "7": "7 实验过程与结果",
    "8": "8 样品检测结果", "version": "版本记录", "other": "其他内容",
}

SECTION_TITLES = {
    "header": "页眉与文件信息", "approval": "审批信息", "toc": "目录",
    "3.2.limit": "3.2 杂质限度", "3.3.impurity": "3.3 杂质信息",
    "4.1.samples": "4.1 供试品", "4.2.referenceStandards": "4.2 对照品",
    "4.3.instruments": "4.3 仪器", "4.3.columns": "4.4 色谱柱", "4.5.reagents": "4.5 试剂",
    "5.validationSummary": "5 验证项目与接受标准", "6.methodParameters": "6 仪器方法参数",
    "7.1.solutions": "7.1 系统适用性溶液", "7.1.systemSuitability": "7.1 系统适用性结果",
    "7.2.solutions": "7.2 专属性溶液", "7.2.specificity": "7.2 专属性结果",
    "7.3.lodSolutions": "7.3 检出限与定量限溶液", "7.3.lod": "7.3 检出限结果", "7.3.loq": "7.3 定量限结果",
    "7.4.linearityPreparation": "7.4 线性溶液", "7.4.linearity": "7.4 线性结果",
    "7.5.solutions": "7.5 重复性溶液", "7.5.repeatability": "7.5 重复性结果",
    "7.6.solutions": "7.6 中间精密度溶液", "7.6.linearityPreparation": "7.6 中间精密度线性溶液",
    "7.6.linearity": "7.6 线性结果", "7.6.intermediatePrecision": "7.6 中间精密度结果",
    "7.7.solutions": "7.7 准确度溶液", "7.7.blankAmount": "7.7 空白本底", "7.7.accuracy": "7.7 准确度结果",
    "7.8.solutions": "7.8 稳定性溶液", "7.8.solutionStability": "7.8 溶液稳定性结果",
    "7.9.solutions": "7.9 耐用性溶液", "7.9.robustnessSpecificity": "7.9 耐用性专属性",
    "7.9.robustnessSolutions": "7.9 耐用性溶液配置", "7.9.robustnessSequence": "7.9 耐用性序列",
    "7.9.robustnessResult": "7.9 耐用性结果", "8.sampleResults": "8 样品检测结果",
    "versionHistory": "版本记录", "cover": "封面", "narrative": "目的、概述与总结", "attachment": "附件",
}

def chapter_key(section_code: str) -> str:
    if section_code in {"header", "approval", "toc", "cover", "narrative"}: return "cover"
    if section_code == "versionHistory": return "version"
    prefix = section_code.split(".", 1)[0]
    return prefix if prefix in {"3", "4", "5", "6", "7", "8"} else "other"
