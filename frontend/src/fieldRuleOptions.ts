export const sourceTypes = [
  { value: "LIMS", label: "LIMS 数据" },
  { value: "AI", label: "AI 生成" },
  { value: "EXCEL", label: "EXCEL 导入" },
  { value: "PROTOCOL", label: "方案提取" },
  { value: "PDF", label: "PDF 读取" },
  { value: "CALCULATED", label: "计算" },
];

export const sourceTypeLabel = (value: string) =>
  sourceTypes.find((item) => item.value === value)?.label || `未知提取方式（${value}）`;
export const limsExtractionTypes = [
  { value: "NORMALIZED_PATH", label: "标准 JSONPath" },
  { value: "RAW_UNIT_FIELD", label: "原始 UNITBODY 字段" },
  { value: "RICH_TEXT_REGEX", label: "富文本正文" },
  { value: "HTML_TABLE_COLUMN", label: "HTML 表格列" },
];
export const transforms = [
  { value: "TRIM", label: "去除首尾空白" }, { value: "NUMBER", label: "转换为数值" },
  { value: "DATE", label: "转换为日期" }, { value: "UPPER", label: "转为大写" },
  { value: "LOWER", label: "转为小写" },
];
export const parsers = [
  { value: "NORMALIZED_JSON", label: "标准 JSON 路径读取" },
  { value: "INSTANCE_FIELD", label: "实验实例字段读取" },
  { value: "STRUCTURED_UNIT", label: "结构化 UNITBODY 解析" },
  { value: "HTML_TABLE_GRID", label: "HTML 表格结构解析" },
];
export const parserProfiles = [
  "SYSTEM_SUITABILITY_MATRIX", "SPECIFICITY_RESULT_TABLE", "SOLUTION_PREPARATION_TABLE",
  "IMPURITY_LIMIT_TABLE", "METHOD_PARAMETER_TABLE", "ROBUSTNESS_SPECIFICITY_TABLE",
  "ROBUSTNESS_SEQUENCE_TABLE",
  "VALIDATION_SUMMARY_TABLE",
  "LIMIT_CALCULATION_TABLE",
];
export const unitTypes = ["Sample", "Standard", "Equipment", "Chromatogram", "Reagent", "Weighing"];
