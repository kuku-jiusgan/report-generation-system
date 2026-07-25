<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Coin, Delete, EditPen, Plus, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi, type LimsExtractionRule, type StandardField, type StandardFieldPreview } from "./admin-api";

const loading = ref(false);
const saving = ref(false);
const fields = ref<StandardField[]>([]);
const selected = ref<StandardField>();
const draft = ref<Partial<StandardField>>();
const rules = ref<LimsExtractionRule[]>([]);
const search = ref("");
const ruleDialog = ref(false);
const ruleDraft = ref<Partial<LimsExtractionRule>>();
const preview = ref<StandardFieldPreview>();
const previewLoading = ref(false);
let previewRequest = 0;

const dataTypes = [
  { value: "string", label: "文本" }, { value: "decimal", label: "数值" },
  { value: "date", label: "日期" }, { value: "richText", label: "富文本" },
  { value: "boolean", label: "布尔值" }, { value: "image", label: "图片" },
];
const sourceTypes = [
  { value: "NORMALIZED_PATH", label: "已有标准数据路径" },
  { value: "RAW_UNIT_FIELD", label: "原始结构化单元字段" },
  { value: "RICH_TEXT_REGEX", label: "富文本正则提取" },
  { value: "HTML_TABLE_COLUMN", label: "HTML 表格列" },
];
const transforms = [
  { value: "TRIM", label: "去除首尾空白" }, { value: "NUMBER", label: "转换为数值" },
  { value: "DATE", label: "转换为日期" }, { value: "UPPER", label: "转为大写" },
  { value: "LOWER", label: "转为小写" },
];
const unitTypes = ["Sample", "Standard", "Equipment", "Chromatogram", "Reagent", "Weighing"];
const sourceTypeLabel = (value: string) => sourceTypes.find((item) => item.value === value)?.label || value;

