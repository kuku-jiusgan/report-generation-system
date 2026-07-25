import axios from "axios";

const http = axios.create({ baseURL: "/api/v1/admin", timeout: 120000 });

export interface AdminOverview {
  mappingCount: number;
  enabledMappings: number;
  tableCount: number;
  enabledTables: number;
  sourceCounts: Record<string, number>;
  pendingCount: number;
  aiRuleCount: number;
  publishedVersion?: number;
  template: { name: string; size: number; exists: boolean };
}

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
  headerRows: number;
  dataRowStart: number;
  dataRowEnd: number;
  footerRows: number;
  recordKey: string;
  mergeFields: string[];
  enabled: boolean;
  notes: string;
  updatedAt: string;
}

export interface DataSourceRule {
  id: number;
  code: string;
  name: string;
  sourceType: string;
  priority: number;
  enabled: boolean;
  config: Record<string, unknown>;
  updatedAt: string;
}

export interface StandardField {
  id: number;
  fieldCode: string;
  label: string;
  groupCode: string;
  collectionCode: string;
  dataType: string;
  cardinality: "ONE" | "MANY";
  dbTable: string;
  dbColumn: string;
  jsonKey: string;
  legacyJsonPath: string;
  description: string;
  outputFormat: string;
  defaultValue: string;
  validationRegex: string;
  orderNo: number;
  enabled: boolean;
  updatedAt: string;
}

export interface LimsExtractionRule {
  id: number;
  fieldCode: string;
  name: string;
  sourceType: "NORMALIZED_PATH" | "RAW_UNIT_FIELD" | "RICH_TEXT_REGEX" | "HTML_TABLE_COLUMN";
  sourceUnitType: string;
  sourcePath: string;
  sectionPattern: string;
  headerPattern: string;
  valuePattern: string;
  transform: string;
  priority: number;
  config: Record<string, unknown>;
  enabled: boolean;
  updatedAt: string;
}

export interface AiRule {
  id?: number;
  fieldCode: string;
  name: string;
  inputFields: string[];
  promptTemplate: string;
  outputType: string;
  maxLength: number;
  requireCitations: boolean;
  requiresApproval: boolean;
  provider: string;
  model: string;
  enabled: boolean;
  updatedAt?: string;
}

export interface ValidationIssue {
  locationId?: string;
  fieldCode?: string;
  code: string;
  message: string;
}
export interface ValidationReport {
  valid: boolean;
  success: Array<Record<string, unknown>>;
  warnings: ValidationIssue[];
  errors: ValidationIssue[];
  statistics: {
    mapped: number;
    warnings: number;
    errors: number;
    compiled: Record<string, number>;
    original: Record<string, number>;
  };
  previewTemplate?: string;
}

export interface RuleVersion {
  id: number | string;
  versionNo: number;
  status: string;
  note: string;
  validationReport: Partial<ValidationReport>;
  compiledTemplate?: string;
  createdAt: string;
  publishedAt?: string;
}

export interface AdminTemplate {
  id: string;
  code: string;
  name: string;
  description: string;
  status: "ACTIVE" | "ARCHIVED";
  versionCount: number;
  latestVersion?: number;
  publishedVersion?: number;
  createdAt: string;
  updatedAt: string;
  active: boolean;
}

export interface AdminTemplateVersion {
  id: string;
  templateId: string;
  versionNo: number;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  note: string;
  templateFile?: string;
  validationReport: Partial<ValidationReport>;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
}

export type ContentBlockKind =
  | "FIXED"
  | "MAPPED_FIELD"
  | "REPEATING_TABLE"
  | "MATRIX"
  | "CALCULATED"
  | "AI_NARRATIVE";
