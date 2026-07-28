<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Coin, CopyDocument, Delete, EditPen, Plus, Refresh, Search, View } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  adminApi,
  type LimsFieldSourcePreview,
  type LimsExtractionRule,
  type StandardField,
  type StandardFieldCatalogChapter,
  type StandardFieldPreview,
  type StandardFieldPreviewItem,
} from "./admin-api";

const loading = ref(false);
const saving = ref(false);
const fields = ref<StandardField[]>([]);
const chapters = ref<StandardFieldCatalogChapter[]>([]);
const catalogUnmappedFields = ref<StandardField[]>([]);
const expandedChapters = ref<Set<number>>(new Set());
const selected = ref<StandardField>();
const draft = ref<Partial<StandardField>>();
const rules = ref<LimsExtractionRule[]>([]);
const search = ref("");
const ruleDialog = ref(false);
const ruleDraft = ref<Partial<LimsExtractionRule>>();
const ruleConfig = ref<Record<string, unknown>>({});
const preview = ref<StandardFieldPreview>();
const previewLoading = ref(false);
const previewInstanceIds = ref<string[]>([]);
const rawJsonVisible = ref(false);
const rawJsonLoading = ref(false);
const rawJson = ref<unknown>();
const rawJsonMatch = ref<LimsFieldSourcePreview>();
const rawJsonContext = ref<StandardFieldPreviewItem>();
let previewRequest = 0;

const dataTypes = [
  { value: "string", label: "文本" }, { value: "decimal", label: "数值" },
  { value: "date", label: "日期" }, { value: "richText", label: "富文本" },
  { value: "boolean", label: "布尔值" }, { value: "image", label: "图片" },
];
const sourceTypes = [
  { value: "NORMALIZED_PATH", label: "标准 JSONPath（非正则）" },
  { value: "RAW_UNIT_FIELD", label: "原始 UNITBODY JSONPath" },
  { value: "RICH_TEXT_REGEX", label: "富文本正文 + 正则" },
  { value: "HTML_TABLE_COLUMN", label: "HTML 表格列 + 正则" },
];
const transforms = [
  { value: "TRIM", label: "去除首尾空白" }, { value: "NUMBER", label: "转换为数值" },
  { value: "DATE", label: "转换为日期" }, { value: "UPPER", label: "转为大写" },
  { value: "LOWER", label: "转为小写" },
];
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
];
const unitTypes = ["Sample", "Standard", "Equipment", "Chromatogram", "Reagent", "Weighing"];
const sourceTypeLabel = (value: string) => sourceTypes.find((item) => item.value === value)?.label || value;
const parserLabel = (rule: LimsExtractionRule) => {
  const parser = String(rule.config?.parser || "");
  return parsers.find((item) => item.value === parser)?.label || sourceTypeLabel(rule.sourceType);
};
const rawJsonText = computed(() => JSON.stringify(rawJson.value || {}, null, 2));

