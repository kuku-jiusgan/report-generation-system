from typing import Any

from .rule_admin_defaults import SOLUTION_TABLE_COLUMN_PATTERNS, SOLUTION_TABLE_DEFAULTS


RAW_UNIT_FIELDS: dict[str, tuple[str, dict[str, list[str]]]] = {
    "samples": ("Sample", {
        "sampleName": ["sampleName"], "batchNo": ["batchNo"],
        "specification": ["ext$.spackagetype"], "clientName": ["clientName"],
        "remark": ["additionalContent"], "sampleNumber": ["sampleNumber"],
        "manufacturer": ["manufactor"], "appearance": ["ext$.samplecolor"],
    }),
    "referenceStandards": ("Standard", {
        "name": ["ext$.mtlname", "ext$.stockmtlname"],
        "content": ["ext$.content", "ext$.purity", "ext$.titer"],
        "batchNo": ["batchNo"], "manufacturer": ["manufacturerVendorId"],
        "expiryDate": ["validDate"], "stockNo": ["stockNo"],
    }),
    "instruments": ("Equipment", {
        "instrumentName": ["equiptName"], "model": ["specification"], "assetNo": ["equiptNo"],
        "manufacturer": ["prodVendorId"], "calibrationExpiryDate": ["ext$.checkvalidate"],
        "location": ["loc"],
    }),
    "columns": ("Chromatogram", {
        "name": ["ext$.model", "ext$.stationaryphase"], "specification": ["chromatogramSpec"],
        "serialNo": ["chromatogramNo"], "manufacturer": ["vendorName"],
        "stationaryPhase": ["ext$.stationaryphase"],
    }),
    "reagents": ("Reagent", {
        "name": ["ext$.mtlname", "ext$.stockmtlname"], "grade": ["ext$.mtllevel"],
        "batchNo": ["batchNo"], "manufacturer": ["manufacturerVendorId"],
        "expiryDate": ["validDate"], "stockNo": ["stockNo", "id"],
    }),
    "weighings": ("Weighing", {
        "name": ["ext$.mtlname", "ext$.stockmtlname"], "batchNo": ["batchNo"],
        "weight": ["weight"], "weightUnit": ["weightUnit"], "weightDate": ["weightDate"],
        "equipmentName": ["equiptName"], "equipmentNo": ["equiptNo"],
        "responseValue": ["responseValue"],
    }),
}

INSTANCE_FIELDS = {
    "project": {"id": "projectId", "name": "title"},
    "document": {"code": "instanceId", "version": "version"},
    "approval": {"field1": "auditEvents[*].role", "field3": "auditEvents[*].name", "date": "auditEvents[*].date"},
}

