<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowDown, ArrowUp, Coin, Delete, EditPen, Plus, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  adminApi,
  type LimsExtractionRule,
  type StandardField,
  type MappingRule,
  type StandardFieldCatalogChapter,
  type SystemFieldRule,
  type SystemFieldGroup,
} from "./admin-api";
import SystemAiRuleEditor from "./SystemAiRuleEditor.vue";
import SystemFieldTree from "./SystemFieldTree.vue";
import SystemFieldCatalogTree from "./SystemFieldCatalogTree.vue";
import ExcelWorkbookLocation from "./ExcelWorkbookLocation.vue";
import ExcelFieldRuleEditor from "./ExcelFieldRuleEditor.vue";
import FieldOutputFormatSelect from "./FieldOutputFormatSelect.vue";
import { workbookLocation } from "./excelWorkbookLocation";
type CatalogRule = Omit<LimsExtractionRule, "sourceType"> & SystemFieldRule;
const loading = ref(false);
const saving = ref(false);
const fields = ref<StandardField[]>([]);
const chapters = ref<StandardFieldCatalogChapter[]>([]);
const groups = ref<SystemFieldGroup[]>([]);
const catalogUnmappedFields = ref<StandardField[]>([]);
const expandedChapters = ref<Set<number>>(new Set());
const selected = ref<StandardField>();
const selectedChapterId = ref<number>();
const selectedGroupCode = ref("");
const selectedGroup = computed(() => groups.value.find((group) => group.groupCode === selectedGroupCode.value));
const groupDraft = ref<Partial<SystemFieldGroup>>({});
const selectedChapter = ref<StandardFieldCatalogChapter>();
const draft = ref<Partial<StandardField>>();
const rules = ref<CatalogRule[]>([]);
const references = ref<MappingRule[]>([]);
const search = ref("");
const ruleDialog = ref(false);
const ruleDraft = ref<Partial<CatalogRule>>();
const ruleConfig = ref<Record<string, unknown>>({});
const dataTypes = [
  { value: "string", label: "文本" }, { value: "decimal", label: "数值" },
  { value: "date", label: "日期" }, { value: "richText", label: "富文本" },
  { value: "boolean", label: "布尔值" }, { value: "image", label: "图片" },
];
const sourceTypes = [
  { value: "LIMS", label: "LIMS 数据" },
  { value: "AI", label: "AI 生成" },
  { value: "EXCEL", label: "EXCEL 导入" },
  { value: "PDF", label: "PDF 读取" },
  { value: "CALCULATED", label: "计算" },
];
const limsExtractionTypes = [
  { value: "NORMALIZED_PATH", label: "标准 JSONPath" },
  { value: "RAW_UNIT_FIELD", label: "原始 UNITBODY 字段" },
  { value: "RICH_TEXT_REGEX", label: "富文本正文" },
  { value: "HTML_TABLE_COLUMN", label: "HTML 表格列" },
];
const transforms = [
  { value: "TRIM", label: "去除首尾空白" }, { value: "NUMBER", label: "转换为数值" },
  { value: "DATE", label: "转换为日期" }, { value: "UPPER", label: "转为大写" },
  { value: "LOWER", label: "转为小写" },
];
const groupDisplay = (field?: Partial<StandardField>) => {
  const labels = field?.groupLabels || [];
  return labels.length ? labels.join(" / ") : field?.groupLabel || field?.groupCode || "";
};
const parsers = [
  { value: "NORMALIZED_JSON", label: "标准 JSON 路径读取" },
  { value: "INSTANCE_FIELD", label: "实验实例字段读取" },
  { value: "STRUCTURED_UNIT", label: "结构化 UNITBODY 解析" },
  { value: "HTML_TABLE_GRID", label: "HTML 表格结构解析" },
];
const parserProfiles = [
  "SYSTEM_SUITABILITY_MATRIX", "SPECIFICITY_RESULT_TABLE", "SOLUTION_PREPARATION_TABLE",
  "IMPURITY_LIMIT_TABLE", "METHOD_PARAMETER_TABLE", "ROBUSTNESS_SPECIFICITY_TABLE",
  "ROBUSTNESS_SEQUENCE_TABLE",
  "VALIDATION_SUMMARY_TABLE",
  "LIMIT_CALCULATION_TABLE",
];
const unitTypes = ["Sample", "Standard", "Equipment", "Chromatogram", "Reagent", "Weighing"];
const sourceTypeLabel = (value: string) => sourceTypes.find((item) => item.value === value)?.label || value;
const parserLabel = (rule: CatalogRule) => {
  const parser = String(rule.config?.parser || "");
  return parsers.find((item) => item.value === parser)?.label || sourceTypeLabel(rule.sourceType);
};
function ruleOrigin(rule: Partial<CatalogRule>) {
  const parser = String(rule.config?.parser || "");
  if (rule.sourceType !== "LIMS") return sourceTypeLabel(String(rule.sourceType));
  if (parser === "HTML_TABLE_GRID") return "LIMS SQL：UNITBODY（TYPE=RichText）内的 HTML 表格";
  if (parser === "STRUCTURED_UNIT") return "LIMS SQL：结构化 UNITBODY";
  if (parser === "INSTANCE_FIELD") return `LIMS 实验实例字段：${String(rule.config?.inputField || "")}`;
  const extractionType = String(rule.config?.extractionType || "NORMALIZED_PATH");
  if (extractionType === "NORMALIZED_PATH") return "LIMS 数据：标准化中间 JSON";
  if (extractionType === "RAW_UNIT_FIELD") return `LIMS 数据：UNITBODY → data[]${rule.sourceUnitType ? `（TYPE=${rule.sourceUnitType}）` : ""}`;
  if (extractionType === "RICH_TEXT_REGEX") return "LIMS 数据：UNITBODY 富文本";
  if (extractionType === "HTML_TABLE_COLUMN") return "LIMS 数据：UNITBODY HTML 表格";
  return "未指定来源";
}
function transformLabel(value: string) {
  return transforms.find((item) => item.value === value)?.label || value || "不转换";
}
function ruleMethodNote(rule: CatalogRule) {
  const parser = String(rule.config?.parser || "");
  const extractionType = String(rule.config?.extractionType || "NORMALIZED_PATH");
  if (parser === "HTML_TABLE_GRID") return `按章节和表头正则定位表格，使用 ${String(rule.config?.parserProfile || "未指定配置")} 解析行列后写入标准 JSON`;
  if (parser === "STRUCTURED_UNIT") return `按 ${String(rule.config?.parserProfile || rule.sourceUnitType || "UNIT 类型")} 识别结构化单元，再读取目标属性`;
  if (extractionType === "NORMALIZED_PATH") return rule.valuePattern ? "JSONPath 读取后再用正则捕获" : "按 JSONPath 直接读取";
  if (extractionType === "RAW_UNIT_FIELD") return rule.valuePattern ? "按字段路径读取后再用正则捕获" : "按原始 JSON 字段路径直接读取";
  if (extractionType === "RICH_TEXT_REGEX") return "先用章节正则筛选正文，再用取值正则捕获";
  if (extractionType === "HTML_TABLE_COLUMN") return "依次用章节、表头和列标题正则定位，再读取单元格";
  return "";
}
interface FieldChapterNode {
  id: number;
  code: string;
  title: string;
  enabled: boolean;
  fields: StandardField[];
  children: FieldChapterNode[];
  fieldCount: number;
}
function buildChapterNode(chapter: StandardFieldCatalogChapter, keyword: string): FieldChapterNode | undefined {
  const chapterMatches = !keyword || `${chapter.code} ${chapter.title}`.toLowerCase().includes(keyword);
  const directFields = chapter.fields
    .filter((item) => chapterMatches || `${item.label} ${item.fieldCode} ${item.groupCode}`.toLowerCase().includes(keyword))
    .sort((a, b) => a.orderNo - b.orderNo || a.id - b.id);
  const children = chapter.children
    .map((item) => buildChapterNode(item, keyword))
    .filter((item): item is FieldChapterNode => Boolean(item));
  if (keyword && !chapterMatches && !directFields.length && !children.length) return undefined;

  const subtreeCodes = new Set(directFields.map((item) => item.fieldCode));
  for (const child of children) {
    collectNodeFieldCodes(child, subtreeCodes);
  }
  return {
    id: chapter.id,
    code: chapter.code,
    title: chapter.title,
    enabled: chapter.enabled,
    fields: directFields,
    children,
    fieldCount: subtreeCodes.size,
  };
}
function collectNodeFieldCodes(node: FieldChapterNode, result: Set<string>) {
  node.fields.forEach((item) => result.add(item.fieldCode));
  node.children.forEach((item) => collectNodeFieldCodes(item, result));
}
const chapterTree = computed(() => {
  const keyword = search.value.trim().toLowerCase();
  return chapters.value
    .map((item) => buildChapterNode(item, keyword))
    .filter((item): item is FieldChapterNode => Boolean(item));
});
const directoryOrderedGroups = computed(() => {
  const ordered: SystemFieldGroup[] = [];
  const added = new Set<string>();
  const appendChapterGroups = (items: StandardFieldCatalogChapter[]) => {
    [...items].sort((a, b) => a.orderNo - b.orderNo || a.id - b.id).forEach((chapter) => {
      groups.value.forEach((group) => {
        if (group.chapterIds.includes(chapter.id) && !added.has(group.groupCode)) {
          ordered.push(group);
          added.add(group.groupCode);
        }
      });
      appendChapterGroups(chapter.children);
    });
  };
  appendChapterGroups(chapters.value);
  groups.value.forEach((group) => {
    if (!added.has(group.groupCode)) ordered.push(group);
  });
  return ordered;
});