function ruleOrigin(rule: Partial<LimsExtractionRule>) {
  const parser = String(rule.config?.parser || "");
  if (parser === "HTML_TABLE_GRID") return "LIMS SQL：UNITBODY（TYPE=RichText）内的 HTML 表格";
  if (parser === "STRUCTURED_UNIT") return "LIMS SQL：结构化 UNITBODY";
  if (parser === "INSTANCE_FIELD") return `LIMS 实验实例字段：${String(rule.config?.inputField || "")}`;
  if (rule.sourceType === "NORMALIZED_PATH") return "非直接读库：标准化中间 JSON";
  if (rule.sourceType === "RAW_UNIT_FIELD") return `LIMS SQL：UNITBODY → data[]${rule.sourceUnitType ? `（TYPE=${rule.sourceUnitType}）` : ""}`;
  if (rule.sourceType === "RICH_TEXT_REGEX") return "LIMS SQL：UNITBODY（TYPE=RichText）";
  if (rule.sourceType === "HTML_TABLE_COLUMN") return "LIMS SQL：UNITBODY 内的 HTML 表格";
  return "未指定来源";
}
function transformLabel(value: string) {
  return transforms.find((item) => item.value === value)?.label || value || "不转换";
}
function ruleMethodNote(rule: LimsExtractionRule) {
  const parser = String(rule.config?.parser || "");
  if (parser === "HTML_TABLE_GRID") return `按章节和表头正则定位表格，使用 ${String(rule.config?.parserProfile || "未指定配置")} 解析行列后写入标准 JSON`;
  if (parser === "STRUCTURED_UNIT") return `按 ${String(rule.config?.parserProfile || rule.sourceUnitType || "UNIT 类型")} 识别结构化单元，再读取目标属性`;
  if (rule.sourceType === "NORMALIZED_PATH") return rule.valuePattern ? "JSONPath 读取后再用正则捕获；上游字段由导入解析器定义" : "按 JSONPath 直接读取，不使用正则；上游字段由导入解析器定义";
  if (rule.sourceType === "RAW_UNIT_FIELD") return rule.valuePattern ? "按字段路径读取后再用正则捕获" : "按原始 JSON 字段路径直接读取，不使用正则";
  if (rule.sourceType === "RICH_TEXT_REGEX") return "先用章节正则筛选正文，再用取值正则捕获";
  if (rule.sourceType === "HTML_TABLE_COLUMN") return "依次用章节、表头和列标题正则定位，再读取单元格";
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
    catalogUnmappedFields.value = catalog.unmappedFields;
    const allChapterIds = new Set<number>();
    const visit = (items: StandardFieldCatalogChapter[]) => items.forEach((item) => {
      allChapterIds.add(item.id);
      visit(item.children);
    });
    visit(chapters.value);
    expandedChapters.value = allChapterIds;
    const target = fields.value.find((item) => item.fieldCode === (preferred || selected.value?.fieldCode)) || fields.value[0];
    if (target) await selectField(target);
  } catch (error) { ElMessage.error(errorText(error)); }
  finally { loading.value = false; }
}
async function selectField(field: StandardField) {
  selected.value = field;
  draft.value = JSON.parse(JSON.stringify(field));
  previewInstanceIds.value = [];
  await Promise.all([loadRules(field.fieldCode), loadPreview(field.fieldCode)]);
}
async function loadRules(fieldCode: string) {
  try { rules.value = await adminApi.extractionRules(fieldCode); }
  catch (error) { ElMessage.error(errorText(error)); }
}
async function loadPreview(fieldCode?: string) {
  if (!fieldCode) { preview.value = undefined; return; }
  const requestId = ++previewRequest;
  previewLoading.value = true;
  try {
    const result = await adminApi.standardFieldPreview(
      fieldCode,
      previewInstanceIds.value.length ? Math.min(50, previewInstanceIds.value.length) : 12,
      previewInstanceIds.value,
    );
    if (requestId === previewRequest) preview.value = result;
  } catch (error) {
    if (requestId === previewRequest) preview.value = undefined;
    ElMessage.error(errorText(error));
  } finally {
    if (requestId === previewRequest) previewLoading.value = false;
  }
}
function previewOptionLabel(item: NonNullable<StandardFieldPreview["options"]>[number]) {
  return `${item.experimentTitle || item.projectName || "未命名实验"} · ${item.instanceId}`;
}
function changePreviewSelection() {
  void loadPreview(selected.value?.fieldCode);
}
function previewValue(value: unknown) {
  if (Array.isArray(value)) {
    if (!value.length) return "-";
    const rendered = value.map((item) => typeof item === "string" ? item : JSON.stringify(item));
    const unique = Array.from(new Set(rendered));
    if (unique.length === 1) return `${unique[0]}（${value.length} 项）`;
    return `${unique.slice(0, 2).join("、")}${unique.length > 2 ? ` 等 ${unique.length} 种` : ""}（共 ${value.length} 项）`;
  }
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}
function evidenceLabel(evidence: Record<string, unknown>, fallback: string) {
  const section = evidence.sectionPath || evidence.section || evidence.chapterPath;
  if (Array.isArray(section)) return section.join(" / ");
  return String(section || fallback || "标准记录");
}
async function showRawJson(item: StandardFieldPreviewItem) {
  rawJsonContext.value = item;
  rawJson.value = undefined;
  rawJsonMatch.value = undefined;
  rawJsonVisible.value = true;
  rawJsonLoading.value = true;
  try {
    const result = await adminApi.rawLimsFieldSource(selected.value?.fieldCode || "", item);
    rawJsonMatch.value = result;
    rawJson.value = result.source;
  } catch (error) {
    ElMessage.error(errorText(error));
  } finally {
    rawJsonLoading.value = false;
  }
}
async function copyRawJson() {
  try {
    await navigator.clipboard.writeText(rawJsonText.value);
    ElMessage.success("原始 JSON 已复制");
  } catch {
    ElMessage.error("复制失败，请在 JSON 内容中手动选择复制");
  }
}
function newField() {
  selected.value = undefined;
  rules.value = [];
  preview.value = undefined;
  previewInstanceIds.value = [];
  draft.value = {
    fieldCode: "", label: "", groupCode: "项目信息", collectionCode: "project",
    dataType: "string", cardinality: "ONE", dbTable: "lims_standard_records",
    dbColumn: "data_json", jsonKey: "", legacyJsonPath: "", description: "",
    outputFormat: "", defaultValue: "", validationRegex: "", orderNo: fields.value.length,
    enabled: true,
  };
}
async function saveField() {
  if (!draft.value?.fieldCode?.trim() || !draft.value.label?.trim()) return ElMessage.warning("字段编码和名称不能为空");
  saving.value = true;
  try {
    const saved = selected.value
      ? await adminApi.updateStandardField(selected.value.fieldCode, draft.value)
      : await adminApi.createStandardField(draft.value);
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
    preview.value = undefined;
    await loadFields();
    ElMessage.success("标准字段已删除");
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(errorText(error)); }
}
function editRule(rule?: LimsExtractionRule) {
  if (!draft.value?.fieldCode) return ElMessage.warning("请先保存标准字段，再配置提取规则");
  const nextRule: Partial<LimsExtractionRule> = rule ? JSON.parse(JSON.stringify(rule)) : {
    fieldCode: draft.value.fieldCode, name: "新提取规则", sourceType: "NORMALIZED_PATH",
    sourceUnitType: "", sourcePath: draft.value.legacyJsonPath || "", sectionPattern: "",
    headerPattern: "", valuePattern: "", transform: "TRIM", priority: (rules.value.length + 1) * 10,
    config: { parser: "NORMALIZED_JSON" }, enabled: true,
  };
  ruleDraft.value = nextRule;
  ruleConfig.value = JSON.parse(JSON.stringify(nextRule.config || {}));
  ruleDialog.value = true;
}
async function saveRule() {
  if (!ruleDraft.value?.name?.trim() || !selected.value) return ElMessage.warning("规则名称不能为空");
  try {
    ruleDraft.value.config = JSON.parse(JSON.stringify(ruleConfig.value));
    if (ruleDraft.value.id) await adminApi.updateExtractionRule(ruleDraft.value.id, ruleDraft.value);
    else await adminApi.createExtractionRule(selected.value.fieldCode, ruleDraft.value);
    rules.value = await adminApi.extractionRules(selected.value.fieldCode);
    ruleDialog.value = false;
    ElMessage.success("提取规则已保存");
  } catch (error) { ElMessage.error(errorText(error)); }
}
async function removeRule(rule: LimsExtractionRule) {
  try {
    await ElMessageBox.confirm(`删除提取规则“${rule.name}”？`, "删除规则", { type: "warning" });
    await adminApi.deleteExtractionRule(rule.id);
    rules.value = rules.value.filter((item) => item.id !== rule.id);
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(errorText(error)); }
}
onMounted(() => loadFields());
</script>

