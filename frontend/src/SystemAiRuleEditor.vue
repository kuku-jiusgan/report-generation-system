<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type StandardField, type StandardFieldPreview } from './admin-api'
import SystemContextVariables, { type ContextVariable } from './SystemContextVariables.vue'

type Variable = ContextVariable

const props = defineProps<{ fields: StandardField[]; groups?: Array<{ groupCode: string; label: string; fields: Array<{ fieldCode: string }> }> }>()
const config = defineModel<Record<string, any>>({ required: true })
const testing = ref(false)
const testOutput = ref('')
const recordsLoading = ref(false)
const recordOptions = ref<NonNullable<StandardFieldPreview['options']>>([])
const selectedInstanceIds = ref<string[]>([])
const variables = computed<Variable[]>({
  get: () => Array.isArray(config.value.contextVariables) ? config.value.contextVariables : [],
  set: (value) => { config.value.contextVariables = value },
})
const referenced = computed(() => Array.from(
  String(config.value.promptTemplate || '').matchAll(/\{\{([^{}]+)\}\}/g), (match) => match[1].trim(),
))
function contextCode(variable: Variable) {
  return variable.groupCode || variable.fieldCode || ''
}
const preview = computed(() => {
  let result = String(config.value.promptTemplate || '')
  variables.value.forEach((item) => {
    const code = contextCode(item)
    const value = item.previewValue || item.defaultValue || `【${code}】`
    result = result.replaceAll(`{{${code}}}`, value)
  })
  return result
})

function insertVariable(code: string) {
  if (!code) return
  const prompt = String(config.value.promptTemplate || '')
  config.value.promptTemplate = `${prompt}${prompt ? '\n' : ''}{{${code}}}`
}
function previewForVariable(variable: Variable, limit: number) {
  if (variable.groupCode) return adminApi.fieldGroupPreview(variable.groupCode, limit, selectedInstanceIds.value)
  if (variable.fieldCode) return adminApi.standardFieldPreview(variable.fieldCode, limit, selectedInstanceIds.value)
  return undefined
}
function previewValue(variable: Variable, items: StandardFieldPreview['items']) {
  if (variable.groupCode) {
    const values = items.map((item) => item.value)
    return values.length === 1 ? JSON.stringify(values[0], null, 2) : JSON.stringify(values, null, 2)
  }
  const raw = items.flatMap((item) => Array.isArray(item.value) ? item.value : [item.value])
  const values = raw.filter((value) => value !== null && value !== undefined && String(value).trim())
  if (!values.length) return ''
  const unique = Array.from(new Set(values.map(String)))
  if (variable.mode === 'COUNT_UNIQUE') return String(unique.length)
  const suffix = variable.suffix || ''
  return variable.mode === 'FIRST'
    ? `${unique[0]}${suffix}`
    : unique.map((item) => `${item}${suffix}`).join(variable.separator || '、')
}
async function loadRecentRecords() {
  recordsLoading.value = true
  try {
    for (const variable of variables.value) {
      const result = previewForVariable(variable, 12)
      if (!result) continue
      const preview = await result
      if (preview.options?.length) {
        recordOptions.value = preview.options
        break
      }
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '最近导入记录加载失败')
  } finally { recordsLoading.value = false }
}
async function fieldPreviewValue(variable: Variable) {
  const preview = previewForVariable(variable, 50)
  if (!preview) return ''
  const result = await preview
  const value = previewValue(variable, result.items)
  if (value || variable.groupCode) return value || variable.defaultValue || ''
  const rules = await adminApi.systemFieldRules(variable.fieldCode!)
  return String(rules.find((rule) => rule.sourceType === 'FIXED' && rule.enabled)?.config?.value || variable.defaultValue || '')
}
async function importSelectedRecords() {
  if (!selectedInstanceIds.value.length) return ElMessage.warning('请先选择实验记录')
  recordsLoading.value = true
  try {
    const resolved = await Promise.all(variables.value.map(fieldPreviewValue))
    variables.value.forEach((variable, index) => { variable.previewValue = resolved[index] })
    ElMessage.success('已导入所选实验记录的真实字段值')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '上下文变量导入失败')
  } finally { recordsLoading.value = false }
}
async function testGeneration() {
  testing.value = true
  testOutput.value = ''
  try {
    const values = Object.fromEntries(variables.value.map((item) => {
      const raw = item.previewValue || item.defaultValue
      const code = contextCode(item)
      if (!item.groupCode || !raw) return [code, raw]
      try { return [item.groupCode, JSON.parse(raw)] } catch { return [item.groupCode, raw] }
    }))
    const result = await adminApi.previewAiRule({ config: config.value, values, execute: true })
    testOutput.value = result.output
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || 'AI 测试生成失败')
  } finally { testing.value = false }
}
onMounted(loadRecentRecords)
</script>

<template>
  <section class="ai-rule-editor">
    <div class="record-importer">
      <el-select v-model="selectedInstanceIds" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择最近导入的实验记录" :loading="recordsLoading">
        <el-option v-for="item in recordOptions" :key="item.instanceId" :value="item.instanceId" :label="`${item.experimentTitle || item.projectName || '未命名实验'} · ${item.instanceId}`" />
      </el-select>
      <el-button :loading="recordsLoading" @click="loadRecentRecords">刷新</el-button>
      <el-button type="primary" :loading="recordsLoading" @click="importSelectedRecords">导入字段值</el-button>
    </div>
    <SystemContextVariables v-model="variables" :fields="props.fields" :groups="props.groups" insert-label="插入" @insert="insertVariable" />
    <el-form-item label="提示词模板"><el-input v-model="config.promptTemplate" type="textarea" :rows="7" placeholder="使用 {{系统字段编码}} 引用上下文" /></el-form-item>
    <p class="referenced-fields">已引用：{{ referenced.join('、') || '暂无' }}</p>
    <el-form-item label="预览用变量值（可选）">
      <div class="preview-values"><el-input v-for="item in variables" :key="contextCode(item)" v-model="item.previewValue" :placeholder="contextCode(item) || '请先选择字段'" /></div>
    </el-form-item>
    <div class="prompt-preview"><b>最终提示词预览</b><pre>{{ preview }}</pre></div>
    <div class="ai-options"><el-input v-model="config.model" placeholder="模型；留空使用系统配置" /><el-input-number v-model="config.maxLength" :min="100" :max="8000" /><el-input-number v-model="config.temperature" :min="0" :max="2" :step="0.1" /></div>
    <div><el-button type="primary" :loading="testing" @click="testGeneration">测试生成</el-button></div>
    <div v-if="testOutput" class="prompt-preview"><b>测试结果</b><pre>{{ testOutput }}</pre></div>
  </section>
</template>

<style scoped>
.ai-rule-editor{display:grid;gap:12px}.ai-editor-head{display:flex;align-items:center;justify-content:space-between}.record-importer{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px}.variable-row{display:grid;grid-template-columns:2fr 1.2fr .7fr 1fr auto auto auto;gap:8px;align-items:center}.referenced-fields{margin:0;color:#64748b;font-size:12px}.preview-values{width:100%;display:grid;gap:8px;grid-template-columns:repeat(2,minmax(0,1fr))}.prompt-preview{padding:12px;border:1px solid #dbe5ee;border-radius:8px;background:#f8fafc}.prompt-preview pre{margin:8px 0 0;white-space:pre-wrap;font:12px/1.6 inherit}.ai-options{display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px}
</style>
