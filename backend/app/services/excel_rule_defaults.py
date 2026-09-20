from datetime import datetime, timezone
import json
from typing import Any

from .excel_standard_path import excel_target_path


EXCEL_FIELD_PATHS = {
    "project.name": "$.project.name",
    "document.version": "$.document.version",
    "impurity.impurityName": "$.impurity[*].impurityName",
    "referenceStandards.name": "$.referenceStandards[*].name",
    "referenceStandards.content": "$.referenceStandards[*].content",
    "systemSuitability.impurityName": "$.systemSuitability[*].impurityName",
    "systemSuitability.solutionName": "$.systemSuitability[*].solutionName",
    "systemSuitability.sequence": "$.systemSuitability[*].sequence",
    "systemSuitability.retentionTime": "$.systemSuitability[*].retentionTime",
    "systemSuitability.peakArea": "$.systemSuitability[*].peakArea",
    "systemSuitability.retentionTimeRsd": "$.systemSuitability[*].retentionTimeRsd",
    "systemSuitability.peakAreaRsd": "$.systemSuitability[*].peakAreaRsd",
    "systemSuitability.conclusion": "$.systemSuitabilityConclusion",
    "specificity.impurityName": "$.specificity[*].impurityName",
    "specificity.solutionName": "$.specificity[*].solutionName",
    "specificity.retentionTime": "$.specificity[*].retentionTime",
    "specificity.peakArea": "$.specificity[*].peakArea",
    "limit.impurityName": "$.limit[*].impurityName",
    "limit.field4": "$.limit[*].field4",
    "limit.field5": "$.limit[*].field5",
    "robustnessSpecificity.solutionName": "$.robustnessSpecificity[*].solutionName",
    "robustnessSpecificity.field2": "$.robustnessSpecificity[*].field2",
    "robustnessSpecificity.field3": "$.robustnessSpecificity[*].field3",
    "uncategorized.field_005": "$.custom.field_005",
    "uncategorized.field_006": "$.custom.field_006",
    "uncategorized.field_007": "$.jiancexian[*].name",
    "uncategorized.field_008": "$.jiancexian[*].field2",
    "uncategorized.field_009": "$.jiancexian[*].field3",
    "uncategorized.field_010": "$.jiancexian[*].field4",
    "uncategorized.field_011": "$.jiancexian[*].field5",
    "uncategorized.field_012": "$.jiancexian[*].field6",
    "uncategorized.field_013": "$.jiancexian[*].field7",
    "uncategorized.field_014": "$.loq[*].sequence",
    "uncategorized.field_015": "$.loq[*].field2",
    "uncategorized.field_016": "$.loq[*].peakArea",
    "uncategorized.field_017": "$.loq[*].field4",
    "uncategorized.field_018": "$.loq[*].field5",
    "uncategorized.field_019": "$.loq[*].field6",
    "uncategorized.field_020": "$.loq[*].field7",
    "uncategorized.field_021": "$.linearity[*].solutionName",
    "uncategorized.field_022": "$.linearity[*].field2",
    "uncategorized.field_023": "$.linearity[*].peakArea",
    "uncategorized.field_024": "$.linearity[*].regressionEquation",
    "uncategorized.field_025": "$.linearity[*].correlationCoefficient",
    "uncategorized.field_026": "$.linearity[*].interceptRatio",
    "uncategorized.field_027": "$.linearity[*].predictedPeakArea",
    "uncategorized.field_029": "$.linearity[*].residualChart",
    "uncategorized.field_047": "$.xianxingjieguo[*].field_047",
    "uncategorized.field_048": "$.xianxingjieguo[*].injections[*].field_048",
    "uncategorized.field_049": "$.chongfuxingjieguo[*].injections[*].field_049",
    "uncategorized.field_050": "$.chongfuxingjieguo[*].injections[*].field_050",
    "uncategorized.field_051": "$.chongfuxingjieguo[*].injections[*].field_051",
    "uncategorized.field_052": "$.chongfuxingjieguo[*].injections[*].field_052",
    "uncategorized.field_053": "$.chongfuxingjieguo[*].injections[*].field_053",
    "uncategorized.field_054": "$.chongfuxingjieguo[*].injections[*].field_054",
    "uncategorized.field_055": "$.chongfuxingjieguo[*].field_055",
    "uncategorized.field_056": "$.chongfuxingjieguo[*].summary.field_056",
    "uncategorized.field_057": "$.chongfuxingjieguo[*].summary.field_057",
    "uncategorized.field_058": "$.chongfuxingjieguo[*].summary.field_058",
    "uncategorized.field_059": "$.chongfuxingjieguo[*].summary.field_059",
    "uncategorized.field_076": "$.custom_1788404594530[*].field_076",
    "uncategorized.field_077": "$.custom_1788404594530[*].injections[*].field_077",
    "uncategorized.field_078": "$.custom_1788404594530[*].injections[*].field_078",
    "uncategorized.field_079": "$.custom_1788404594530[*].injections[*].field_079",
    "uncategorized.field_080": "$.custom_1788404594530[*].injections[*].field_080",
    "uncategorized.field_081": "$.custom_1788404594530[*].injections[*].field_081",
    "uncategorized.field_084": "$.xianxingjieguo[*].summary.field_084",
    **{f"uncategorized.field_{index:03d}": f"$.custom.field_{index:03d}"
       for index in (60, 61, 62, 64, 67, 68, 69, 70, 71, 72, 73, 74, 75, 96)},
    **{f"uncategorized.field_{index:03d}": f"$.custom.field_{index:03d}" for index in range(30, 43)},
    "uncategorized.field_046": "$.dingliangxianjieguo[*].field_046",
}