<template>
  <div class="lims-catalog">
    <header class="module-header">
      <div class="module-title"><Coin /><div><strong>LIMS 标准字段</strong><small>字段字典与提取规则</small></div></div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadFields()">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="newField">新增标准字段</el-button>
      </div>
    </header>
    <main class="catalog-main">
      <aside class="field-index">
        <div class="index-head"><h1>标准字段目录</h1><span>{{ fields.length }} 个字段</span></div>
        <el-input v-model="search" :prefix-icon="Search" placeholder="搜索字段名称或编码" clearable />
        <div v-loading="loading" class="field-list">
          <div v-for="row in visibleChapterRows" :key="row.node.id" class="chapter-entry">
            <button
              class="chapter-row"
              :class="{ muted: !row.node.enabled }"
              :style="{ '--chapter-depth': row.depth }"
              :aria-expanded="row.open"
              @click="toggleChapter(row.node.id)"
            >
              <span class="chapter-caret" :class="{ open: row.open }">›</span>
              <span class="chapter-code">{{ row.node.code }}</span>
              <b>{{ row.node.title }}</b>
              <span class="chapter-count">{{ row.node.fieldCount }}</span>
            </button>
            <div v-if="row.open && row.node.fields.length" class="chapter-fields" :style="{ '--chapter-depth': row.depth }">
              <button v-for="item in row.node.fields" :key="`${row.node.id}-${item.fieldCode}`" class="field-item" :class="{ selected: selected?.fieldCode === item.fieldCode }" @click="selectField(item)">
                <span><b>{{ item.label }}</b><small>{{ item.fieldCode }}</small></span>
                <span class="field-state" :class="{ disabled: !item.enabled }" :title="item.enabled ? '已启用' : '已停用'" />
              </button>
            </div>
          </div>
          <section v-if="unmappedFields.length" class="unmapped-fields">
            <h2>未映射字段<span>{{ unmappedFields.length }}</span></h2>
            <button v-for="item in unmappedFields" :key="item.fieldCode" class="field-item" :class="{ selected: selected?.fieldCode === item.fieldCode }" @click="selectField(item)">
              <span><b>{{ item.label }}</b><small>{{ item.fieldCode }}</small></span>
              <span class="field-state" :class="{ disabled: !item.enabled }" :title="item.enabled ? '已启用' : '已停用'" />
            </button>
          </section>
          <el-empty v-if="!loading && !visibleChapterRows.length && !unmappedFields.length" :image-size="52" description="没有匹配的字段或章节" />
        </div>
      </aside>
      <section class="field-workspace">
        <template v-if="draft">
          <div class="workspace-head">
            <div><span>全局字段库 / {{ draft.groupCode || "未分组" }}</span><h1>{{ draft.label || "新标准字段" }}</h1></div>
            <div><el-button v-if="selected" type="danger" plain :icon="Delete" @click="removeField">删除字段</el-button><el-button type="primary" :loading="saving" @click="saveField">保存字段</el-button></div>
          </div>
          <section v-loading="previewLoading" class="result-preview-band">
            <div class="preview-head">
              <div>
                <h2>字段结果预览</h2>
                <span v-if="preview?.storageSupported && preview.total">共 {{ preview.total }} 个实验记录<template v-if="preview.recognizedTotal !== undefined">、{{ preview.recognizedTotal }} 个识别结果</template>，显示最近 {{ preview.items.length }} 个实验记录</span>
                <span v-else>最近解析的 LIMS 标准数据</span>
              </div>
              <div class="preview-actions">
                <el-select
                  v-model="previewInstanceIds"
                  class="preview-instance-select"
                  multiple
                  filterable
                  clearable
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="选择实验记录（默认最近 12 个）"
                  :disabled="!selected || previewLoading"
                  @change="changePreviewSelection"
                >
                  <el-option
                    v-for="item in preview?.options || []"
                    :key="item.instanceId"
                    :label="previewOptionLabel(item)"
                    :value="item.instanceId"
                  >
                    <span class="preview-option"><b>{{ item.experimentTitle || item.projectName || '未命名实验' }}</b><small>{{ item.instanceId }} · {{ item.recognizedCount }} 个识别结果</small></span>
                  </el-option>
                </el-select>
                <el-button :icon="Refresh" :disabled="!selected" @click="loadPreview(selected?.fieldCode)">刷新预览</el-button>
              </div>
            </div>
            <el-table v-if="preview?.items.length" :data="preview.items" size="small" max-height="260">
              <el-table-column label="识别结果" min-width="220">
                <template #default="scope"><span class="preview-value" :title="previewValue(scope.row.value)">{{ previewValue(scope.row.value) }}</span></template>
              </el-table-column>
              <el-table-column label="实验记录" min-width="190">
                <template #default="scope"><span class="preview-context"><b>{{ scope.row.experimentTitle || scope.row.projectName || '未命名实验' }}</b><small>{{ scope.row.instanceId }}</small></span></template>
              </el-table-column>
              <el-table-column label="数据来源" min-width="190">
                <template #default="scope"><span class="preview-context"><b>{{ evidenceLabel(scope.row.evidence, scope.row.collectionCode) }}</b><small>{{ scope.row.fileName }}</small></span></template>
              </el-table-column>
              <el-table-column label="原始数据" width="132" align="right">
                <template #default="scope"><el-button link type="primary" :icon="View" @click="showRawJson(scope.row)">查看原始 JSON</el-button></template>
              </el-table-column>
            </el-table>
            <div v-else-if="preview && !preview.storageSupported" class="preview-empty">当前数据库位置暂不支持自动预览</div>
            <div v-else-if="!previewLoading" class="preview-empty">暂无已解析结果，导入并识别 LIMS 数据后会显示在这里</div>
          </section>
          <div class="definition-band">
            <h2>字段定义</h2>
            <el-form label-position="top">
              <div class="form-grid four">
                <el-form-item label="字段名称"><el-input v-model="draft.label" /></el-form-item>
                <el-form-item label="字段编码"><el-input v-model="draft.fieldCode" :disabled="Boolean(selected)" /></el-form-item>
                <el-form-item label="字段分组"><el-input v-model="draft.groupCode" /></el-form-item>
                <el-form-item label="标准集合编码"><el-input v-model="draft.collectionCode" /></el-form-item>
              </div>
              <el-form-item label="业务定义"><el-input v-model="draft.description" type="textarea" :rows="2" /></el-form-item>
              <div class="form-grid four">
                <el-form-item label="数据类型"><el-select v-model="draft.dataType"><el-option v-for="item in dataTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
                <el-form-item label="数据关系"><el-select v-model="draft.cardinality"><el-option label="单值" value="ONE" /><el-option label="一对多" value="MANY" /></el-select></el-form-item>
                <el-form-item label="输出格式"><el-input v-model="draft.outputFormat" placeholder="如 2 或 %Y-%m-%d" /></el-form-item>
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
              <el-checkbox v-model="draft.enabled">启用该标准字段</el-checkbox>
            </el-form>
          </div>
          <div class="rules-band">
            <div class="rules-head"><div><h2>提取规则</h2><span>按优先级从小到大执行，首个有效结果写入标准字段；“正则”与“JSONPath”会明确区分</span></div><el-button type="primary" plain :icon="Plus" @click="editRule()">新增规则</el-button></div>
            <div class="rule-flow" aria-label="当前字段数据流">
              <span><b>原始来源</b>LIMS SQL 导出字段</span><i>→</i>
              <span><b>规则处理</b>JSONPath / 正则 / 表格列</span><i>→</i>
              <span><b>标准 JSON</b><code>{{ draft.legacyJsonPath || draft.fieldCode }}</code></span><i>→</i>
              <span><b>入库位置</b><code>{{ draft.dbTable }}.{{ draft.dbColumn }}<template v-if="draft.jsonKey"> → {{ draft.jsonKey }}</template></code></span>
            </div>
            <el-table :data="rules" row-key="id">
              <el-table-column prop="priority" label="优先级" width="76" />
              <el-table-column prop="name" label="规则名称" min-width="150" />
              <el-table-column label="原始数据库字段" min-width="260"><template #default="scope"><span class="rule-source"><b>{{ ruleOrigin(scope.row) }}</b><small>{{ ruleMethodNote(scope.row) }}</small></span></template></el-table-column>
              <el-table-column label="定位与提取规则" min-width="330">
                <template #default="scope">
                  <div class="rule-detail">
                    <el-tag size="small" effect="plain">{{ parserLabel(scope.row) }}</el-tag>
                    <span v-if="scope.row.config?.parserProfile"><b>解析配置</b><code>{{ scope.row.config.parserProfile }}</code></span>
                    <span v-if="scope.row.sourcePath"><b>{{ scope.row.sourceType === 'HTML_TABLE_COLUMN' ? '列标题正则' : '字段路径' }}</b><code>{{ scope.row.sourcePath }}</code></span>
                    <span v-if="scope.row.sectionPattern"><b>章节正则</b><code>/{{ scope.row.sectionPattern }}/i</code></span>
                    <span v-if="scope.row.headerPattern"><b>表头正则</b><code>/{{ scope.row.headerPattern }}/i</code></span>
                    <span v-if="scope.row.valuePattern"><b>取值正则</b><code>/{{ scope.row.valuePattern }}/is</code></span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="结果处理" min-width="130"><template #default="scope"><span class="rule-transform"><b>{{ transformLabel(scope.row.transform) }}</b><small>写入 {{ draft.legacyJsonPath || draft.fieldCode }}</small></span></template></el-table-column>
              <el-table-column label="状态" width="76"><template #default="scope"><el-tag size="small" :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
              <el-table-column label="操作" width="130" align="right"><template #default="scope"><el-button link type="primary" :icon="EditPen" @click="editRule(scope.row)" /><el-button link type="danger" :icon="Delete" @click="removeRule(scope.row)" /></template></el-table-column>
            </el-table>
          </div>
        </template>
        <div v-else class="empty-state"><Coin /><h2>选择或新增标准字段</h2></div>
      </section>
    </main>

    <el-dialog v-model="ruleDialog" :title="ruleDraft?.id ? '编辑提取规则' : '新增提取规则'" width="720px">
      <el-form v-if="ruleDraft" label-position="top">
        <div class="form-grid three">
          <el-form-item label="规则名称"><el-input v-model="ruleDraft.name" /></el-form-item>
          <el-form-item label="提取方式"><el-select v-model="ruleDraft.sourceType"><el-option v-for="item in sourceTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="优先级"><el-input-number v-model="ruleDraft.priority" :min="1" controls-position="right" /></el-form-item>
        </div>
        <div class="rule-origin-note"><b>数据来源：</b>{{ ruleOrigin(ruleDraft) }}</div>
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
        <el-form-item v-if="ruleDraft.sourceType === 'RAW_UNIT_FIELD'" label="LIMS TYPE 筛选值"><el-select v-model="ruleDraft.sourceUnitType"><el-option v-for="item in unitTypes" :key="item" :label="item" :value="item" /></el-select><small class="form-help">对应 LIMS SQL 查询结果中的 TYPE 字段。</small></el-form-item>
        <el-form-item v-if="['NORMALIZED_PATH','RAW_UNIT_FIELD'].includes(ruleDraft.sourceType || '')" :label="ruleDraft.sourceType === 'NORMALIZED_PATH' ? '标准 JSONPath（不是正则）' : 'UNITBODY.data[] 内的字段路径（不是正则）'"><el-input v-model="ruleDraft.sourcePath" placeholder="例如 ext$.mtlname" /></el-form-item>
        <template v-if="['RICH_TEXT_REGEX','HTML_TABLE_COLUMN'].includes(ruleDraft.sourceType || '') || ruleConfig.parser === 'HTML_TABLE_GRID'">
          <el-form-item label="章节路径正则"><el-input v-model="ruleDraft.sectionPattern" placeholder="例如 实验材料|实验过程" /></el-form-item>
          <el-form-item v-if="ruleDraft.sourceType === 'HTML_TABLE_COLUMN' || ruleConfig.parser === 'HTML_TABLE_GRID'" label="表头特征正则"><el-input v-model="ruleDraft.headerPattern" placeholder="例如 No\.? .*保留时间.*峰面积" /></el-form-item>
          <el-form-item v-if="ruleDraft.sourceType === 'HTML_TABLE_COLUMN'" label="取值列标题正则"><el-input v-model="ruleDraft.sourcePath" placeholder="例如 批号|批次号" /></el-form-item>
          <el-form-item label="取值正则（可选）"><el-input v-model="ruleDraft.valuePattern" placeholder="存在捕获组时取第一个捕获组；否则取完整匹配" /></el-form-item>
        </template>
        <div class="form-grid two"><el-form-item label="结果转换"><el-select v-model="ruleDraft.transform"><el-option v-for="item in transforms" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="状态"><el-switch v-model="ruleDraft.enabled" active-text="启用" inactive-text="停用" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="ruleDialog = false">取消</el-button><el-button type="primary" @click="saveRule">保存规则</el-button></template>
    </el-dialog>

    <el-drawer v-model="rawJsonVisible" size="58%" class="raw-json-drawer" destroy-on-close>
      <template #header>
        <div class="raw-json-head">
          <div><h2>当前字段的原始 JSON</h2><span>{{ selected?.label }} · {{ rawJsonContext?.fileName }} · 实验实例 {{ rawJsonContext?.instanceId }}</span></div>
          <el-button :icon="CopyDocument" :disabled="rawJsonLoading || !rawJson" @click="copyRawJson">复制 JSON</el-button>
        </div>
      </template>
      <div v-loading="rawJsonLoading" class="raw-json-body">
        <p v-if="rawJsonMatch?.matchedBy !== 'none'">这是当前字段在该实验记录下的完整 JSON；最外层按实验实例聚合，内部按 <code>unitId</code> 分组并保留全部识别结果与来源项。</p>
        <p v-else-if="!rawJsonLoading">当前标准记录缺少可定位的 <code>unitId / richTextId</code>，未返回整份实验 JSON。</p>
        <pre v-if="rawJson">{{ rawJsonText }}</pre>
        <el-empty v-else-if="!rawJsonLoading" description="未找到当前字段对应的原始 JSON 记录" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.rule-flow{padding:12px 20px;display:flex;align-items:stretch;gap:10px;border-bottom:1px solid #e2e7e4;background:#f6f8f7}.rule-flow>span{min-width:0;display:grid;gap:4px;color:#50635c;font-size:11px}.rule-flow>span:first-child{flex:.9}.rule-flow>span:nth-of-type(2){flex:1}.rule-flow>span:nth-of-type(3){flex:1.15}.rule-flow>span:last-child{flex:1.3}.rule-flow b{color:#75847e;font-size:10px;font-weight:500}.rule-flow code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rule-flow i{align-self:center;color:#8aa098;font-style:normal}.rule-source,.rule-transform{display:grid;gap:4px}.rule-source b,.rule-transform b{color:#31463f;font-size:11px;font-weight:600}.rule-source small,.rule-transform small{color:#71817b;font-size:10px;line-height:1.45}.rule-detail{display:flex;flex-wrap:wrap;align-items:center;gap:5px 8px}.rule-detail>span{min-width:0;display:flex;align-items:center;gap:5px}.rule-detail>span b{flex:none;color:#71817b;font-size:10px;font-weight:500}.rule-detail code{max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.rule-origin-note{margin-bottom:14px;padding:10px 12px;color:#50635c;background:#f4f7f5;border:1px solid #dce5e1;font-size:11px;line-height:1.6}.parser-config-grid{padding:10px 12px 0;background:#f6f8f7}.parser-config-grid+.parser-config-grid{margin-bottom:14px;padding-top:0}.form-help{display:block;margin-top:5px;color:#71817b;font-size:10px}.raw-json-head{width:100%;display:flex;align-items:center;justify-content:space-between;gap:18px}.raw-json-head h2{margin:0;color:#173f36;font-size:17px}.raw-json-head span{display:block;margin-top:5px;color:#6b7c75;font-size:11px}.raw-json-body{height:100%;min-height:280px;display:flex;flex-direction:column}.raw-json-body>p{margin:0 0 12px;padding:10px 12px;color:#52665f;background:#f4f7f5;border:1px solid #dce5e1;font-size:11px;line-height:1.65}.raw-json-body>p code{color:#235c4d}.raw-json-body pre{min-height:0;flex:1;margin:0;padding:16px;overflow:auto;color:#d8e6e1;background:#19312b;border-radius:4px;font:11px/1.65 Consolas,"SFMono-Regular",monospace;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:1400px){.rule-flow{flex-wrap:wrap}.rule-flow i{display:none}.rule-flow>span{flex:1 1 40%!important}}
.lims-catalog{--space-xs:4px;--space-sm:8px;--space-md:12px;--space-lg:16px;--space-xl:24px;height:100%;min-width:0;color:#263731;background:#edf0ee;overflow:hidden}.module-header{height:64px;padding:0 var(--space-xl);display:flex;align-items:center;background:#fff;border-bottom:1px solid #d5ddda}.module-title{display:flex;align-items:center;gap:var(--space-md)}.module-title>svg{width:22px;color:#286958}.module-title strong,.module-title small{display:block}.module-title strong{color:#173f36;font-size:14px}.module-title small{margin-top:3px;color:#6b7c75;font-size:10px}.header-actions{margin-left:auto;display:flex;gap:var(--space-sm)}.header-actions .el-button{margin:0}.catalog-main{height:calc(100% - 64px);display:grid;grid-template-columns:380px minmax(0,1fr)}.field-index{min-height:0;padding:18px 14px 0;display:flex;flex-direction:column;background:#fff;border-right:1px solid #d5ddda}.index-head{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:14px}.index-head h1{margin:0;color:#173f36;font-size:18px}.index-head span{color:#6d7e78;font-size:11px}.field-list{min-height:0;flex:1;overflow:auto;margin-top:var(--space-md);padding-bottom:var(--space-lg)}.field-list section{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 7px}.field-list section h2{grid-column:1/-1;margin:14px 8px 1px;display:flex;justify-content:space-between;color:#53675f;font-size:12px}.field-list section h2 span{font-weight:400}.field-list button{width:100%;min-width:0;min-height:44px;padding:6px var(--space-sm);display:grid;grid-template-columns:minmax(0,1fr) 8px;align-items:center;gap:6px;border:1px solid #e4e9e6;border-radius:4px;background:#fff;text-align:left;cursor:pointer;transition:background-color 180ms ease-out,border-color 180ms ease-out}.field-list button:hover{background:#f1f6f4;border-color:#b8cbc4}.field-list button.selected{background:#e5f0ed;border-color:#4f8b7b}.field-list b,.field-list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.field-list b{font-size:12px}.field-list small{margin-top:3px;color:#687a73;font-size:10px}.field-state{width:7px;height:7px;border-radius:50%;background:#49a36e}.field-state.disabled{background:#9aa6a1}.field-workspace{min-width:0;overflow:auto;padding:var(--space-xl) 28px}.workspace-head,.rules-head,.preview-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.workspace-head>div:last-child{display:flex;gap:var(--space-sm)}.workspace-head span,.rules-head span,.preview-head span{color:#6b7c75;font-size:11px}.workspace-head h1{margin:6px 0 0;color:#173f36;font-size:24px}.result-preview-band,.definition-band,.rules-band{margin-top:20px;background:#fff;border:1px solid #d7dfdb}.result-preview-band{min-height:118px}.preview-head{padding:var(--space-lg) 20px;border-bottom:1px solid #e2e7e4}.preview-head h2,.definition-band h2,.rules-head h2{margin:0 0 var(--space-lg);color:#234c41;font-size:16px}.preview-head h2,.rules-head h2{margin-bottom:var(--space-xs)}.preview-empty{min-height:68px;padding:var(--space-xl);display:grid;place-items:center;color:#6b7c75;font-size:12px}.preview-value{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#173f36;font-weight:600}.preview-context b,.preview-context small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.preview-context b{font-size:12px;font-weight:500}.preview-context small{margin-top:2px;color:#708079;font-size:10px}.definition-band{padding:20px}.form-grid{display:grid;gap:var(--space-md)}.form-grid.two{grid-template-columns:1fr 1fr}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.form-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.database-row{margin-top:var(--space-xs);padding-top:14px;border-top:1px solid #e4e9e6}.rules-band{padding:0;overflow-x:auto}.rules-head{padding:18px 20px;border-bottom:1px solid #e2e7e4}.rules-band code{color:#31594e}.empty-state{height:100%;display:grid;place-content:center;text-align:center;color:#708079}.empty-state svg{width:36px;margin:auto}.empty-state h2{font-size:18px}.el-select,.el-input-number{width:100%}@media(max-width:1400px){.catalog-main{grid-template-columns:360px minmax(0,1fr)}.field-workspace{padding:var(--space-xl)}.form-grid.four{grid-template-columns:1fr 1fr}}@media(prefers-reduced-motion:reduce){.field-list button{transition:none}}
.chapter-entry{min-width:0}.field-list .chapter-row{--indent:calc(var(--chapter-depth) * 16px);width:100%;height:34px;min-height:34px;padding:0 8px 0 calc(4px + var(--indent));display:grid;grid-template-columns:14px minmax(34px,auto) minmax(0,1fr) 24px;align-items:center;gap:6px;border:0;border-bottom:1px solid #edf0ee;border-radius:0;background:transparent;color:#3d554d;text-align:left;cursor:pointer}.field-list .chapter-row:hover{background:#f1f6f4;border-color:#edf0ee}.chapter-row.muted{opacity:.58}.chapter-row b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;font-weight:600}.chapter-caret{display:block;color:#71827b;font-size:18px;line-height:1;transform:rotate(0deg);transition:transform 160ms ease-out}.chapter-caret.open{transform:rotate(90deg)}.chapter-code{color:#697a74;font:10px/1.2 Consolas,"SFMono-Regular",monospace}.chapter-count{color:#84928d;font-size:10px;text-align:right}.chapter-fields{margin:4px 0 8px;padding-left:calc(20px + var(--chapter-depth) * 16px);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 7px}.field-list .field-item{width:100%;min-width:0;min-height:44px;padding:6px var(--space-sm);display:grid;grid-template-columns:minmax(0,1fr) 8px;align-items:center;gap:6px;border:1px solid #e4e9e6;border-radius:4px;background:#fff;text-align:left;cursor:pointer}.field-list .field-item:hover{background:#f1f6f4;border-color:#b8cbc4}.field-list .field-item.selected{background:#e5f0ed;border-color:#4f8b7b}.unmapped-fields{margin-top:14px;padding-top:6px;border-top:1px solid #dde4e1}.field-list .unmapped-fields h2{margin-top:4px}.field-list .el-empty{padding:28px 0}
.preview-actions{display:flex;align-items:center;gap:8px}.preview-instance-select{width:360px}.preview-option{display:grid;gap:2px;line-height:1.25}.preview-option b{max-width:310px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#31463f;font-size:12px;font-weight:500}.preview-option small{color:#71817b;font-size:10px}@media(max-width:1200px){.preview-actions{width:100%;align-items:stretch}.preview-instance-select{min-width:0;flex:1}.preview-head{align-items:stretch;flex-direction:column}}
@media(prefers-reduced-motion:reduce){.chapter-caret{transition:none}}
</style>
