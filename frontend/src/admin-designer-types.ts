/** 模板设计器的数据结构定义。
 *
 * 这些类型描述“设计器里能看到什么”，与后端 admin_table_rules / admin_mapping_rules
 * 一一对应；从 admin-api.ts 拆出来，是为了让接口文件保持在仓库的 600 行上限内。
 */

export interface MappingRule {
  id: number;
  locationId: string;
  sectionCode: string;
  tableNo: string;
  wordLabel: string;
  fieldCode: string;
  dataType: string;
  sourceType: string;
  sourcePath: string;
  standardFieldCode?: string;
  repeatType: string;
  repeatKey: string;
  mergeRule: string;
  fillRule: string;
  calculationRule: string;
  calculationExpression: string;
  calculationDependencies: string[];
  calculationScope: "REPORT" | "BLOCK" | "CURRENT_ROW";
  calculationPrecision: number;
  calculationNullBehavior: "ERROR" | "ZERO" | "SKIP";
  controlTag: string;
  /** 写回报告固定字段的编码（如 report_no）；空表示该控件不写回报告字段 */
  reportBindingCode: string;
  required: boolean;
  sourcePending: boolean;
  enabled: boolean;
  updatedAt: string;
  chapterId?: number;
  blockId?: number;
}

export interface TableRule {
  tableNo: string;
  sectionCode: string;
  mode: string;
  /** TABLE_REPEAT 时按该字段将数据分组后复制整张原型表 */
  groupKey?: string;
  /** TABLE_REPEAT 时复制表内采用 ROW_REPEAT 或 MATRIX */
  innerMode?: "ROW_REPEAT" | "MATRIX";
  headerRows: number;
  dataRowStart: number;
  dataRowEnd: number;
  footerRows: number;
  recordKey: string;
  mergeFields: string[];
  /** Word 正文里的第几张表格；0 表示未配置，编译时会跳过该表并给出警告 */
  physicalTableIndex: number;
  /** 重建数据行时保留的汇总行标签，例如 RSD、结论 */
  preservedRowLabels: string[];
  /** 生成时清除该表内的图片与嵌入对象 */
  clearEmbeddedObjects: boolean;
  /** 矩阵表版式（JSON 文本）：rowFields / rowLabels / scalarCells */
  matrixLayout: string;
  enabled: boolean;
  notes: string;
  updatedAt: string;
}


export type ContentBlockKind =
  | "FIXED"
  | "MAPPED_FIELD"
  | "REPEATING_TABLE"
  | "MATRIX"
  | "TABLE_REPEAT"
  | "CALCULATED"
  | "AI_NARRATIVE";
export interface DesignerBlock {
  id: number;
  chapterId: number;
  title: string;
  standardGroupCode?: string;
  standardFields?: Array<{ fieldCode: string; label: string; enabled: boolean }>;
  kind: ContentBlockKind;
  tableNo: string;
  sourcePath: string;
  repeatKey: string;
  prototypeLocation: string;
  dedupKey: string;
  sortRule: string;
  emptyBehavior: string;
  mergeRule: string;
  orderNo: number;
  enabled: boolean;
  mappingIds: number[];
  controlTags: string[];
  sources: string[];
  status: "READY" | "PENDING" | "DISABLED" | "UNCONFIGURED";
  mappings: MappingRule[];
  tableRule?: TableRule;
}
export interface DesignerChapter {
  id: number;
  parentId?: number;
  code: string;
  standardGroups?: Array<{ groupCode: string; label: string; fields: Array<{ fieldCode: string; label: string; enabled: boolean }> }>;
  title: string;
  pageHint?: number;
  orderNo: number;
  enabled: boolean;
  blocks: DesignerBlock[];
  children: DesignerChapter[];
}
export interface TemplateDesigner {
  template: {
    id: string;
    name: string;
    draftFile: string;
    templateId?: string;
    templateName?: string;
    versionId?: string;
    versionNo?: number;
    publishedVersion?: number;
    status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  };
  chapters: DesignerChapter[];
  summary: {
    chapters: number;
    blocks: number;
    mappings: number;
    pending: number;
  };
}