EXCEL_WORKBOOK_LOCATIONS = {
    "project.name": {"sheet": "首页", "cells": "B3", "matchBy": "固定单元格", "valueColumn": "B"},
    "document.version": {"sheet": "首页", "cells": "F4", "matchBy": "固定单元格", "valueColumn": "F"},
    "impurity.impurityName": {"sheet": "首页", "cells": "B9:B23", "matchBy": "首页 B8 指定杂质数量", "valueColumn": "B"},
    "referenceStandards.name": {"sheet": "对照品配置", "cells": "A3:A*", "matchBy": "非空数据行", "valueColumn": "A（名称）"},
    "referenceStandards.content": {"sheet": "对照品配置", "cells": "C3:C*", "matchBy": "与名称列同一行", "valueColumn": "C（含量）"},
    "systemSuitability.sequence": {"sheet": "系统适用性", "cells": "固定数据行 3:8", "matchBy": "首页 B9 起的杂质顺序 + 进样序号 1-6", "valueColumn": "按行生成，不读取工作表列"},
    "systemSuitability.solutionName": {"sheet": "系统适用性", "cells": "A3:A8、D3:D8、G3:G8……", "matchBy": "每个杂质对应的系统适用性溶液名称", "valueColumn": "第 3i-2 列"},
    "systemSuitability.retentionTime": {"sheet": "系统适用性", "cells": "B3:B8、E3:E8、H3:H8……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i-1 列（B、E、H、K……）"},
    "systemSuitability.peakArea": {"sheet": "系统适用性", "cells": "C3:C8、F3:F8、I3:I8……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i 列（C、F、I、L……）"},
    "systemSuitability.retentionTimeRsd": {"sheet": "系统适用性", "cells": "B9、E9、H9、K9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "保留时间 RSD"},
    "systemSuitability.peakAreaRsd": {"sheet": "系统适用性", "cells": "C9、F9、I9、L9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "峰面积 RSD"},
    "systemSuitability.conclusion": {"sheet": "系统适用性", "cells": "B10", "matchBy": "固定结论单元格", "valueColumn": "结论"},
    "specificity.impurityName": {"sheet": "专属性", "cells": "每个杂质 5 行分块", "matchBy": "首页杂质名称顺序", "valueColumn": "关联杂质名称"},
    "specificity.solutionName": {"sheet": "专属性", "cells": "B 列，每个杂质块 4 行", "matchBy": "杂质名称分块 + 数据行", "valueColumn": "B（溶液名称）"},
    "specificity.retentionTime": {"sheet": "专属性", "cells": "C 列，每个杂质块 4 行", "matchBy": "杂质名称分块 + 数据行", "valueColumn": "C（保留时间）"},
    "specificity.peakArea": {"sheet": "专属性", "cells": "D 列，每个杂质块 4 行", "matchBy": "杂质名称分块 + 数据行", "valueColumn": "D（峰面积）"},
    "uncategorized.field_005": {"sheet": "系统适用性", "cells": "B9、E9、H9、K9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i-1 列（保留时间 RSD）"},
    "uncategorized.field_006": {"sheet": "系统适用性", "cells": "C9、F9、I9、L9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i 列（峰面积 RSD）"},
    "uncategorized.field_007": {"sheet": "检测限与定量限", "cells": "C3:C*", "matchBy": "首页 B8 指定杂质数量", "valueColumn": "C（杂质名称）"},
    "uncategorized.field_008": {"sheet": "检测限与定量限", "cells": "D3:D*", "matchBy": "与杂质名称同一行", "valueColumn": "D（S/N-1）"},
    "uncategorized.field_009": {"sheet": "检测限与定量限", "cells": "E3:E*", "matchBy": "与杂质名称同一行", "valueColumn": "E（S/N-2）"},
    "uncategorized.field_010": {"sheet": "检测限与定量限", "cells": "F3:F*", "matchBy": "与杂质名称同一行", "valueColumn": "F（S/N-3）"},
    "uncategorized.field_011": {"sheet": "检测限与定量限", "cells": "G3:G*", "matchBy": "与杂质名称同一行", "valueColumn": "G（检测限浓度）"},
    "uncategorized.field_012": {"sheet": "检测限与定量限", "cells": "H3:H*", "matchBy": "与杂质名称同一行", "valueColumn": "H（相当于供试品中含量）"},
    "uncategorized.field_013": {"sheet": "检测限与定量限", "cells": "I3:I*", "matchBy": "与杂质名称同一行", "valueColumn": "I（占限度百分比）"},
    "uncategorized.field_014": {"sheet": "检测限与定量限", "cells": "D8:D13、D16:D21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "D（No.）"},
    "uncategorized.field_015": {"sheet": "检测限与定量限", "cells": "E8:E13、E16:E21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "E（信噪比 S/N）"},
    "uncategorized.field_016": {"sheet": "检测限与定量限", "cells": "F8:F13、F16:F21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "F（峰面积）"},
    "uncategorized.field_017": {"sheet": "检测限与定量限", "cells": "G8:G13、G16:G21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "G（峰面积 RSD）"},
    "uncategorized.field_018": {"sheet": "检测限与定量限", "cells": "H8:H13、H16:H21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "H（定量限浓度）"},
    "uncategorized.field_019": {"sheet": "检测限与定量限", "cells": "I8:I13、I16:I21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "I（相当于供试品含量）"},
    "uncategorized.field_020": {"sheet": "检测限与定量限", "cells": "J8:J13、J16:J21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "J（占限度百分比）"},
    "uncategorized.field_046": {"sheet": "检测限与定量限", "cells": "C(首页!B8+5)、之后每隔 8 行", "matchBy": "杂质数量决定定量限首个表头行", "valueColumn": "C（杂质名称）"},
    "uncategorized.field_021": {"sheet": "线性", "cells": "C2:G2、C26:G26……", "matchBy": "每个杂质 5 个水平", "valueColumn": "溶液名称"},
    "uncategorized.field_022": {"sheet": "线性", "cells": "C3:G3、C27:G27……", "matchBy": "每个杂质 5 个水平", "valueColumn": "实际浓度"},
    "uncategorized.field_023": {"sheet": "线性", "cells": "C4:G4、C28:G28……", "matchBy": "每个杂质 5 个水平", "valueColumn": "峰面积"},
    "uncategorized.field_024": {"sheet": "线性", "cells": "C6、C30、C54……", "matchBy": "每个杂质一条", "valueColumn": "线性回归方程"},
    "uncategorized.field_025": {"sheet": "线性", "cells": "C7、C31、C55……", "matchBy": "每个杂质一条", "valueColumn": "线性相关系数 R²"},
    "uncategorized.field_026": {"sheet": "线性", "cells": "G7、G31、G55……", "matchBy": "每个杂质一条", "valueColumn": "截距/100%浓度峰面积"},
    "uncategorized.field_027": {"sheet": "线性", "cells": "C8:G8、C32:G32……", "matchBy": "每个杂质 5 个水平", "valueColumn": "预测峰面积"},
    "uncategorized.field_029": {"sheet": "线性", "cells": "图表对象", "matchBy": "每个杂质的普通线性残差图", "valueColumn": "残差图"},
    "uncategorized.field_047": {"sheet": "线性", "cells": "A2、A26、A50……", "matchBy": "每个杂质分块的首个结果表", "valueColumn": "A（杂质名称）"},
    "uncategorized.field_048": {"sheet": "线性", "cells": "C9:G9、C33:G33……", "matchBy": "每个杂质 5 个水平", "valueColumn": "残差"},
    "uncategorized.field_049": {"sheet": "重复性跟中间精密度", "cells": "D3:D8、D36:D41……", "matchBy": "每个杂质 6 次测定", "valueColumn": "D（编号）"},
    "uncategorized.field_050": {"sheet": "重复性跟中间精密度", "cells": "E3:E8、E36:E41……", "matchBy": "每个杂质 6 次测定", "valueColumn": "E（称样量）"},
    "uncategorized.field_051": {"sheet": "重复性跟中间精密度", "cells": "F3:F8、F36:F41……", "matchBy": "每个杂质 6 次测定", "valueColumn": "F（保留时间）"},
    "uncategorized.field_052": {"sheet": "重复性跟中间精密度", "cells": "G3:G8、G36:G41……", "matchBy": "每个杂质 6 次测定", "valueColumn": "G（峰面积）"},
    "uncategorized.field_053": {"sheet": "重复性跟中间精密度", "cells": "H3:H8、H36:H41……", "matchBy": "每个杂质 6 次测定", "valueColumn": "H（测得浓度）"},
    "uncategorized.field_054": {"sheet": "重复性跟中间精密度", "cells": "I3:I8、I36:I41……", "matchBy": "每个杂质 6 次测定", "valueColumn": "I（相当供试品中含量）"},
    "uncategorized.field_055": {"sheet": "重复性跟中间精密度", "cells": "A2、A35、A68……", "matchBy": "每个杂质分块的首个结果表", "valueColumn": "A（杂质名称）"},
    "uncategorized.field_056": {"sheet": "重复性跟中间精密度", "cells": "F9、F42、F75……", "matchBy": "每个杂质重复性汇总行", "valueColumn": "保留时间 RSD"},
    "uncategorized.field_057": {"sheet": "重复性跟中间精密度", "cells": "I9、I42、I75……", "matchBy": "每个杂质重复性汇总行", "valueColumn": "相当供试品中含量 RSD"},
    "uncategorized.field_058": {"sheet": "重复性跟中间精密度", "cells": "F11 与 I11、F44 与 I44……", "matchBy": "每个杂质重复性汇总行", "valueColumn": "含量 95% 置信区间"},
    "uncategorized.field_059": {"sheet": "重复性跟中间精密度", "cells": "F12 与 I12、F45 与 I45……", "matchBy": "每个杂质重复性汇总行", "valueColumn": "占理论含量百分比区间"},
    "uncategorized.field_084": {"sheet": "线性", "cells": "由实际浓度与峰面积生成", "matchBy": "每个杂质的首个结果表", "valueColumn": "回归曲线图"},
    **{f"uncategorized.field_{index:03d}": {
        "sheet": "准确度", "cells": f"{column}16:{column}24、{column}44:{column}52……",
        "matchBy": "每个杂质的准确度试验结果表，每 28 行一组", "valueColumn": column,
    } for index, column in {61: "E", 62: "F", 64: "G", 67: "D", 68: "H",
                            69: "I", 70: "J", 71: "K", 72: "L"}.items()},
    "uncategorized.field_060": {"sheet": "准确度", "cells": "A14、A42、A70……", "matchBy": "每个杂质的准确度试验结果表", "valueColumn": "杂质名称"},
    "uncategorized.field_073": {"sheet": "准确度", "cells": "G25、G53、G81……", "matchBy": "每个杂质的准确度试验结果表", "valueColumn": "平均回收率"},
    "uncategorized.field_074": {"sheet": "准确度", "cells": "G26、G54、G82……", "matchBy": "每个杂质的准确度试验结果表", "valueColumn": "RSD"},
    "uncategorized.field_075": {"sheet": "准确度", "cells": "F27 与 K27、F55 与 K55……", "matchBy": "每个杂质的准确度试验结果表", "valueColumn": "95%置信区间"},
    "uncategorized.field_096": {"sheet": "准确度", "cells": "G28、G56、G84……", "matchBy": "每个杂质的准确度试验结果表", "valueColumn": "结论"},
    "uncategorized.field_076": {"sheet": "溶液稳定性", "cells": "A2、A11、A20……", "matchBy": "每个杂质的溶液稳定性试验结果表，每 9 行一组", "valueColumn": "A（杂质名称）"},
    **{f"uncategorized.field_{index:03d}": {
        "sheet": "溶液稳定性", "cells": f"{column}4:{column}9、{column}13:{column}18……",
        "matchBy": "每个杂质的溶液稳定性试验结果表，每 9 行一组", "valueColumn": column,
    } for index, column in {77: "C", 78: "D", 79: "E", 80: "F", 81: "G"}.items()},
    "uncategorized.field_030": {"sheet": "重复性跟中间精密度", "cells": "D3:D8、D35:D40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "No"},
    "uncategorized.field_031": {"sheet": "重复性跟中间精密度", "cells": "E3:E8、E35:E40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "E（称样量）"},
    "uncategorized.field_032": {"sheet": "重复性跟中间精密度", "cells": "F3:F8、F35:F40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "保留时间"},
    "uncategorized.field_033": {"sheet": "重复性跟中间精密度", "cells": "G3:G8、G35:G40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "峰面积"},
    "uncategorized.field_034": {"sheet": "重复性跟中间精密度", "cells": "H3:H8、H35:H40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "测得浓度"},
    "uncategorized.field_035": {"sheet": "重复性跟中间精密度", "cells": "I3:I8、I35:I40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "相当供试品中含量"},
    "uncategorized.field_036": {"sheet": "重复性跟中间精密度", "cells": "F9、F42……", "matchBy": "每个杂质汇总行", "valueColumn": "RSD"},
    "uncategorized.field_037": {"sheet": "重复性跟中间精密度", "cells": "F11、F44……", "matchBy": "每个杂质汇总行", "valueColumn": "含量-95%置信下限"},
    "uncategorized.field_038": {"sheet": "重复性跟中间精密度", "cells": "I11、I44……", "matchBy": "每个杂质汇总行", "valueColumn": "含量-95%置信上限"},
    "uncategorized.field_039": {"sheet": "重复性跟中间精密度", "cells": "E10、E43……", "matchBy": "每个杂质汇总行", "valueColumn": "RSD-95%置信下限"},
    "uncategorized.field_040": {"sheet": "重复性跟中间精密度", "cells": "H10、H43……", "matchBy": "每个杂质汇总行", "valueColumn": "RSD-95%置信上限"},
    "uncategorized.field_041": {"sheet": "重复性跟中间精密度", "cells": "F12、F45……", "matchBy": "每个杂质汇总行", "valueColumn": "占理论含量百分比上限"},
    "uncategorized.field_042": {"sheet": "重复性跟中间精密度", "cells": "I12、I45……", "matchBy": "每个杂质汇总行", "valueColumn": "占理论含量百分比下限"},
}


DETECTION_LIMIT_COLUMNS = {
    "uncategorized.field_007": 3,
    "uncategorized.field_008": 4,
    "uncategorized.field_009": 5,
    "uncategorized.field_010": 6,
    "uncategorized.field_011": 7,
    "uncategorized.field_012": 8,
    "uncategorized.field_013": 9,
}

QUANTITATION_LIMIT_COLUMNS = {
    "uncategorized.field_014": 4,
    "uncategorized.field_015": 5,
    "uncategorized.field_016": 6,
    "uncategorized.field_017": 7,
    "uncategorized.field_018": 8,
    "uncategorized.field_019": 9,
    "uncategorized.field_020": 10,
}

LINEARITY_ROWS = {
    "uncategorized.field_021": 2,
    "uncategorized.field_022": 3,
    "uncategorized.field_023": 4,
    "uncategorized.field_027": 8,
    "uncategorized.field_048": 9,
}
LINEARITY_DIRECT_CELLS = {
    "uncategorized.field_024": (6, 3),
    "uncategorized.field_025": (7, 3),
    "uncategorized.field_026": (7, 7),
}

REPEATABILITY_DETAIL_COLUMNS = {
    "uncategorized.field_030": 4, "uncategorized.field_031": 5,
    "uncategorized.field_032": 6, "uncategorized.field_033": 7,
    "uncategorized.field_034": 8, "uncategorized.field_035": 9,
}
REPEATABILITY_SUMMARY_CELLS = {
    "uncategorized.field_036": (9, 6), "uncategorized.field_037": (11, 6),
    "uncategorized.field_038": (11, 9), "uncategorized.field_039": (10, 5),
    "uncategorized.field_040": (10, 8), "uncategorized.field_041": (12, 6),
    "uncategorized.field_042": (12, 9),
}
CURRENT_REPEATABILITY_DETAIL_COLUMNS = {
    "uncategorized.field_049": 4, "uncategorized.field_050": 5,
    "uncategorized.field_051": 6, "uncategorized.field_052": 7,
    "uncategorized.field_053": 8, "uncategorized.field_054": 9,
}
CURRENT_REPEATABILITY_SUMMARY_CELLS = {
    "uncategorized.field_056": (9, 6), "uncategorized.field_057": (9, 9),
}
CURRENT_REPEATABILITY_INTERVAL_CELLS = {
    "uncategorized.field_058": (11, (6, 9)),
    "uncategorized.field_059": (12, (6, 9)),
}
ACCURACY_DETAIL_COLUMNS = {
    "uncategorized.field_061": 5, "uncategorized.field_062": 6,
    "uncategorized.field_064": 7, "uncategorized.field_067": 4,
    "uncategorized.field_068": 8, "uncategorized.field_069": 9,
    "uncategorized.field_070": 10, "uncategorized.field_071": 11,
    "uncategorized.field_072": 12,
}
ACCURACY_SUMMARY_CELLS = {
    "uncategorized.field_060": (14, 1),
    "uncategorized.field_073": (25, 7),
    "uncategorized.field_074": (26, 7),
    "uncategorized.field_096": (28, 7),
}
ACCURACY_FIELDS = {*ACCURACY_DETAIL_COLUMNS, *ACCURACY_SUMMARY_CELLS, "uncategorized.field_075"}
STABILITY_DETAIL_COLUMNS = {
    "uncategorized.field_077": 3, "uncategorized.field_078": 4,
    "uncategorized.field_079": 5, "uncategorized.field_080": 6,
    "uncategorized.field_081": 7,
}
STABILITY_FIELDS = {"uncategorized.field_076", *STABILITY_DETAIL_COLUMNS}
EXCLUSIVE_EXCEL_FIELDS = {*ACCURACY_FIELDS, *STABILITY_FIELDS}
EXCEL_ONLY_FIELDS = {
    *EXCLUSIVE_EXCEL_FIELDS,
    *CURRENT_REPEATABILITY_DETAIL_COLUMNS,
    "uncategorized.field_055",
    *CURRENT_REPEATABILITY_SUMMARY_CELLS,
    *CURRENT_REPEATABILITY_INTERVAL_CELLS,
}


def _sync_repeated_field_catalog(database: Any, repeated_fields: tuple[str, ...]) -> None:
    with database.connect() as connection:
        placeholders = ",".join("%s" for _ in repeated_fields)
        connection.execute(
            f"UPDATE lims_field_catalog SET cardinality='MANY' WHERE field_code IN ({placeholders})",
            repeated_fields,
        )
        connection.execute(
            f"""UPDATE lims_field_catalog
                SET group_code=(SELECT gf.group_code FROM system_field_group_fields gf
                                WHERE gf.field_code=lims_field_catalog.field_code LIMIT 1)
                WHERE field_code IN ({placeholders})
                  AND EXISTS(SELECT 1 FROM system_field_group_fields gf
                             WHERE gf.field_code=lims_field_catalog.field_code)""",
            repeated_fields,
        )
        connection.execute(
            f"DELETE FROM system_field_catalog_fields WHERE field_code IN ({placeholders})",
            repeated_fields,
        )


def _sync_repeatability_group_chapter(database: Any) -> None:
    with database.connect() as connection:
        group = connection.execute(
            """SELECT DISTINCT gf.group_code FROM system_field_group_fields gf
               WHERE gf.field_code IN ({}) LIMIT 1""".format(
                ",".join("%s" for _ in REPEATABILITY_DETAIL_COLUMNS)
            ), tuple(REPEATABILITY_DETAIL_COLUMNS),
        ).fetchone()
        chapter = connection.execute(
            "SELECT id FROM system_field_catalog_chapters WHERE code='7.5' LIMIT 1"
        ).fetchone()
        if not group or not chapter:
            return
        connection.execute(
            "INSERT IGNORE INTO system_field_catalog_groups(group_code,chapter_id) VALUES(%s,%s)",
            (group["group_code"], chapter["id"]),
        )


def _ensure_repeated_field_contracts(database: Any) -> None:
    repeated_fields = (*DETECTION_LIMIT_COLUMNS, *QUANTITATION_LIMIT_COLUMNS,
                       *LINEARITY_ROWS, *LINEARITY_DIRECT_CELLS,
                       "uncategorized.field_029", "uncategorized.field_047",
                       "uncategorized.field_084",
                       "uncategorized.field_046",
                       *EXCEL_ONLY_FIELDS,
                       *REPEATABILITY_DETAIL_COLUMNS, *REPEATABILITY_SUMMARY_CELLS)
    _sync_repeated_field_catalog(database, repeated_fields)
    _sync_repeatability_group_chapter(database)


def _ensure_quantitation_impurity_name_contract(database: Any) -> None:
    """杂质名称来自定量限分块，必须保留每个杂质一条记录。"""
    with database.connect() as connection:
        connection.execute(
            """UPDATE lims_field_catalog
               SET cardinality='MANY', group_code=COALESCE(
                   (SELECT gf.group_code FROM system_field_group_fields gf
                    WHERE gf.field_code='uncategorized.field_046' LIMIT 1), group_code)
               WHERE field_code='uncategorized.field_046'"""
        )


def _rule_config(field_code: str, source_path: str) -> dict[str, Any]:
    config = {
        "sourcePath": source_path,
        "workbookFormat": "WENXIA_VALIDATION_V49",
        "valueMode": "CACHED",
        "layout": "VBA_FIXED_BLOCKS",
        "workbookLocation": EXCEL_WORKBOOK_LOCATIONS.get(field_code, {}),
    }
    if field_code == "systemSuitability.conclusion":
        config.update({"mode": "FIXED_CELL", "sheet": "系统适用性", "row": 10, "column": 2})
    elif field_code.startswith("systemSuitability."):
        field = field_code.rsplit(".", 1)[-1]
        if field == "impurityName":
            config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 3, "rowEnd": 3,
                           "repeatValueSource": {"sheet": "首页", "row": 9, "column": 2, "rowStep": 1},
                           "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                           "maxRepeat": 15, "valueMode": "REPEAT_VALUE"})
            return config
        if field in {"retentionTimeRsd", "peakAreaRsd"}:
            config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 9, "rowEnd": 9,
                           "startColumn": 2 if field == "retentionTimeRsd" else 3, "columnStep": 3,
                           "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                           "maxRepeat": 15, "valueMode": "CELL"})
            return config
        config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 3, "rowEnd": 8,
                       "startColumn": 2 if field == "retentionTime" else 3 if field == "peakArea" else 1,
                       "columnStep": 3, "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "INDEX" if field == "sequence" else "CELL",
                       "indexBase": 1})
        if field == "sequence":
            config.update({"generateSequence": True, "sequenceDependency": "systemSuitability.peakArea"})
    elif field_code.startswith("specificity."):
        field = field_code.rsplit(".", 1)[-1]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "专属性", "rowStart": 2, "rowEnd": 5,
                       "startColumn": {"solutionName": 2, "retentionTime": 3, "peakArea": 4}.get(field, 1),
                       "columnStep": 0, "rowStep": 5, "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
        if field == "impurityName":
            config.update({"valueMode": "REPEAT_VALUE", "repeatValueSource": {
                "sheet": "专属性", "row": 2, "column": 1, "rowStep": 5, "columnStep": 0,
            }})
    elif field_code in {"uncategorized.field_005", "uncategorized.field_006"}:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 9, "rowEnd": 9,
                       "startColumn": 2 if field_code.endswith("005") else 3, "columnStep": 3,
                       "rowStep": 0, "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code == "uncategorized.field_046":
        config.update({"mode": "REPEAT_BLOCK", "sheet": "检测限与定量限", "rowStart": 8, "rowEnd": 8,
                       "startColumn": 3, "columnStep": 0, "rowStep": 8,
                       "rowStartOffsetFromRepeatCount": 5, "rowCount": 1,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in DETECTION_LIMIT_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "检测限与定量限", "rowStart": 3, "rowEnd": 3,
                       "startColumn": DETECTION_LIMIT_COLUMNS[field_code], "columnStep": 0, "rowStep": 1,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in QUANTITATION_LIMIT_COLUMNS:
        summary = field_code in {
            "uncategorized.field_017", "uncategorized.field_018",
            "uncategorized.field_019", "uncategorized.field_020",
        } and str(source_path).startswith("$.dingliangxianjieguo")
        config.update({"mode": "REPEAT_BLOCK", "sheet": "检测限与定量限", "rowStart": 8, "rowEnd": 13,
                       "startColumn": QUANTITATION_LIMIT_COLUMNS[field_code], "columnStep": 0, "rowStep": 8,
                       "rowStartOffsetFromRepeatCount": 6, "rowCount": 1 if summary else 6,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code == "uncategorized.field_047":
        config.update({"mode": "REPEAT_BLOCK", "sheet": "线性", "rowStart": 2, "rowEnd": 2,
                       "startColumn": 1, "rowStep": 24,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in LINEARITY_ROWS:
        row = LINEARITY_ROWS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "线性", "rowStart": row, "rowEnd": row,
                       "startColumn": 3, "rowStep": 24, "valueCountMode": "UNTIL_BLANK", "maxValueCount": 100,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "HORIZONTAL_CELL"})
    elif field_code in LINEARITY_DIRECT_CELLS:
        row, column = LINEARITY_DIRECT_CELLS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "线性", "rowStart": row, "rowEnd": row,
                       "startColumn": column, "rowStep": 24,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code == "uncategorized.field_029":
        config.update({"mode": "CHART_IMAGE", "sheet": "线性",
                       "pointsPerTest": 1 if ".summary." in source_path else 5})
    elif field_code == "uncategorized.field_084":
        config.update({"mode": "LINEAR_REGRESSION_CHART", "sheet": "线性", "pointsPerTest": 1})
    elif field_code == "uncategorized.field_055":
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度",
                       "rowStart": 2, "rowEnd": 2, "startColumn": 1, "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in CURRENT_REPEATABILITY_DETAIL_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度",
                       "rowStart": 3, "rowEnd": 8,
                       "startColumn": CURRENT_REPEATABILITY_DETAIL_COLUMNS[field_code],
                       "columnStep": 0, "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in CURRENT_REPEATABILITY_SUMMARY_CELLS:
        row, column = CURRENT_REPEATABILITY_SUMMARY_CELLS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度",
                       "rowStart": row, "rowEnd": row, "startColumn": column,
                       "columnStep": 0, "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in CURRENT_REPEATABILITY_INTERVAL_CELLS:
        row, columns = CURRENT_REPEATABILITY_INTERVAL_CELLS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度",
                       "rowStart": row, "rowEnd": row, "pairColumns": list(columns),
                       "pairSeparator": "～", "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL_PAIR"})
    elif field_code in ACCURACY_DETAIL_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "准确度", "rowStart": 16, "rowEnd": 24,
                       "startColumn": ACCURACY_DETAIL_COLUMNS[field_code], "rowStep": 28,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15,
                       "valueMode": "MERGED_CELL" if field_code in {
                           "uncategorized.field_067", "uncategorized.field_070", "uncategorized.field_072",
                       } else "CELL"})
    elif field_code in ACCURACY_SUMMARY_CELLS:
        row, column = ACCURACY_SUMMARY_CELLS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "准确度", "rowStart": row, "rowEnd": row,
                       "startColumn": column, "rowStep": 28,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code == "uncategorized.field_075":
        config.update({"mode": "REPEAT_BLOCK", "sheet": "准确度", "rowStart": 27, "rowEnd": 27,
                       "pairColumns": [6, 11], "pairSeparator": "～", "rowStep": 28,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL_PAIR"})
    elif field_code == "uncategorized.field_076":
        config.update({"mode": "REPEAT_BLOCK", "sheet": "溶液稳定性",
                       "rowStart": 2, "rowEnd": 2, "startColumn": 1, "rowStep": 9,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in STABILITY_DETAIL_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "溶液稳定性",
                       "rowStart": 4, "rowEnd": 9,
                       "startColumn": STABILITY_DETAIL_COLUMNS[field_code], "rowStep": 9,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in REPEATABILITY_DETAIL_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度", "rowStart": 3, "rowEnd": 8,
                       "startColumn": REPEATABILITY_DETAIL_COLUMNS[field_code], "columnStep": 0, "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in REPEATABILITY_SUMMARY_CELLS:
        row, column = REPEATABILITY_SUMMARY_CELLS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度", "rowStart": row, "rowEnd": row,
                       "startColumn": column, "columnStep": 0, "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    return config


def ensure_excel_field_rules(database: Any) -> None:
    """补齐 Excel 规则，并同步编组字段的标准结果路径。"""
    _ensure_repeated_field_contracts(database)
    _ensure_quantitation_impurity_name_contract(database)
    for field_code, default_path in EXCEL_FIELD_PATHS.items():
        field = database.get_lims_field(field_code)
        if not field:
            continue
        source_path = excel_target_path(field, str(field.get("legacyJsonPath") or "") or default_path)
        field_rules = database.list_system_field_rules(field_code)
        if len(field_rules) > 1:
            raise ValueError(f"字段 {field_code} 存在多条提取规则，请先解决规则冲突")
        existing = [rule for rule in field_rules if rule.get("sourceType") == "EXCEL"]
        if existing:
            if field_code in EXCLUSIVE_EXCEL_FIELDS and any(
                rule.get("sourceType") != "EXCEL" for rule in field_rules
            ):
                raise ValueError(f"字段 {field_code} 同时存在 Excel 与其他来源规则，请先解决来源冲突")
            for rule in existing:
                config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
                desired_row_count = 1 if (
                    field_code in {"uncategorized.field_017", "uncategorized.field_018",
                                   "uncategorized.field_019", "uncategorized.field_020"}
                    and source_path.startswith("$.dingliangxianjieguo")
                ) else None
                needs_row_count = desired_row_count is not None and config.get("rowCount") != desired_row_count
                needs_field_config = field_code in {
                    "uncategorized.field_046", "uncategorized.field_047",
                    "uncategorized.field_048", "uncategorized.field_029",
                    "uncategorized.field_084",
                } or field_code.startswith("systemSuitability.") \
                    or field_code in LINEARITY_DIRECT_CELLS or field_code in EXCEL_ONLY_FIELDS
                if config.get("sourcePath") == source_path and not needs_row_count and not needs_field_config:
                    continue
                updated_config = _rule_config(field_code, source_path) if needs_field_config else {**config, "sourcePath": source_path}
                if desired_row_count is not None:
                    updated_config["rowCount"] = desired_row_count
                database.save_system_field_rule(
                    {**rule, "config": updated_config}, rule.get("id")
                )
            continue
        if field_rules and field_code not in EXCEL_ONLY_FIELDS:
            continue
        replaceable = ([rule for rule in field_rules if rule.get("sourceType") in ({"LIMS", "AI"} if field_code in EXCLUSIVE_EXCEL_FIELDS else {"LIMS"})]
                       if field_code in EXCEL_ONLY_FIELDS else [])
        if len(replaceable) > 1:
            raise ValueError(f"字段 {field_code} 存在多条旧来源规则，不能确定要替换的规则")
        if replaceable:
            database.save_system_field_rule({
                **replaceable[0], "name": "文霞 V49 验证结果计算页", "sourceType": "EXCEL",
                "priority": 50, "transform": "TRIM", "enabled": True,
                "config": _rule_config(field_code, source_path),
            }, replaceable[0].get("id"))
            continue
        database.save_system_field_rule({
            "fieldCode": field_code, "name": "文霞 V49 验证结果计算页", "sourceType": "EXCEL",
            "priority": 50, "transform": "TRIM", "enabled": True,
            "config": _rule_config(field_code, source_path),
        })