TABLES: dict[str, dict[str, Any]] = {
    "impurity": {
        "sectionPattern": r"(?:实|试)验设计|参考文件|限度",
        "headerPattern": r"(?=.*(?:杂质名称|名称))(?=.*CAS)(?=.*(?:杂质)?限度)",
        "columns": {
            "impurityName": r"^(?:杂质名称|名称|化合物名称)$", "field2": r"^CAS(?:号|编号|No\.?)?$",
            "field3": r"^(?:化学)?结构式?$|^结构图片$", "field4": r"^(?:杂质)?限度(?:\([^)]*\))?$|^限量",
        },
    },
    "limit": {
        "sectionPattern": r"(?:实|试)验设计|杂质信息|限度计算",
        "headerPattern": r"(?=.*(?:杂质)?名称)(?=.*(?:AI值|每日允许摄入量))(?=.*最大日剂量)(?=.*杂质限度)(?=.*API\s*浓度)(?=.*限度浓度)",
        "columns": {
            "impurityName": r"^(?:杂质)?名称$", "field2": r"^(?:AI值|每日允许摄入量)",
            "field3": r"^最大日剂量", "field4": r"^杂质限度(?:\s*\([^)]*\))?$",
            "field5": r"^(?:供试品溶液中\s*)?API\s*浓度", "field6": r"^(?:杂质)?限度浓度",
        },
    },
    "validationSummary": {
        "sectionPattern": r"(?:实|试)验设计|验证(?:项目|内容)|(?:可)?接受标准",
        "headerPattern": r"(?=.*(?:验证|试验|检验)?项目|.*验证内容)(?=.*(?:可)?接受标准|.*接收标准|.*验收标准|.*判定标准)",
        "columns": {
            "field1": r"^(?:(?:验证|试验|检验)?项目|验证内容|项目名称)$",
            "acceptanceCriteria": r"^(?:可)?接受标准$|^接收标准$|^验收标准$|^判定标准$|^Acceptance\s*Criteria$",
        },
    },
    "methodParameters": {
        "sectionPattern": r"仪器方法|分析方法", "headerPattern": r"项目.*参数|分析方法",
        "columnIndexes": {"field1": 0, "field2": 1, "field3": 2},
    },
    "specificity": {
        "sectionPattern": r"实验结果.*原始数据与处理结果",
        "headerPattern": r"杂质名称.*溶液名称.*保留时间.*峰面积",
        "columns": {"impurityName": r"^杂质名称$", "solutionName": r"^溶液名称$",
                    "retentionTime": r"^保留时间", "peakArea": r"^峰面积"},
    },
    "jiancexian": {
        "sectionPattern": r"检测限与定量限|检测限", "headerPattern": r"杂质名称.*信噪比.*检测限",
        "columnIndexes": {"name": 0, "field2": 1, "field3": 2, "field4": 3,
                          "field5": 4, "field6": 5, "field7": 6},
        "excludeRowPattern": r"^结论(?:\||$)",
    },
    "loq": {
        "sectionPattern": r"检测限与定量限|定量限", "headerPattern": r"信噪比.*定量限.*峰面积",
        "columnIndexes": {"sequence": 0, "field2": 1, "peakArea": 2, "field4": 3,
                          "field5": 4, "field6": 5, "field7": 6},
        "excludeRowPattern": r"^结论(?:\||$)",
    },
    "linearityPreparation": {
        "sectionPattern": r"线性|溶液配制", "headerPattern": r"量取体积.*定容.*溶液.*名称",
        "columnIndexes": {"field1": 0, "field2": 1, "field3": 2, "field4": 3,
                          "field5": 4, "solutionName": -1},
    },
    "repeatability": {
        "sectionPattern": r"重复性", "headerPattern": r"No\.? .*保留时间.*峰面积|人员/日期.*峰面积",
        "columnIndexes": {"field1": 0, "sequence": 1, "field3": 2, "retentionTime": 3,
                          "peakArea": 4, "field6": 5, "field7": 6},
    },
    "intermediatePrecision": {
        "sectionPattern": r"中间精密度", "headerPattern": r"No\.? .*保留时间.*峰面积|人员/日期.*峰面积",
        "columnIndexes": {"field1": 0, "sequence": 1, "field3": 2, "retentionTime": 3,
                          "peakArea": 4, "field6": 5, "field7": 6},
    },
    "blankAmount": {
        "sectionPattern": r"空白", "headerPattern": r"杂质名称.*平均含量",
        "columnIndexes": {"impurityName": 0, "sequence": 1, "field3": 2, "peakArea": 3,
                          "field5": 4, "content": 5, "field7": 6},
    },
    "accuracy": {
        "sectionPattern": r"准确度", "headerPattern": r"回收率.*加入量|溶液.*回收率.*平均值",
        "columnIndexes": {"solutionName": 0, "sequence": 1, "field3": 2, "field4": 3,
                          "field5": 4, "field6": 5, "field7": 6, "field8": 7, "field9": 8},
    },
    "solutionStability": {
        "sectionPattern": r"稳定性", "headerPattern": r"时间.*(?:对照品溶液|100%加标)",
        "columnIndexes": {"timePoint": 0, "field2": 1, "field3": 2, "field4": 3, "field5": 4},
    },
    "robustnessSpecificity": {
        "sectionPattern": r"实验结果.*原始数据与处理结果", "headerPattern": r"溶液名称.*色谱柱1.*色谱柱2",
        "columns": {"solutionName": r"^溶液名称$", "field2": r"^色谱柱1$", "field3": r"^色谱柱2$"},
    },
    "robustnessSequence": {
        "sectionPattern": r"实验设计|实验结果", "headerPattern": r"溶液.*进样针数.*接受标准",
        "columns": {"field1": r"^溶液", "field2": r"^进样针数$", "acceptanceCriteria": r"^接受标准$"},
    },
    "robustnessResult": {
        "sectionPattern": r"实验结果", "headerPattern": r"溶液.*(?:结果|结论)",
        "columnIndexes": {"field1": 0, "field2": 1},
    },
}