const visibleChapterRows = computed(() => {
  const rows: Array<{ node: FieldChapterNode; depth: number; open: boolean }> = [];
  const searching = Boolean(search.value.trim());
  function visit(items: FieldChapterNode[], depth: number) {
    for (const node of items) {
      const open = searching || expandedChapters.value.has(node.id);
      rows.push({ node, depth, open });
      if (open) visit(node.children, depth + 1);
    }
  }
  visit(chapterTree.value, 0);
  return rows;
});

const unmappedFields = computed(() => {
  const keyword = search.value.trim().toLowerCase();
  return catalogUnmappedFields.value.filter((item) =>
    !keyword || `${item.label} ${item.fieldCode} ${item.groupCode}`.toLowerCase().includes(keyword),
  );
});

function toggleChapter(id: number) {
  const next = new Set(expandedChapters.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedChapters.value = next;
}
function selectGroup(group: SystemFieldGroup) { selectedGroupCode.value = group.groupCode; groupDraft.value = JSON.parse(JSON.stringify(group)); selected.value = undefined; draft.value = undefined }
function selectChapter(chapter: StandardFieldCatalogChapter) { selectedGroupCode.value = ''; selectedChapter.value = chapter; selected.value = undefined; draft.value = undefined }
async function saveSelectedGroup() {
  if (!selectedGroup.value || !groupDraft.value.label) return
  try { await adminApi.updateFieldGroup(selectedGroup.value.groupCode, groupDraft.value); await loadFields(); ElMessage.success('编组已保存') }
  catch (error) { ElMessage.error(errorText(error)) }
}
async function moveGroupField(index: number, delta: number) {
  if (!selectedGroup.value) return
  const next = index + delta
  if (next < 0 || next >= selectedGroup.value.fields.length) return
  const codes = selectedGroup.value.fields.map(field => field.fieldCode)
  ;[codes[index], codes[next]] = [codes[next], codes[index]]
  try {
    await adminApi.reorderFieldGroup(selectedGroup.value.groupCode, codes)
    const group = groups.value.find(item => item.groupCode === selectedGroup.value?.groupCode)
    if (group) {
      const fieldsByCode = new Map(group.fields.map(field => [field.fieldCode, field]))
      group.fields = codes.map(fieldCode => fieldsByCode.get(fieldCode)!).filter(Boolean)
    }
    ElMessage.success('字段顺序已保存')
  }
  catch (error) { ElMessage.error(errorText(error)) }
}
async function removeSelectedGroup() {
  if (!selectedGroup.value) return
  try {
    await ElMessageBox.confirm(`删除编组“${selectedGroup.value.label}”？字段本身不会被删除。`, '删除编组', { type: 'warning' })
    await adminApi.deleteFieldGroup(selectedGroup.value.groupCode)
    selectedGroupCode.value = ''
    groupDraft.value = {}
    await loadFields()
    ElMessage.success('编组已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorText(error))
  }
}
async function saveSelectedChapter() {
  if (!selectedChapter.value) return
  try { await adminApi.updateChapter(selectedChapter.value.id, { code: selectedChapter.value.code, title: selectedChapter.value.title }); await loadFields(); ElMessage.success('章节已保存') }
  catch (error) { ElMessage.error(errorText(error)) }
}
async function removeSelectedChapter() {
  if (!selectedChapter.value) return
  try {
    await ElMessageBox.confirm(`删除章节“${selectedChapter.value.title}”？章节下的编组和字段不会被删除。`, '删除章节', { type: 'warning' })
    await adminApi.deleteChapter(selectedChapter.value.id)
    selectedChapter.value = undefined
    await loadFields()
    ElMessage.success('章节已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorText(error))
  }
}
async function createGroupInChapter() {
  if (!selectedChapter.value) return
  try {
    const result = await ElMessageBox.prompt('请输入编组名称', '新增编组', { confirmButtonText: '创建', cancelButtonText: '取消', inputPlaceholder: '例如：定量限结果' })
    if (!result.value.trim()) return ElMessage.warning('编组名称不能为空')
    const code = `custom_${Date.now()}`
    await adminApi.createFieldGroup({ groupCode: code, label: result.value.trim(), cardinality: 'MANY' })
    await adminApi.assignGroupChapter(code, selectedChapter.value.id)
    await loadFields()
    selectedGroupCode.value = code
    ElMessage.success('编组已创建')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorText(error))
  }
}
function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } }; message?: string };
  return value.response?.data?.detail || value.message || "操作失败";
}
async function loadFields(preferred?: string) {
  loading.value = true;
  try {
    const catalog = await adminApi.standardFieldCatalog();
    fields.value = catalog.fields;
    chapters.value = catalog.chapters;
    groups.value = catalog.groups || [];
    catalogUnmappedFields.value = catalog.unmappedFields;
    const target = fields.value.find((item) => item.fieldCode === (preferred || selected.value?.fieldCode)) || fields.value[0];
    if (target) await selectField(target);
  } catch (error) { ElMessage.error(errorText(error)); }
  finally { loading.value = false; }
}
async function selectField(field: StandardField, chapterId?: number) {
  selectedGroupCode.value = '';
  selectedChapter.value = undefined;
  if (chapterId) selectedChapterId.value = chapterId;
  selected.value = field;
  draft.value = JSON.parse(JSON.stringify(field));
  await Promise.all([loadRules(field.fieldCode), loadReferences(field.fieldCode)]);
}
async function loadRules(fieldCode: string) {
  try { rules.value = (await adminApi.systemFieldRules(fieldCode)).map((rule) => ({ ...rule.config, ...rule })) as CatalogRule[]; }
  catch (error) { ElMessage.error(errorText(error)); }
}
async function loadReferences(fieldCode: string) {
  try { references.value = await adminApi.standardFieldReferences(fieldCode) }
  catch (error) { references.value = []; ElMessage.error(errorText(error)) }
}
async function newField(groupCode = selectedGroupCode.value) {
  try {
    const result = await ElMessageBox.prompt("请输入字段名称", "新增系统字段", {
      confirmButtonText: "创建", cancelButtonText: "取消", inputPlaceholder: "例如：报告摘要",
      inputValidator: (value) => Boolean(value.trim()) || "字段名称不能为空",
    });
    // 新字段先进入未映射区，章节和编组由用户在目录管理中明确关联。
    const saved = await adminApi.createStandardField({ label: result.value.trim(), groupCode });
    await loadFields(saved.fieldCode);
    ElMessage.success(`系统字段已创建，编码：${saved.fieldCode}`);
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(errorText(error));
  }
}
async function saveField() {
  if (!draft.value?.fieldCode?.trim() || !draft.value.label?.trim()) return ElMessage.warning("字段编码和名称不能为空");
  saving.value = true;
  try {
    const payload = { ...draft.value, enabled: true };
    const saved = selected.value
      ? await adminApi.updateStandardField(selected.value.fieldCode, payload)
      : await adminApi.createStandardField(payload);
    await loadFields(saved.fieldCode);
    ElMessage.success(selected.value ? "标准字段已保存" : "标准字段已创建");
  } catch (error) { ElMessage.error(errorText(error)); }
  finally { saving.value = false; }
}
async function removeField() {
  if (!selected.value) return;
  try {
    await ElMessageBox.confirm(`删除标准字段“${selected.value.label}”？该字段的提取规则也会删除。`, "删除标准字段", { type: "warning" });
    await adminApi.deleteStandardField(selected.value.fieldCode);
    selected.value = undefined; draft.value = undefined; rules.value = [];
    await loadFields();
    ElMessage.success("标准字段已删除");
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(errorText(error)); }
}
function editRule(rule?: CatalogRule) {
  if (!draft.value?.fieldCode) return ElMessage.warning("请先保存标准字段，再配置提取规则");
  const nextRule: Partial<CatalogRule> = rule ? JSON.parse(JSON.stringify(rule)) : (rules.value[0] ? JSON.parse(JSON.stringify(rules.value[0])) : {
    fieldCode: draft.value.fieldCode, name: "新来源规则", sourceType: "LIMS",
    sourceUnitType: "", sourcePath: draft.value.legacyJsonPath || "", sectionPattern: "",
    headerPattern: "", valuePattern: "", transform: "TRIM", priority: (rules.value.length + 1) * 10,
    config: { parser: "NORMALIZED_JSON", extractionType: "NORMALIZED_PATH" }, enabled: true,
  });
  const legacyType = String(nextRule.sourceType || "LIMS");
  if (limsExtractionTypes.some((item) => item.value === legacyType)) {
    nextRule.sourceType = "LIMS";
    nextRule.config = { ...(nextRule.config || {}), extractionType: legacyType };
  }
  ruleDraft.value = nextRule;
  ruleConfig.value = JSON.parse(JSON.stringify(nextRule.config || {}));
  ruleDialog.value = true;
}
async function saveRule() {
  if (!ruleDraft.value?.name?.trim() || !selected.value) return ElMessage.warning("规则名称不能为空");
  try {
    const savedConfig = JSON.parse(JSON.stringify(ruleConfig.value));
    (savedConfig.contextVariables || []).forEach((item: Record<string, unknown>) => delete item.previewValue);
    ruleDraft.value.config = ruleDraft.value.sourceType === "LIMS" ? { ...savedConfig,
      sourceUnitType: ruleDraft.value.sourceUnitType, sourcePath: ruleDraft.value.sourcePath,
      sectionPattern: ruleDraft.value.sectionPattern, headerPattern: ruleDraft.value.headerPattern,
      valuePattern: ruleDraft.value.valuePattern } : savedConfig;
    delete ruleDraft.value.priority;
    if (ruleDraft.value.id) await adminApi.updateSystemFieldRule(ruleDraft.value.id, ruleDraft.value);
    else await adminApi.createSystemFieldRule(selected.value.fieldCode, ruleDraft.value);
    await loadRules(selected.value.fieldCode);
    ruleDialog.value = false;
    ElMessage.success("提取规则已保存");
  } catch (error) { ElMessage.error(errorText(error)); }
}
async function removeRule(rule: CatalogRule) {
  try {
    await ElMessageBox.confirm(`删除提取规则“${rule.name}”？`, "删除规则", { type: "warning" });
    await adminApi.deleteSystemFieldRule(rule.id);
    rules.value = rules.value.filter((item) => item.id !== rule.id);
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(errorText(error)); }
}
onMounted(() => loadFields());
</script>