const filtered = computed(() => {
  const keyword = search.value.trim().toLowerCase();
  return fields.value.filter((item) => !keyword || `${item.label} ${item.fieldCode} ${item.groupCode}`.toLowerCase().includes(keyword));
});
const grouped = computed(() => {
  const result = new Map<string, StandardField[]>();
  for (const item of filtered.value) {
    if (!result.has(item.groupCode)) result.set(item.groupCode, []);
    result.get(item.groupCode)!.push(item);
  }
  return Array.from(result, ([code, items]) => ({ code, items }));
});

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } }; message?: string };
  return value.response?.data?.detail || value.message || "操作失败";
}
async function loadFields(preferred?: string) {
  loading.value = true;
  try {
    fields.value = await adminApi.allStandardFields();
    const target = fields.value.find((item) => item.fieldCode === (preferred || selected.value?.fieldCode)) || fields.value[0];
    if (target) await selectField(target);
  } catch (error) { ElMessage.error(errorText(error)); }
  finally { loading.value = false; }
}
async function selectField(field: StandardField) {
  selected.value = field;
  draft.value = JSON.parse(JSON.stringify(field));
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
    const result = await adminApi.standardFieldPreview(fieldCode);
    if (requestId === previewRequest) preview.value = result;
  } catch (error) {
    if (requestId === previewRequest) preview.value = undefined;
    ElMessage.error(errorText(error));
  } finally {
    if (requestId === previewRequest) previewLoading.value = false;
  }
}
function previewValue(value: unknown) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}
function evidenceLabel(evidence: Record<string, unknown>, fallback: string) {
  const section = evidence.sectionPath || evidence.section || evidence.chapterPath;
  if (Array.isArray(section)) return section.join(" / ");
  return String(section || fallback || "标准记录");
}
function newField() {
  selected.value = undefined;
  rules.value = [];
  preview.value = undefined;
  draft.value = {
    fieldCode: "", label: "", groupCode: "project", collectionCode: "project",
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
  ruleDraft.value = rule ? JSON.parse(JSON.stringify(rule)) : {
    fieldCode: draft.value.fieldCode, name: "新提取规则", sourceType: "NORMALIZED_PATH",
    sourceUnitType: "", sourcePath: draft.value.legacyJsonPath || "", sectionPattern: "",
    headerPattern: "", valuePattern: "", transform: "TRIM", priority: (rules.value.length + 1) * 10,
    config: {}, enabled: true,
  };
  ruleDialog.value = true;
}
async function saveRule() {
  if (!ruleDraft.value?.name?.trim() || !selected.value) return ElMessage.warning("规则名称不能为空");
  try {
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
          <section v-for="group in grouped" :key="group.code">
            <h2>{{ group.code }}<span>{{ group.items.length }}</span></h2>
            <button v-for="item in group.items" :key="item.fieldCode" :class="{ selected: selected?.fieldCode === item.fieldCode }" @click="selectField(item)">
              <span><b>{{ item.label }}</b><small>{{ item.fieldCode }}</small></span>
              <span class="field-state" :class="{ disabled: !item.enabled }" :title="item.enabled ? '已启用' : '已停用'" />
            </button>
          </section>
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
                <span v-if="preview?.storageSupported && preview.total">共 {{ preview.total }} 条，显示最近 {{ preview.items.length }} 条</span>
                <span v-else>最近解析的 LIMS 标准数据</span>
              </div>
              <el-button :icon="Refresh" :disabled="!selected" @click="loadPreview(selected?.fieldCode)">刷新预览</el-button>
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
            <div class="rules-head"><div><h2>提取规则</h2><span>按优先级从小到大执行，首个有效结果写入标准字段</span></div><el-button type="primary" plain :icon="Plus" @click="editRule()">新增规则</el-button></div>
            <el-table :data="rules" row-key="id">
              <el-table-column prop="priority" label="优先级" width="90" />
              <el-table-column prop="name" label="规则名称" min-width="180" />
              <el-table-column label="来源方式" min-width="180"><template #default="scope">{{ sourceTypeLabel(scope.row.sourceType) }}</template></el-table-column>
              <el-table-column prop="sourcePath" label="来源字段/列" min-width="220"><template #default="scope"><code>{{ scope.row.sourcePath || '-' }}</code></template></el-table-column>
              <el-table-column label="状态" width="90"><template #default="scope"><el-tag size="small" :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
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
          <el-form-item label="来源方式"><el-select v-model="ruleDraft.sourceType"><el-option v-for="item in sourceTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="优先级"><el-input-number v-model="ruleDraft.priority" :min="1" controls-position="right" /></el-form-item>
        </div>
        <el-form-item v-if="ruleDraft.sourceType === 'RAW_UNIT_FIELD'" label="LIMS 单元类型"><el-select v-model="ruleDraft.sourceUnitType"><el-option v-for="item in unitTypes" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item v-if="['NORMALIZED_PATH','RAW_UNIT_FIELD'].includes(ruleDraft.sourceType || '')" :label="ruleDraft.sourceType === 'NORMALIZED_PATH' ? '标准数据来源路径' : '原始 JSON 字段路径'"><el-input v-model="ruleDraft.sourcePath" placeholder="例如 ext$.mtlname" /></el-form-item>
        <template v-if="['RICH_TEXT_REGEX','HTML_TABLE_COLUMN'].includes(ruleDraft.sourceType || '')">
          <el-form-item label="章节路径匹配"><el-input v-model="ruleDraft.sectionPattern" placeholder="例如 实验材料|实验过程" /></el-form-item>
          <el-form-item v-if="ruleDraft.sourceType === 'HTML_TABLE_COLUMN'" label="表头匹配"><el-input v-model="ruleDraft.headerPattern" placeholder="例如 名称.*批号" /></el-form-item>
          <el-form-item v-if="ruleDraft.sourceType === 'HTML_TABLE_COLUMN'" label="取值列标题"><el-input v-model="ruleDraft.sourcePath" placeholder="例如 批号|批次号" /></el-form-item>
          <el-form-item label="取值正则"><el-input v-model="ruleDraft.valuePattern" placeholder="可留空；存在捕获组时取第一个捕获组" /></el-form-item>
        </template>
        <div class="form-grid two"><el-form-item label="结果转换"><el-select v-model="ruleDraft.transform"><el-option v-for="item in transforms" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="状态"><el-switch v-model="ruleDraft.enabled" active-text="启用" inactive-text="停用" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="ruleDialog = false">取消</el-button><el-button type="primary" @click="saveRule">保存规则</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.lims-catalog{--space-xs:4px;--space-sm:8px;--space-md:12px;--space-lg:16px;--space-xl:24px;height:100%;min-width:0;color:#263731;background:#edf0ee;overflow:hidden}.module-header{height:64px;padding:0 var(--space-xl);display:flex;align-items:center;background:#fff;border-bottom:1px solid #d5ddda}.module-title{display:flex;align-items:center;gap:var(--space-md)}.module-title>svg{width:22px;color:#286958}.module-title strong,.module-title small{display:block}.module-title strong{color:#173f36;font-size:14px}.module-title small{margin-top:3px;color:#6b7c75;font-size:10px}.header-actions{margin-left:auto;display:flex;gap:var(--space-sm)}.header-actions .el-button{margin:0}.catalog-main{height:calc(100% - 64px);display:grid;grid-template-columns:380px minmax(0,1fr)}.field-index{min-height:0;padding:18px 14px 0;display:flex;flex-direction:column;background:#fff;border-right:1px solid #d5ddda}.index-head{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:14px}.index-head h1{margin:0;color:#173f36;font-size:18px}.index-head span{color:#6d7e78;font-size:11px}.field-list{min-height:0;flex:1;overflow:auto;margin-top:var(--space-md);padding-bottom:var(--space-lg)}.field-list section{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 7px}.field-list section h2{grid-column:1/-1;margin:14px 8px 1px;display:flex;justify-content:space-between;color:#53675f;font-size:12px}.field-list section h2 span{font-weight:400}.field-list button{width:100%;min-width:0;min-height:44px;padding:6px var(--space-sm);display:grid;grid-template-columns:minmax(0,1fr) 8px;align-items:center;gap:6px;border:1px solid #e4e9e6;border-radius:4px;background:#fff;text-align:left;cursor:pointer;transition:background-color 180ms ease-out,border-color 180ms ease-out}.field-list button:hover{background:#f1f6f4;border-color:#b8cbc4}.field-list button.selected{background:#e5f0ed;border-color:#4f8b7b}.field-list b,.field-list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.field-list b{font-size:12px}.field-list small{margin-top:3px;color:#687a73;font-size:10px}.field-state{width:7px;height:7px;border-radius:50%;background:#49a36e}.field-state.disabled{background:#9aa6a1}.field-workspace{min-width:0;overflow:auto;padding:var(--space-xl) 28px}.workspace-head,.rules-head,.preview-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.workspace-head>div:last-child{display:flex;gap:var(--space-sm)}.workspace-head span,.rules-head span,.preview-head span{color:#6b7c75;font-size:11px}.workspace-head h1{margin:6px 0 0;color:#173f36;font-size:24px}.result-preview-band,.definition-band,.rules-band{margin-top:20px;background:#fff;border:1px solid #d7dfdb}.result-preview-band{min-height:118px}.preview-head{padding:var(--space-lg) 20px;border-bottom:1px solid #e2e7e4}.preview-head h2,.definition-band h2,.rules-head h2{margin:0 0 var(--space-lg);color:#234c41;font-size:16px}.preview-head h2,.rules-head h2{margin-bottom:var(--space-xs)}.preview-empty{min-height:68px;padding:var(--space-xl);display:grid;place-items:center;color:#6b7c75;font-size:12px}.preview-value{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#173f36;font-weight:600}.preview-context b,.preview-context small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.preview-context b{font-size:12px;font-weight:500}.preview-context small{margin-top:2px;color:#708079;font-size:10px}.definition-band{padding:20px}.form-grid{display:grid;gap:var(--space-md)}.form-grid.two{grid-template-columns:1fr 1fr}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.form-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.database-row{margin-top:var(--space-xs);padding-top:14px;border-top:1px solid #e4e9e6}.rules-band{padding:0;overflow-x:auto}.rules-head{padding:18px 20px;border-bottom:1px solid #e2e7e4}.rules-band code{color:#31594e}.empty-state{height:100%;display:grid;place-content:center;text-align:center;color:#708079}.empty-state svg{width:36px;margin:auto}.empty-state h2{font-size:18px}.el-select,.el-input-number{width:100%}@media(max-width:1400px){.catalog-main{grid-template-columns:360px minmax(0,1fr)}.field-workspace{padding:var(--space-xl)}.form-grid.four{grid-template-columns:1fr 1fr}}@media(prefers-reduced-motion:reduce){.field-list button{transition:none}}
</style>
