<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowLeft, Coin, Delete, EditPen, Plus, Refresh, Search, Setting } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi, type LimsExtractionRule, type StandardField } from "./admin-api";

defineEmits<{ templates: []; exit: [] }>();

const loading = ref(false);
const saving = ref(false);
const fields = ref<StandardField[]>([]);
const selected = ref<StandardField>();
const draft = ref<Partial<StandardField>>();
const rules = ref<LimsExtractionRule[]>([]);
const search = ref("");
const ruleDialog = ref(false);
const ruleDraft = ref<Partial<LimsExtractionRule>>();

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
  try { rules.value = await adminApi.extractionRules(field.fieldCode); }
  catch (error) { ElMessage.error(errorText(error)); }
}
function newField() {
  selected.value = undefined;
  rules.value = [];
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
    <header class="catalog-header">
      <div class="catalog-brand"><Coin /><div><strong>LIMS 标准字段</strong><small>字段字典与提取规则</small></div></div>
      <div class="header-actions">
        <el-button :icon="ArrowLeft" @click="$emit('exit')">返回报告</el-button>
        <el-button :icon="Setting" @click="$emit('templates')">模板管理</el-button>
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
              <el-tag size="small" :type="item.enabled ? 'success' : 'info'">{{ item.enabled ? '启用' : '停用' }}</el-tag>
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
.lims-catalog{height:100vh;min-width:1120px;color:#263731;background:#edf0ee;overflow:hidden}.catalog-header{height:64px;padding:0 20px;display:flex;align-items:center;color:#fff;background:#123f36;border-bottom:2px solid #b88b49}.catalog-brand{display:flex;align-items:center;gap:11px}.catalog-brand>svg{width:25px}.catalog-brand strong,.catalog-brand small{display:block}.catalog-brand strong{font-size:14px}.catalog-brand small{margin-top:3px;color:#aec3bd;font-size:10px}.header-actions{margin-left:auto;display:flex;gap:7px}.header-actions .el-button{margin:0}.header-actions .el-button:not(.el-button--primary){color:#eef5f3;border-color:#52756d;background:transparent}.catalog-main{height:calc(100vh - 64px);display:grid;grid-template-columns:330px minmax(0,1fr)}.field-index{min-height:0;padding:18px 14px 0;display:flex;flex-direction:column;background:#fff;border-right:1px solid #d5ddda}.index-head{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:14px}.index-head h1{margin:0;color:#173f36;font-size:18px}.index-head span{color:#6d7e78;font-size:11px}.field-list{min-height:0;flex:1;overflow:auto;margin-top:12px;padding-bottom:16px}.field-list section h2{margin:14px 8px 5px;display:flex;justify-content:space-between;color:#53675f;font-size:12px}.field-list section h2 span{font-weight:400}.field-list button{width:100%;min-height:55px;padding:8px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;border:0;border-bottom:1px solid #e8ecea;background:#fff;text-align:left;cursor:pointer}.field-list button:hover,.field-list button.selected{background:#e8f1ee}.field-list b,.field-list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.field-list b{font-size:13px}.field-list small{margin-top:4px;color:#687a73;font-size:11px}.field-workspace{min-width:0;overflow:auto;padding:26px 30px}.workspace-head,.rules-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}.workspace-head>div:last-child{display:flex;gap:8px}.workspace-head span,.rules-head span{color:#6b7c75;font-size:11px}.workspace-head h1{margin:6px 0 0;color:#173f36;font-size:24px}.definition-band,.rules-band{margin-top:20px;padding:20px;background:#fff;border:1px solid #d7dfdb}.definition-band h2,.rules-head h2{margin:0 0 16px;color:#234c41;font-size:16px}.rules-head h2{margin-bottom:4px}.form-grid{display:grid;gap:12px}.form-grid.two{grid-template-columns:1fr 1fr}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.form-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.database-row{margin-top:4px;padding-top:14px;border-top:1px solid #e4e9e6}.rules-band{padding:0}.rules-head{padding:18px 20px;border-bottom:1px solid #e2e7e4}.rules-band code{color:#31594e}.empty-state{height:100%;display:grid;place-content:center;text-align:center;color:#708079}.empty-state svg{width:36px;margin:auto}.empty-state h2{font-size:18px}.el-select,.el-input-number{width:100%}@media(max-width:1300px){.catalog-main{grid-template-columns:290px minmax(0,1fr)}.field-workspace{padding:22px}.form-grid.four{grid-template-columns:1fr 1fr}}@media(prefers-reduced-motion:reduce){.field-list button{transition:none}}
</style>