PROFILE_COLLECTIONS = {
    "IMPURITY_LIMIT_TABLE": "impurity", "LIMIT_CALCULATION_TABLE": "limit",
    "VALIDATION_SUMMARY_TABLE": "validationSummary", "METHOD_PARAMETER_TABLE": "methodParameters",
    "SPECIFICITY_RESULT_TABLE": "specificity", "ROBUSTNESS_SPECIFICITY_TABLE": "robustnessSpecificity",
    "ROBUSTNESS_SEQUENCE_TABLE": "robustnessSequence", "SYSTEM_SUITABILITY_MATRIX": "systemSuitability",
}

# 方法参数的 field3 读取第 3 列，表头必须明确包含至少三列。
METHOD_PARAMETERS_HEADER_PATTERN = r"^(?=(?:[^|]*\|){2})(?=.*(?:项目.*参数|分析方法))"


def _system_suitability(json_key: str) -> dict[str, Any] | None:
    values = {
        "retentionTime": {}, "peakArea": {"valueColumnOffset": 1},
        "impurityName": {"valueRowIndex": 0}, "solutionName": {"valueRowIndex": 0},
        "injectionId": {"valueColumnIndex": 0},
        "sequence": {
            "valueColumnIndex": 0, "valueTemplate": "{header}-{value}",
            "headerValuePattern": r"^([^|]+)",
        },
    }
    if json_key not in values:
        return None
    return {
        "extractionType": "HTML_TABLE_COLUMN", "recordMode": "MATRIX", "headerRows": 2,
        "dataStartRow": 2, "dataStartColumn": 1, "columnStride": 2,
        "sectionPattern": r"(?:实|试)验结果.*系统适用性(?:结果)?",
        # 首列在不同 LIMS 模板中可能叫“名称”或“No.”。
        "headerPattern": r"(?:No\.?|名称).*保留时间.*峰面积", "excludeRowPattern": r"结论|RSD|平均|标准差|置信区间",
        **values[json_key],
    }


def direct_rule_config(collection: str, json_key: str) -> dict[str, Any] | None:
    if collection in INSTANCE_FIELDS and json_key in INSTANCE_FIELDS[collection]:
        return {"extractionType": "INSTANCE_PATH", "sourcePath": INSTANCE_FIELDS[collection][json_key]}
    raw = RAW_UNIT_FIELDS.get(collection)
    if raw and json_key in raw[1]:
        paths = raw[1][json_key]
        return {"extractionType": "RAW_UNIT_FIELD", "sourceUnitType": raw[0],
                "sourcePath": paths[0], "sourcePaths": paths}
    if collection in SOLUTION_TABLE_DEFAULTS and json_key in SOLUTION_TABLE_COLUMN_PATTERNS:
        return {
            "extractionType": "HTML_TABLE_COLUMN", "recordMode": "ROWS", "headerRows": 1,
            "sourcePath": SOLUTION_TABLE_COLUMN_PATTERNS[json_key],
            "sectionPattern": r"实验设计|溶液配制",
            "headerPattern": r"(?=.*(?:溶液名称|名称))(?=.*(?:配制方法|溶液配制))",
            "rowPattern": SOLUTION_TABLE_DEFAULTS[collection]["rowPattern"],
        }
    if collection == "systemSuitability":
        return _system_suitability(json_key)
    table = TABLES.get(collection)
    if table:
        config = {
            "extractionType": "HTML_TABLE_COLUMN", "recordMode": "ROWS", "headerRows": 1,
            "sectionPattern": table["sectionPattern"], "headerPattern": table["headerPattern"],
        }
        if collection == "methodParameters" and json_key == "field3":
            config["headerPattern"] = METHOD_PARAMETERS_HEADER_PATTERN
        if json_key in table.get("columns", {}):
            config["sourcePath"] = table["columns"][json_key]
        elif json_key in table.get("columnIndexes", {}):
            index = table["columnIndexes"][json_key]
            config["sourceColumnIndex"] = index
            config["sourcePath"] = ""
        else:
            return None
        if table.get("excludeRowPattern"):
            config["excludeRowPattern"] = table["excludeRowPattern"]
        return config
    if collection == "formulas" and json_key == "text":
        return {"extractionType": "RICH_TEXT_REGEX", "sectionPattern": r"计算公式"}
    if collection == "conclusions" and json_key == "text":
        return {"extractionType": "RICH_TEXT_REGEX", "sectionPattern": r"实验结论"}
    return None