<template>
  <div class="lims-catalog">
    <header class="module-header">
      <div class="module-title"><Coin /><div><strong>系统标准字段</strong><small>字段目录与统一来源规则</small></div></div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadFields()">刷新</el-button>
        <el-button type="primary" :icon="Plus" :disabled="!selectedGroupCode" @click="newField()">在当前编组新增字段</el-button>
      </div>
    </header>
    <main class="catalog-main">
      <aside class="field-index">
        <div class="index-head"><h1>标准字段目录</h1><span>{{ fields.length }} 个字段</span></div>
        <el-input v-model="search" :prefix-icon="Search" placeholder="搜索字段名称或编码" clearable />
        <SystemFieldCatalogTree :chapters="chapterTree" :groups="directoryOrderedGroups" :fields="fields" :selected-code="selected?.fieldCode" @select="selectField" @group="selectGroup" @chapter="selectChapter" />
      </aside>
      <section class="field-workspace">
        <section v-if="selectedGroup && !draft" class="definition-band">
          <div class="workspace-head"><div><span>字段编组</span><h1>{{ selectedGroup.label }}</h1></div><el-tag>{{ selectedGroup.groupCode }}</el-tag></div>
          <div class="form-grid two"><el-form-item label="编组名称"><el-input v-model="groupDraft.label" /></el-form-item><el-form-item label="数据关系"><el-select v-model="groupDraft.cardinality"><el-option label="单值" value="ONE" /><el-option label="数组/多行" value="MANY" /></el-select></el-form-item></div><el-button type="primary" @click="saveSelectedGroup">保存编组</el-button><el-button type="danger" plain @click="removeSelectedGroup">删除编组</el-button>
          <div class="group-field-order"><div class="group-field-order-head"><span>字段顺序</span><small>调整后自动保存</small></div><div v-for="(field,index) in selectedGroup.fields" :key="field.fieldCode" class="group-field-order-row"><span class="group-field-order-index">{{ String(index + 1).padStart(2, '0') }}</span><b>{{ field.label }}</b><code>{{ field.fieldCode }}</code><div class="group-field-order-actions"><el-tooltip content="上移" placement="top"><el-button circle text size="small" :icon="ArrowUp" :disabled="index===0" aria-label="上移" @click="moveGroupField(index,-1)" /></el-tooltip><el-tooltip content="下移" placement="top"><el-button circle text size="small" :icon="ArrowDown" :disabled="index===selectedGroup.fields.length-1" aria-label="下移" @click="moveGroupField(index,1)" /></el-tooltip></div></div><p v-if="!selectedGroup.fields.length" class="group-field-order-empty">当前编组暂无字段</p></div>
          <p class="form-help">当前编组包含 {{ selectedGroup.fields.length }} 个字段。点击左侧字段进入具体配置。</p>
        </section>
        <section v-else-if="selectedChapter && !draft" class="definition-band">
          <div class="workspace-head"><div><span>章节</span><h1>{{ selectedChapter.title }}</h1></div><el-tag>{{ selectedChapter.code }}</el-tag></div>
