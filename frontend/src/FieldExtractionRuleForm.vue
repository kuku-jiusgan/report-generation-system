<script setup lang="ts">
import { computed, watch } from 'vue'
import type { LimsExtractionRule, StandardField, SystemFieldGroup, SystemFieldRule } from './admin-api'
import SystemAiRuleEditor from './SystemAiRuleEditor.vue'
import SystemContextVariables, { type ContextVariable } from './SystemContextVariables.vue'
import ExcelWorkbookLocation from './ExcelWorkbookLocation.vue'
import ExcelFieldRuleEditor from './ExcelFieldRuleEditor.vue'
import ProtocolFieldRuleEditor from './ProtocolFieldRuleEditor.vue'
import { sourceTypes, limsExtractionTypes, transforms, parsers, parserProfiles, unitTypes } from './fieldRuleOptions'
type CatalogRule = Omit<LimsExtractionRule, 'sourceType'> & SystemFieldRule
const rule = defineModel<Partial<CatalogRule>>('rule', { required: true })
const config = defineModel<Record<string, unknown>>('config', { required: true })
defineProps<{ fields: StandardField[]; groups: SystemFieldGroup[]; fieldCode: string; origin: string }>()
const emit = defineEmits<{ 'group-updated': [group: SystemFieldGroup]; 'mapping-dirty': [dirty: boolean] }>()
const calculatedVariables = computed<ContextVariable[]>({
  get: () => Array.isArray(config.value.contextVariables) ? config.value.contextVariables as ContextVariable[] : [],
  set: value => { config.value.contextVariables = value },
})
watch(() => rule.value.sourceType, (sourceType, previous) => {
  emit('mapping-dirty', false)
  if (sourceType === 'PROTOCOL' || previous === 'PROTOCOL') config.value = {}
})
</script>
<template>
      <el-form v-if="rule" label-position="top">
        <div class="form-grid three">
          <el-form-item label="规则名称"><el-input v-model="rule.name" /></el-form-item>
          <el-form-item label="提取方式"><el-select v-model="rule.sourceType"><el-option v-for="item in sourceTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        </div>
        <div class="rule-origin-note"><b>数据来源：</b>{{ origin }}</div>
        <ProtocolFieldRuleEditor v-if="rule.sourceType === 'PROTOCOL'" v-model="config" :groups="groups" :field-code="fieldCode" :transform="rule.transform || 'TRIM'" @group-updated="emit('group-updated', $event)" @mapping-dirty="emit('mapping-dirty', $event)" />
        <template v-if="rule.sourceType === 'PDF'">
          <el-form-item label="PDF 字段路径或字段编码"><el-input v-model="config.sourcePath" placeholder="默认使用当前系统字段编码" /></el-form-item>
          <el-form-item label="PDF 取值正则（可选）"><el-input v-model="config.valuePattern" /></el-form-item>
        </template>
        <template v-if="rule.sourceType === 'EXCEL'">
          <ExcelFieldRuleEditor v-model="config" :fields="fields" />
          <ExcelWorkbookLocation :config="config" />
        </template>
        <template v-if="rule.sourceType === 'AI'">
          <SystemAiRuleEditor v-model="config" :fields="fields" :groups="groups" :field-code="fieldCode" />
        </template>
        <template v-if="rule.sourceType === 'CALCULATED'">
          <el-form-item label="依赖系统字段"><el-select v-model="config.dependencies" multiple filterable><el-option v-for="item in fields" :key="item.fieldCode" :label="`${item.label} · ${item.fieldCode}`" :value="item.fieldCode" /></el-select></el-form-item>
          <el-form-item label="计算表达式"><el-input v-model="config.expression" placeholder="例如 {sample.weight} / {sample.volume}" /></el-form-item>
          <el-form-item label="文本拼接模板"><el-input v-model="config.textTemplate" type="textarea" :rows="4" placeholder="例如 {sample.name}（批号：{sample.batchNo}）" /><small class="form-help">计算表达式和文本拼接模板二选一。文本模板用 {系统字段编码} 引用下面的上下文变量。</small></el-form-item>
          <el-form-item v-if="config.textTemplate" label="上下文变量">
            <SystemContextVariables v-model="calculatedVariables" :fields="fields" :groups="groups" />
            <small class="form-help">成组字段（一个字段多条取值）必须在这里声明取值方式，否则模板拿到的是整个列表。</small>
          </el-form-item>
        </template>
        <template v-if="rule.sourceType === 'LIMS'">
        <el-form-item label="LIMS 解析方式"><el-select v-model="config.extractionType"><el-option v-for="item in limsExtractionTypes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <div class="form-grid three parser-config-grid">
          <el-form-item label="上游解析器">
            <el-select v-model="config.parser"><el-option v-for="item in parsers" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          </el-form-item>
          <el-form-item label="解析配置">
            <el-select v-model="config.parserProfile" filterable allow-create clearable placeholder="选择或输入解析配置">
              <el-option v-for="item in parserProfiles" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="原始数据库字段"><el-input v-model="config.inputField" placeholder="例如 UNITBODY" /></el-form-item>
        </div>
        <div class="form-grid two parser-config-grid">
          <el-form-item label="输出标准集合"><el-input v-model="config.outputCollection" placeholder="例如 systemSuitability" /></el-form-item>
          <el-form-item label="输出 JSON 属性"><el-input v-model="config.outputField" placeholder="例如 peakArea" /></el-form-item>
        </div>
        <el-form-item v-if="config.extractionType === 'RAW_UNIT_FIELD'" label="LIMS TYPE 筛选值"><el-select v-model="rule.sourceUnitType"><el-option v-for="item in unitTypes" :key="item" :label="item" :value="item" /></el-select><small class="form-help">对应 LIMS SQL 查询结果中的 TYPE 字段。</small></el-form-item>
        <el-form-item v-if="['NORMALIZED_PATH','RAW_UNIT_FIELD'].includes(String(config.extractionType || ''))" :label="config.extractionType === 'RAW_UNIT_FIELD' ? 'UNITBODY.data[] 内的字段路径（不是正则）' : '标准 JSONPath（不是正则）'"><el-input v-model="rule.sourcePath" placeholder="例如 $.samples[*].sampleName" /></el-form-item>
        <template v-if="['RICH_TEXT_REGEX','HTML_TABLE_COLUMN'].includes(String(config.extractionType || '')) || config.parser === 'HTML_TABLE_GRID'">
          <el-form-item label="章节路径正则"><el-input v-model="rule.sectionPattern" placeholder="例如 实验材料|实验过程" /></el-form-item>
          <el-form-item v-if="config.extractionType === 'HTML_TABLE_COLUMN' || config.parser === 'HTML_TABLE_GRID'" label="表头特征正则"><el-input v-model="rule.headerPattern" placeholder="例如 No\.? .*保留时间.*峰面积" /></el-form-item>
          <el-form-item v-if="config.extractionType === 'HTML_TABLE_COLUMN'" label="取值列标题正则"><el-input v-model="rule.sourcePath" placeholder="例如 批号|批次号" /></el-form-item>
          <el-form-item label="取值正则（可选）"><el-input v-model="rule.valuePattern" placeholder="存在捕获组时取第一个捕获组；否则取完整匹配" /></el-form-item>
          <el-form-item v-if="config.parser === 'HTML_TABLE_GRID' || config.extractionType === 'HTML_TABLE_COLUMN'" label="数据行过滤正则（可选）"><el-input v-model="config.rowPattern" placeholder="例如 验证项目=.*系统适用性" /></el-form-item>
        </template>
        </template>
        <div class="form-grid two"><el-form-item label="结果转换"><el-select v-model="rule.transform"><el-option v-for="item in transforms" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="状态"><el-switch v-model="rule.enabled" active-text="启用" inactive-text="停用" /></el-form-item></div>
      </el-form>
</template>
<style scoped>
.form-grid{display:grid;gap:16px}.form-grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.rule-origin-note{margin-bottom:14px;padding:10px 12px;color:#50635c;background:#f4f7fb;border:1px solid #dce5e1;font-size:12px;line-height:1.6}.parser-config-grid{padding:10px 12px 0;background:#f7f9fc}.form-help{display:block;margin-top:5px;color:#52635c;font-size:12px;line-height:1.6}@media(max-width:640px){.form-grid.two,.form-grid.three{grid-template-columns:1fr}}
</style>
