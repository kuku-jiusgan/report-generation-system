<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { adminApi, type LimsRuleMetadata, type StandardField, type SystemFieldGroup, type SystemFieldRule } from './admin-api'
import SystemAiRuleEditor from './SystemAiRuleEditor.vue'
import SystemContextVariables, { type ContextVariable } from './SystemContextVariables.vue'
import ExcelWorkbookLocation from './ExcelWorkbookLocation.vue'
import ExcelFieldRuleEditor from './ExcelFieldRuleEditor.vue'
import ProtocolFieldRuleEditor from './ProtocolFieldRuleEditor.vue'
import LimsFieldRuleEditor from './LimsFieldRuleEditor.vue'
import KeyedLookupRuleEditor from './KeyedLookupRuleEditor.vue'
import { shouldResetProtocolConfig, sourceTypes, transforms } from './fieldRuleOptions'
type CatalogRule = SystemFieldRule
const rule = defineModel<Partial<CatalogRule>>('rule', { required: true })
const config = defineModel<Record<string, unknown>>('config', { required: true })
defineProps<{ fields: StandardField[]; groups: SystemFieldGroup[]; fieldCode: string; origin: string }>()
const emit = defineEmits<{ 'group-updated': [group: SystemFieldGroup]; 'mapping-dirty': [dirty: boolean] }>()
const limsMetadata = ref<LimsRuleMetadata>()
const limsMetadataLoading = ref(false)
const limsMetadataError = ref('')
const availableTransforms = computed(() => rule.value.sourceType === 'LIMS' ? limsMetadata.value?.transforms || [] : transforms)
const limsConfigError = computed(() => {
  const extractionType = String(config.value.extractionType || '')
  if (!limsMetadata.value || !extractionType) return ''
  return limsMetadata.value.extractionTypes.some(item => item.value === extractionType)
    ? ''
    : `当前规则使用已停用的 LIMS 提取方式：${extractionType}，请重新选择提取方式`
})
const calculatedVariables = computed<ContextVariable[]>({
  get: () => Array.isArray(config.value.contextVariables) ? config.value.contextVariables as ContextVariable[] : [],
  set: value => { config.value.contextVariables = value },
})
function initializeLimsConfig() {
  if (!limsMetadata.value) return
  const types = limsMetadata.value.extractionTypes
  if (!config.value.extractionType && types[0]) {
    config.value = { ...types[0].defaultConfig }
  }
}
async function loadLimsMetadata() {
  if (limsMetadata.value) return initializeLimsConfig()
  if (limsMetadataLoading.value) return
  limsMetadataLoading.value = true
  limsMetadataError.value = ''
  try {
    limsMetadata.value = await adminApi.limsRuleMetadata()
    initializeLimsConfig()
  } catch {
    limsMetadataError.value = 'LIMS 提取规则配置加载失败，请刷新后重试'
  } finally {
    limsMetadataLoading.value = false
  }
}
watch(() => rule.value.sourceType, (sourceType, previous) => {
  emit('mapping-dirty', false)
  if (shouldResetProtocolConfig(sourceType, previous)) config.value = {}
  if (sourceType === 'LIMS') void loadLimsMetadata()
  if (sourceType !== 'LIMS' && rule.value.transform === 'REGEX_REPLACE') rule.value.transform = 'TRIM'
}, { immediate: true })
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
          <KeyedLookupRuleEditor v-model="config" :fields="fields" :field-code="fieldCode" />
          <template v-if="String(config.operation || '').toUpperCase() !== 'KEYED_LOOKUP'">
            <el-form-item v-if="config.textTemplate" label="上下文变量">
              <SystemContextVariables v-model="calculatedVariables" :fields="fields" :groups="groups" />
              <small class="form-help">成组字段（一个字段多条取值）必须在这里声明取值方式，否则模板拿到的是整个列表。</small>
            </el-form-item>
          </template>
        </template>
        <el-skeleton v-if="rule.sourceType === 'LIMS' && limsMetadataLoading" :rows="3" animated />
        <div v-else-if="rule.sourceType === 'LIMS' && limsMetadataError" class="rule-load-error">
          <el-alert type="error" :title="limsMetadataError" show-icon :closable="false" />
          <el-button @click="loadLimsMetadata">重新加载</el-button>
        </div>
        <el-alert v-else-if="rule.sourceType === 'LIMS' && limsConfigError" type="error" :title="limsConfigError" show-icon :closable="false" />
        <LimsFieldRuleEditor v-if="rule.sourceType === 'LIMS' && limsMetadata" v-model="config" :metadata="limsMetadata" :transform="rule.transform || 'TRIM'" />
        <div class="form-grid two"><el-form-item label="结果转换"><el-select v-model="rule.transform"><el-option v-for="item in availableTransforms" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="状态"><el-switch v-model="rule.enabled" active-text="启用" inactive-text="停用" /></el-form-item></div>
      </el-form>
</template>
<style scoped>
.form-grid{display:grid;gap:16px}.form-grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.rule-origin-note{margin-bottom:14px;padding:10px 12px;color:#50635c;background:#f4f7fb;border:1px solid #dce5e1;font-size:12px;line-height:1.6}.rule-load-error{display:flex;align-items:center;gap:12px;margin-bottom:16px}.rule-load-error .el-alert{min-width:0;flex:1}.form-help{display:block;margin-top:5px;color:#52635c;font-size:12px;line-height:1.6}@media(max-width:640px){.form-grid.two,.form-grid.three{grid-template-columns:1fr}.rule-load-error{align-items:stretch;flex-direction:column}}
</style>