<div class="form-grid two"><el-form-item label="章节编号"><el-input v-model="selectedChapter.code" /></el-form-item><el-form-item label="章节名称"><el-input v-model="selectedChapter.title" /></el-form-item></div><el-button type="primary" @click="saveSelectedChapter">保存章节</el-button><el-button type="primary" plain @click="createGroupInChapter">新增编组</el-button><el-button type="danger" plain @click="removeSelectedChapter">删除章节</el-button><p class="form-help">该章节下可管理编组和字段。请从左侧选择具体编组或字段。</p>
        </section>
        <template v-if="draft">
          <div class="workspace-head">
            <div><span>全局字段库 / {{ groupDisplay(draft) || "未分组" }}</span><h1>{{ draft.label || "新标准字段" }}</h1></div>
            <div><el-button v-if="selected" type="danger" plain :icon="Delete" @click="removeField">删除字段</el-button><el-button type="primary" :loading="saving" @click="saveField">保存字段</el-button></div>
          </div>
          <div class="definition-band">
            <h2>字段定义</h2>
            <el-form label-position="top">
              <div class="form-grid four">
                <el-form-item label="字段名称"><el-input v-model="draft.label" /></el-form-item>
                <el-form-item label="字段编码"><el-input v-model="draft.fieldCode" disabled /></el-form-item>
                <el-form-item label="字段分组"><el-input :model-value="groupDisplay(draft)" disabled /></el-form-item>
                <el-form-item label="标准集合编码"><el-input v-model="draft.collectionCode" /></el-form-item>
              </div>
              <el-form-item label="业务定义"><el-input v-model="draft.description" type="textarea" :rows="2" /></el-form-item>
              <div class="form-grid four">
                <el-form-item label="数据类型"><el-select v-model="draft.dataType"><el-option v-for="item in dataTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
                <el-form-item label="数据关系"><el-select v-model="draft.cardinality"><el-option label="单值" value="ONE" /><el-option label="一对多" value="MANY" /></el-select></el-form-item>
                <el-form-item label="输出格式"><FieldOutputFormatSelect v-model="draft.outputFormat" :data-type="draft.dataType" /></el-form-item>
                <el-form-item label="排序号"><el-input-number v-model="draft.orderNo" :min="0" controls-position="right" /></el-form-item>
              </div>
              <div class="form-grid three">
                <el-form-item label="标准数据路径"><el-input v-model="draft.legacyJsonPath" placeholder="$.samples[*].sampleName" /></el-form-item>
                <el-form-item label="默认值"><el-input v-model="draft.defaultValue" /></el-form-item>
                <el-form-item label="结果校验正则"><el-input v-model="draft.validationRegex" /></el-form-item>
              </div>
              <div class="form-grid three database-row">
                <el-form-item label="数据库表"><el-input v-model="draft.dbTable" /></el-form-item>
                <el-form-item label="数据库列"><el-input v-model="draft.dbColumn" /></el-form-item>
                <el-form-item label="JSON 属性"><el-input v-model="draft.jsonKey" /></el-form-item>
              </div>
            </el-form>
          </div>
          <section class="references-band">
            <div class="rules-head"><div><h2>模板引用</h2></div></div>
            <el-table v-if="references.length" :data="references" size="small">
              <el-table-column label="模板" prop="templateName" min-width="240" />
              <el-table-column label="模板字段" prop="wordLabel" min-width="180" />
              <el-table-column label="字段编码" prop="fieldCode" min-width="180" />
              <el-table-column label="位置" prop="locationId" min-width="220" />
              <el-table-column label="表格" prop="tableNo" width="100" />
            </el-table>
            <el-empty v-else description="当前字段暂未被模板字段引用" :image-size="55" />
          </section>
          <div class="rules-band">
            <div class="rules-head"><div><h2>提取规则</h2></div><el-button type="primary" plain :icon="EditPen" @click="editRule(rules[0])">配置规则</el-button></div>
            <el-table :data="rules" row-key="id">
              <el-table-column prop="name" label="规则名称" min-width="150" />
              <el-table-column label="原始数据库字段" min-width="260"><template #default="scope"><span class="rule-source"><b>{{ ruleOrigin(scope.row) }}</b><small>{{ ruleMethodNote(scope.row) }}</small></span></template></el-table-column>
              <el-table-column label="结果处理" min-width="130"><template #default="scope"><span class="rule-transform"><b>{{ transformLabel(scope.row.transform) }}</b><small>写入 {{ draft.legacyJsonPath || draft.fieldCode }}</small></span></template></el-table-column>
              <el-table-column label="状态" width="76"><template #default="scope"><el-tag size="small" :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
              <el-table-column label="操作" width="130" align="right"><template #default="scope"><el-button link type="primary" :icon="EditPen" @click="editRule(scope.row)" /><el-button link type="danger" :icon="Delete" @click="removeRule(scope.row)" /></template></el-table-column>
            </el-table>
          </div>
        </template>
        <div v-else class="empty-state"><Coin /><h2>选择或新增标准字段</h2></div>
      </section>
    </main>

    <el-dialog v-model="ruleDialog" :title="ruleDraft?.id ? '编辑提取规则' : '新增提取规则'" width="min(960px, 94vw)" class="rule-editor-dialog">
      <el-form v-if="ruleDraft" label-position="top">
        <div class="form-grid three">
          <el-form-item label="规则名称"><el-input v-model="ruleDraft.name" /></el-form-item>
          <el-form-item label="提取方式"><el-select v-model="ruleDraft.sourceType"><el-option v-for="item in sourceTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        </div>
        <div class="rule-origin-note"><b>数据来源：</b>{{ ruleOrigin(ruleDraft) }}</div>
        <template v-if="ruleDraft.sourceType === 'PDF'">
          <el-form-item label="PDF 字段路径或字段编码"><el-input v-model="ruleConfig.sourcePath" placeholder="默认使用当前系统字段编码" /></el-form-item>
          <el-form-item label="PDF 取值正则（可选）"><el-input v-model="ruleConfig.valuePattern" /></el-form-item>
        </template>
        <template v-if="ruleDraft.sourceType === 'EXCEL'">
          <ExcelFieldRuleEditor v-model="ruleConfig" :fields="fields" />
          <ExcelWorkbookLocation :config="ruleConfig" />
        </template>
        <template v-if="ruleDraft.sourceType === 'AI'">
          <SystemAiRuleEditor v-model="ruleConfig" :fields="fields" />
        </template>
        <template v-if="ruleDraft.sourceType === 'CALCULATED'">
          <el-form-item label="依赖系统字段"><el-select v-model="ruleConfig.dependencies" multiple filterable><el-option v-for="item in fields" :key="item.fieldCode" :label="`${item.label} · ${item.fieldCode}`" :value="item.fieldCode" /></el-select></el-form-item>
          <el-form-item label="计算表达式"><el-input v-model="ruleConfig.expression" placeholder="例如 {sample.weight} / {sample.volume}" /></el-form-item>
          <el-form-item label="文本拼接模板"><el-input v-model="ruleConfig.textTemplate" placeholder="例如 {sample.name}（批号：{sample.batchNo}）" /><small class="form-help">计算表达式和文本拼接模板二选一。</small></el-form-item>
        </template>
        <template v-if="ruleDraft.sourceType === 'LIMS'">
        <el-form-item label="LIMS 解析方式"><el-select v-model="ruleConfig.extractionType"><el-option v-for="item in limsExtractionTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <div class="form-grid three parser-config-grid">
          <el-form-item label="上游解析器">
            <el-select v-model="ruleConfig.parser"><el-option v-for="item in parsers" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          </el-form-item>
          <el-form-item label="解析配置">
            <el-select v-model="ruleConfig.parserProfile" filterable allow-create clearable placeholder="选择或输入解析配置">
              <el-option v-for="item in parserProfiles" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="原始数据库字段"><el-input v-model="ruleConfig.inputField" placeholder="例如 UNITBODY" /></el-form-item>
        </div>
        <div class="form-grid two parser-config-grid">
          <el-form-item label="输出标准集合"><el-input v-model="ruleConfig.outputCollection" placeholder="例如 systemSuitability" /></el-form-item>
          <el-form-item label="输出 JSON 属性"><el-input v-model="ruleConfig.outputField" placeholder="例如 peakArea" /></el-form-item>
        </div>
        <el-form-item v-if="ruleConfig.extractionType === 'RAW_UNIT_FIELD'" label="LIMS TYPE 筛选值"><el-select v-model="ruleDraft.sourceUnitType"><el-option v-for="item in unitTypes" :key="item" :label="item" :value="item" /></el-select><small class="form-help">对应 LIMS SQL 查询结果中的 TYPE 字段。</small></el-form-item>
        <el-form-item v-if="['NORMALIZED_PATH','RAW_UNIT_FIELD'].includes(String(ruleConfig.extractionType || ''))" :label="ruleConfig.extractionType === 'RAW_UNIT_FIELD' ? 'UNITBODY.data[] 内的字段路径（不是正则）' : '标准 JSONPath（不是正则）'"><el-input v-model="ruleDraft.sourcePath" placeholder="例如 $.samples[*].sampleName" /></el-form-item>
        <template v-if="['RICH_TEXT_REGEX','HTML_TABLE_COLUMN'].includes(String(ruleConfig.extractionType || '')) || ruleConfig.parser === 'HTML_TABLE_GRID'">
          <el-form-item label="章节路径正则"><el-input v-model="ruleDraft.sectionPattern" placeholder="例如 实验材料|实验过程" /></el-form-item>
          <el-form-item v-if="ruleConfig.extractionType === 'HTML_TABLE_COLUMN' || ruleConfig.parser === 'HTML_TABLE_GRID'" label="表头特征正则"><el-input v-model="ruleDraft.headerPattern" placeholder="例如 No\.? .*保留时间.*峰面积" /></el-form-item>
          <el-form-item v-if="ruleConfig.extractionType === 'HTML_TABLE_COLUMN'" label="取值列标题正则"><el-input v-model="ruleDraft.sourcePath" placeholder="例如 批号|批次号" /></el-form-item>
          <el-form-item label="取值正则（可选）"><el-input v-model="ruleDraft.valuePattern" placeholder="存在捕获组时取第一个捕获组；否则取完整匹配" /></el-form-item>
          <el-form-item v-if="ruleConfig.parser === 'HTML_TABLE_GRID' || ruleConfig.extractionType === 'HTML_TABLE_COLUMN'" label="数据行过滤正则（可选）"><el-input v-model="ruleConfig.rowPattern" placeholder="例如 验证项目=.*系统适用性" /></el-form-item>
        </template>
        </template>
        <div class="form-grid two"><el-form-item label="结果转换"><el-select v-model="ruleDraft.transform"><el-option v-for="item in transforms" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="状态"><el-switch v-model="ruleDraft.enabled" active-text="启用" inactive-text="停用" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="ruleDialog = false">取消</el-button><el-button type="primary" @click="saveRule">保存规则</el-button></template>
    </el-dialog>

  </div>
