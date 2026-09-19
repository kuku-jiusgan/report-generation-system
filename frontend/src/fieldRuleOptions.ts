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
export const transforms = [
  { value: "TRIM", label: "去除首尾空白" }, { value: "NUMBER", label: "转换为数值" },
  { value: "DATE", label: "转换为日期" }, { value: "UPPER", label: "转为大写" },
  { value: "LOWER", label: "转为小写" },
];