export interface DesignerBlock {
  id: number;
  chapterId: number;
  title: string;
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
  status: "READY" | "PENDING" | "DISABLED";
  mappings: MappingRule[];
  tableRule?: TableRule;
}
export interface DesignerChapter {
  id: number;
  parentId?: number;
  code: string;
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

export interface OnlyOfficeBootstrap {
  documentServerUrl: string;
  config: Record<string, unknown> & {
    events?: Record<string, (...args: unknown[]) => void>;
  };
}

export interface LimsInstanceSummary {
  instanceId: string;
  projectId?: string;
  title: string;
  version: number;
  createdBy?: string;
  createdTime?: string;
  rowCount: number;
  unitCounts: Record<string, number>;
  structuredDataCounts: Record<string, number>;
  richTextCount: number;
  richTextCharacters: number;
}

export interface LimsImport {
  id: string;
  fileName: string;
  size: number;
  summary: {
    rowCount: number;
    instanceCount: number;
    projects: string[];
    instances: LimsInstanceSummary[];
  };
  createdAt: string;
}

export interface LimsRecognitionTest {
  recognizedCounts: Record<string, number>;
  recognizedTotal: number;
  duplicateCount: number;
  conflicts: Array<Record<string, unknown>>;
  unmatched: Array<Record<string, unknown>>;
  coverage: { recognizedTables: number; unmatchedTables: number };
}

const limsHttp = axios.create({ baseURL: "/api/v1/lims", timeout: 120000 });

export const adminApi = {
  templates: async () => (await http.get<AdminTemplate[]>("/templates")).data,
  createTemplate: async (data: {
    code: string;
    name: string;
    description?: string;
    note?: string;
  }) => (await http.post<AdminTemplate>("/templates", data)).data,
  updateTemplate: async (id: string, data: Partial<AdminTemplate>) =>
    (await http.put<AdminTemplate>(`/templates/${id}`, data)).data,
  deleteTemplate: async (id: string) =>
    (await http.delete(`/templates/${id}`)).data,
  templateVersions: async (templateId: string) =>
    (
      await http.get<AdminTemplateVersion[]>(
        `/templates/${templateId}/versions`,
      )
    ).data,
  createTemplateVersion: async (
    templateId: string,
    data: { baseVersionId?: string; note?: string },
  ) =>
    (
      await http.post<AdminTemplateVersion>(
        `/templates/${templateId}/versions`,
        data,
      )
    ).data,
  activateTemplateVersion: async (templateId: string, versionId: string) =>
    (await http.post(`/templates/${templateId}/versions/${versionId}/activate`))
      .data,
  overview: async () => (await http.get<AdminOverview>("/overview")).data,
  designer: async () => (await http.get<TemplateDesigner>("/designer")).data,
  chapters: async () => (await http.get<DesignerChapter[]>("/chapters")).data,
  createChapter: async (data: Partial<DesignerChapter>) =>
    (await http.post<DesignerChapter>("/chapters", data)).data,
  updateChapter: async (id: number, data: Partial<DesignerChapter>) =>
    (await http.put<DesignerChapter>(`/chapters/${id}`, data)).data,
  deleteChapter: async (id: number) =>
    (await http.delete(`/chapters/${id}`)).data,
  contentBlocks: async () =>
    (await http.get<DesignerBlock[]>("/content-blocks")).data,
  createContentBlock: async (data: Partial<DesignerBlock>) =>
    (await http.post<DesignerBlock>("/content-blocks", data)).data,
  updateContentBlock: async (id: number, data: Partial<DesignerBlock>) =>
    (await http.put<DesignerBlock>(`/content-blocks/${id}`, data)).data,
  deleteContentBlock: async (id: number, deleteMappings = true) =>
    (
      await http.delete(`/content-blocks/${id}`, {
        params: { delete_mappings: deleteMappings },
      })
    ).data,
  reorderContentBlocks: async (chapterId: number, blockIds: number[]) =>
    (
      await http.post(`/chapters/${chapterId}/content-blocks/reorder`, {
        blockIds,
      })
    ).data,
  reorderBlockMappings: async (blockId: number, mappingIds: number[]) =>
    (
      await http.post(`/content-blocks/${blockId}/mappings/reorder`, {
        mappingIds,
      })
    ).data,
  onlyOfficeConfig: async () =>
    (await http.get<OnlyOfficeBootstrap>("/onlyoffice/config")).data,
  sendWordCommand: async (data: Record<string, unknown>) =>
    (await http.post<{ accepted: boolean; nonce: number }>("/onlyoffice/command", data)).data,
  mappings: async (params: Record<string, string> = {}) =>
    (await http.get<MappingRule[]>("/mappings", { params })).data,
  standardFields: async () =>
    (await http.get<StandardField[]>("/standard-fields")).data,
  allStandardFields: async () =>
    (await http.get<StandardField[]>("/standard-fields", { params: { include_disabled: true } })).data,
  createStandardField: async (data: Partial<StandardField>) =>
    (await http.post<StandardField>("/standard-fields", data)).data,
  updateStandardField: async (fieldCode: string, data: Partial<StandardField>) =>
    (await http.put<StandardField>(`/standard-fields/${encodeURIComponent(fieldCode)}`, data)).data,
  deleteStandardField: async (fieldCode: string) =>
    (await http.delete(`/standard-fields/${encodeURIComponent(fieldCode)}`)).data,
  extractionRules: async (fieldCode: string) =>
    (await http.get<LimsExtractionRule[]>(`/standard-fields/${encodeURIComponent(fieldCode)}/extraction-rules`)).data,
  createExtractionRule: async (fieldCode: string, data: Partial<LimsExtractionRule>) =>
    (await http.post<LimsExtractionRule>(`/standard-fields/${encodeURIComponent(fieldCode)}/extraction-rules`, data)).data,
  updateExtractionRule: async (id: number, data: Partial<LimsExtractionRule>) =>
    (await http.put<LimsExtractionRule>(`/extraction-rules/${id}`, data)).data,
  deleteExtractionRule: async (id: number) =>
    (await http.delete(`/extraction-rules/${id}`)).data,
  createMapping: async (data: Partial<MappingRule>) =>
    (await http.post<MappingRule>("/mappings", data)).data,
  updateMapping: async (id: number, data: Partial<MappingRule>) =>
    (await http.put<MappingRule>(`/mappings/${id}`, data)).data,
  deleteMapping: async (id: number) =>
    (await http.delete(`/mappings/${id}`)).data,
  tables: async () => (await http.get<TableRule[]>("/table-rules")).data,
  updateTable: async (tableNo: string, data: Partial<TableRule>) =>
    (await http.put<TableRule>(`/table-rules/${tableNo}`, data)).data,
  sources: async () => (await http.get<DataSourceRule[]>("/data-sources")).data,
  updateSource: async (code: string, data: Partial<DataSourceRule>) =>
    (await http.put<DataSourceRule>(`/data-sources/${code}`, data)).data,
  aiRules: async () => (await http.get<AiRule[]>("/ai-rules")).data,
  saveAiRule: async (data: AiRule) =>
    data.id
      ? (
          await http.put<AiRule>(
            `/ai-rules/${encodeURIComponent(data.fieldCode)}`,
            data,
          )
        ).data
      : (await http.post<AiRule>("/ai-rules", data)).data,
  deleteAiRule: async (id: number) =>
    (await http.delete(`/ai-rules/${id}`)).data,
  testAiRule: async (
    data: AiRule & { sampleInputs: Record<string, unknown> },
  ) => (await http.post("/ai-rules/test", data)).data,
  validate: async () => (await http.post<ValidationReport>("/validate")).data,
  publish: async (note: string) =>
    (await http.post<RuleVersion>("/publish", { note })).data,
  versions: async () => (await http.get<RuleVersion[]>("/versions")).data,
  limsImports: async () => (await limsHttp.get<LimsImport[]>("/imports")).data,
  uploadLimsImport: async (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return (await limsHttp.post<LimsImport>("/imports", data)).data;
  },
  limsInstance: async (importId: string, instanceId: string) =>
    (
      await limsHttp.get<Record<string, unknown>>(
        `/imports/${importId}/instances/${instanceId}`,
      )
    ).data,
  limsRecognition: async (importId: string, instanceIds: string[]) =>
    (
      await http.post<LimsRecognitionTest>("/lims-recognition-test", {
        importId,
        instanceIds,
      })
    ).data,
};