</template>

<style scoped>
.rule-flow{padding:12px 20px;display:flex;align-items:stretch;gap:10px;border-bottom:1px solid #e2e7e4;background:#f7f9fc}.rule-flow>span{min-width:0;display:grid;gap:4px;color:#50635c;font-size:11px}.rule-flow>span:first-child{flex:.9}.rule-flow>span:nth-of-type(2){flex:1}.rule-flow>span:nth-of-type(3){flex:1.15}.rule-flow>span:last-child{flex:1.3}.rule-flow b{color:#75847e;font-size:10px;font-weight:500}.rule-flow code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rule-flow i{align-self:center;color:#8aa098;font-style:normal}.rule-source,.rule-transform{display:grid;gap:4px}.rule-source b,.rule-transform b{color:#31463f;font-size:11px;font-weight:600}.rule-source small,.rule-transform small{color:#71817b;font-size:10px;line-height:1.45}.rule-detail{display:flex;flex-wrap:wrap;align-items:center;gap:5px 8px}.rule-detail>span{min-width:0;display:flex;align-items:center;gap:5px}.rule-detail>span b{flex:none;color:#71817b;font-size:10px;font-weight:500}.rule-detail code{max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.rule-origin-note{margin-bottom:14px;padding:10px 12px;color:#50635c;background:#f4f7fb;border:1px solid #dce5e1;font-size:11px;line-height:1.6}.parser-config-grid{padding:10px 12px 0;background:#f7f9fc}.parser-config-grid+.parser-config-grid{margin-bottom:14px;padding-top:0}.form-help{display:block;margin-top:5px;color:#71817b;font-size:10px}.raw-json-head{width:100%;display:flex;align-items:center;justify-content:space-between;gap:18px}.raw-json-head h2{margin:0;color:#263548;font-size:17px}.raw-json-head span{display:block;margin-top:5px;color:#6b7c75;font-size:11px}.raw-json-body{height:100%;min-height:280px;display:flex;flex-direction:column}.raw-json-body>p{margin:0 0 12px;padding:10px 12px;color:#52665f;background:#f4f7fb;border:1px solid #dce5e1;font-size:11px;line-height:1.65}.raw-json-body>p code{color:#235c4d}.raw-json-body pre{min-height:0;flex:1;margin:0;padding:16px;overflow:auto;color:#d8e6e1;background:#19312b;border-radius:4px;font:11px/1.65 Consolas,"SFMono-Regular",monospace;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:1400px){.rule-flow{flex-wrap:wrap}.rule-flow i{display:none}.rule-flow>span{flex:1 1 40%!important}}
.lims-catalog{--space-xs:4px;--space-sm:8px;--space-md:12px;--space-lg:16px;--space-xl:24px;height:100%;min-width:0;color:#263731;background:#f4f7fb;overflow:hidden}.module-header{height:64px;padding:0 var(--space-xl);display:flex;align-items:center;background:#fff;border-bottom:1px solid #e4eaf2}.module-title{display:flex;align-items:center;gap:var(--space-md)}.module-title>svg{width:22px;color:#2167e8}.module-title strong,.module-title small{display:block}.module-title strong{color:#263548;font-size:14px}.module-title small{margin-top:3px;color:#6b7c75;font-size:10px}.header-actions{margin-left:auto;display:flex;gap:var(--space-sm)}.header-actions .el-button{margin:0}.catalog-main{height:calc(100% - 64px);display:grid;grid-template-columns:380px minmax(0,1fr)}.field-index{min-height:0;padding:18px 14px 0;display:flex;flex-direction:column;background:#fff;border-right:1px solid #e4eaf2}.index-head{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:14px}.index-head h1{margin:0;color:#263548;font-size:18px}.index-head span{color:#6d7e78;font-size:11px}.field-list{min-height:0;flex:1;overflow:auto;margin-top:var(--space-md);padding-bottom:var(--space-lg)}.field-list section{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 7px}.field-list section h2{grid-column:1/-1;margin:14px 8px 1px;display:flex;justify-content:space-between;color:#53675f;font-size:12px}.field-list section h2 span{font-weight:400}.field-list button{width:100%;min-width:0;min-height:44px;padding:6px var(--space-sm);display:grid;grid-template-columns:minmax(0,1fr) 8px;align-items:center;gap:6px;border:1px solid #e4e9e6;border-radius:4px;background:#fff;text-align:left;cursor:pointer;transition:background-color 180ms ease-out,border-color 180ms ease-out}.field-list button:hover{background:#f1f6f4;border-color:#b8cbc4}.field-list button.selected{background:#e5f0ed;border-color:#4f8ee8}.field-list b,.field-list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.field-list b{font-size:12px}.field-list small{margin-top:3px;color:#687a73;font-size:10px}.field-state{width:7px;height:7px;border-radius:50%;background:#49a36e}.field-state.disabled{background:#9aa6a1}.field-workspace{min-width:0;overflow:auto;padding:var(--space-xl) 28px}.workspace-head,.rules-head,.preview-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.workspace-head>div:last-child{display:flex;gap:var(--space-sm)}.workspace-head span,.rules-head span,.preview-head span{color:#6b7c75;font-size:11px}.workspace-head h1{margin:6px 0 0;color:#263548;font-size:24px}.result-preview-band,.definition-band,.rules-band{margin-top:20px;background:#fff;border:1px solid #d7dfdb}.result-preview-band{min-height:118px}.preview-head{padding:var(--space-lg) 20px;border-bottom:1px solid #e2e7e4}.preview-head h2,.definition-band h2,.rules-head h2{margin:0 0 var(--space-lg);color:#234c41;font-size:16px}.preview-head h2,.rules-head h2{margin-bottom:var(--space-xs)}.preview-empty{min-height:68px;padding:var(--space-xl);display:grid;place-items:center;color:#6b7c75;font-size:12px}.preview-value{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#263548;font-weight:600}.preview-context b,.preview-context small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.preview-context b{font-size:12px;font-weight:500}.preview-context small{margin-top:2px;color:#708079;font-size:10px}.definition-band{padding:20px}.form-grid{display:grid;gap:var(--space-md)}.form-grid.two{grid-template-columns:1fr 1fr}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.form-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.database-row{margin-top:var(--space-xs);padding-top:14px;border-top:1px solid #e4e9e6}.rules-band{padding:0;overflow-x:auto}.rules-head{padding:18px 20px;border-bottom:1px solid #e2e7e4}.rules-band code{color:#31594e}.empty-state{height:100%;display:grid;place-content:center;text-align:center;color:#708079}.empty-state svg{width:36px;margin:auto}.empty-state h2{font-size:18px}.el-select,.el-input-number{width:100%}@media(max-width:1400px){.catalog-main{grid-template-columns:360px minmax(0,1fr)}.field-workspace{padding:var(--space-xl)}.form-grid.four{grid-template-columns:1fr 1fr}}@media(prefers-reduced-motion:reduce){.field-list button{transition:none}}
.chapter-entry{min-width:0}.field-list .chapter-row{--indent:calc(var(--chapter-depth) * 16px);width:100%;height:34px;min-height:34px;padding:0 8px 0 calc(4px + var(--indent));display:grid;grid-template-columns:14px minmax(34px,auto) minmax(0,1fr) 24px;align-items:center;gap:6px;border:0;border-bottom:1px solid #f4f7fb;border-radius:0;background:transparent;color:#3d554d;text-align:left;cursor:pointer}.field-list .chapter-row:hover{background:#f1f6f4;border-color:#f4f7fb}.chapter-row.muted{opacity:.58}.chapter-row b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;font-weight:600}.chapter-caret{display:block;color:#71827b;font-size:18px;line-height:1;transform:rotate(0deg);transition:transform 160ms ease-out}.chapter-caret.open{transform:rotate(90deg)}.chapter-code{color:#697a74;font:10px/1.2 Consolas,"SFMono-Regular",monospace}.chapter-count{color:#84928d;font-size:10px;text-align:right}.chapter-fields{margin:4px 0 8px;padding-left:calc(20px + var(--chapter-depth) * 16px);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 7px}.field-list .field-item{width:100%;min-width:0;min-height:44px;padding:6px var(--space-sm);display:grid;grid-template-columns:minmax(0,1fr) 8px;align-items:center;gap:6px;border:1px solid #e4e9e6;border-radius:4px;background:#fff;text-align:left;cursor:pointer}.field-list .field-item:hover{background:#f1f6f4;border-color:#b8cbc4}.field-list .field-item.selected{background:#e5f0ed;border-color:#4f8ee8}.unmapped-fields{margin-top:14px;padding-top:6px;border-top:1px solid #dde4e1}.field-list .unmapped-fields h2{margin-top:4px}.field-list .el-empty{padding:28px 0}
.preview-actions{display:flex;align-items:center;gap:8px}.preview-instance-select{width:360px}.preview-option{display:grid;gap:2px;line-height:1.25}.preview-option b{max-width:310px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#31463f;font-size:12px;font-weight:500}.preview-option small{color:#71817b;font-size:10px}@media(max-width:1200px){.preview-actions{width:100%;align-items:stretch}.preview-instance-select{min-width:0;flex:1}.preview-head{align-items:stretch;flex-direction:column}}
@media(prefers-reduced-motion:reduce){.chapter-caret{transition:none}}
.group-field-order{margin-top:18px;padding:14px 16px;border:1px solid #e1e8e5;border-radius:8px;background:#f8fafb}.group-field-order-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;color:#30483f;font-size:12px;font-weight:650}.group-field-order-head small{color:#81908a;font-size:10px;font-weight:400}.group-field-order-row{min-height:38px;display:grid;grid-template-columns:34px minmax(120px,1fr) minmax(120px,1fr) auto;align-items:center;gap:10px;padding:5px 4px;border-top:1px solid #e8eeeb}.group-field-order-index{color:#7d9188;font:11px/1 Consolas,monospace}.group-field-order-row b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#2d443b;font-size:12px;font-weight:550}.group-field-order-row code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#778a83;font:10px/1.3 Consolas,monospace}.group-field-order-actions{display:flex;gap:2px}.group-field-order-actions .el-button{width:28px;height:28px;margin:0;color:#477265}.group-field-order-actions .el-button:not(.is-disabled):hover{color:#2167e8;background:#e8f0ff}.group-field-order-empty{margin:10px 0 2px;color:#8a9993;font-size:11px;text-align:center}@media(max-width:700px){.group-field-order-row{grid-template-columns:28px minmax(0,1fr) auto}.group-field-order-row code{display:none}}.group-index{max-height:220px;overflow:auto;margin-bottom:12px}.group-index h1{margin:0 0 8px;font-size:13px}.group-index .el-menu{border-right:0}.group-index .el-menu-item{height:36px;line-height:36px;padding:0 10px!important;display:flex;justify-content:space-between}</style>
