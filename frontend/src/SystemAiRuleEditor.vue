<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type GenerationHistoryItem, type ReportAiContext, type StandardField } from './admin-api'
import SystemContextVariables, { type ContextVariable } from './SystemContextVariables.vue'

type Variable = ContextVariable

const props = defineProps<{ fieldCode?: string; fields: StandardField[]; groups?: Array<{ groupCode: string; label: string; fields: Array<{ fieldCode: string }> }> }>()
const config = defineModel<Record<string, any>>({ required: true })
const testing = ref(false)
const testOutput = ref('')
const recordsLoading = ref(false)
const recordOptions = ref<GenerationHistoryItem[]>([])
const selectedGenerationId = ref('')
const contextLoading = ref(false)
const importError = ref('')
const missingVariables = ref<string[]>([])
const importedContext = ref<ReportAiContext>()
const selectedRecordIndex = ref<number>()
const currentRecordOptions = ref<Record<string, unknown>[]>([])
const requiresCurrentRecord = computed(() => variables.value.some((variable) => variable.mode === 'CURRENT_RECORD'))
let contextRequest = 0
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
function formatPromptPreview(prompt: string) {
  const images = new Map<string, number>()
  return prompt.replace(
    /data:image\/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/]+={0,2}(?=$|["'\s,;，；)\]}])/g,
    (dataUrl) => {
      if (!images.has(dataUrl)) images.set(dataUrl, images.size + 1)
      return `[图片 ${images.get(dataUrl)}，将作为视觉输入发送]`
    },
  )
}
const preview = computed(() => {
  let result = String(config.value.promptTemplate || '')
  variables.value.forEach((item) => {
    const code = contextCode(item)
    const value = item.previewValue || item.defaultValue || `【${code}】`
    result = result.replaceAll(`{{${code}}}`, value)
  })
  return formatPromptPreview(result)
})

function insertVariable(code: string) {
  if (!code) return
  const prompt = String(config.value.promptTemplate || '')
  config.value.promptTemplate = `${prompt}${prompt ? '\n' : ''}{{${code}}}`
}
function recordLabel(item: GenerationHistoryItem) {
  const phase = item.generation_context?.phase
  const date = new Date(item.generated_at).toLocaleString('zh-CN', { hour12: false })
  return `${item.title} · ${date}${phase ? ` · ${phase}` : ''}`
}
function currentRecordLabel(record: Record<string, unknown>, index: number) {
  const values = Object.values(record).filter((value) => ['string', 'number'].includes(typeof value))
  return `第 ${index + 1} 条${values.length ? ` · ${values.join('、')}` : ''}`
}
async function loadRecentRecords() {
  recordsLoading.value = true
  importError.value = ''
  try {
    const result = await adminApi.reportHistory({ status: 'SUCCESS', page_size: 50 })
    recordOptions.value = result.items
  } catch (error: any) {
    importError.value = error?.response?.data?.detail || '报告生成记录加载失败，请重试'
  } finally { recordsLoading.value = false }
}
async function importSelectedRecords() {
  const requestId = ++contextRequest
  importedContext.value = undefined
  missingVariables.value = []
  importError.value = ''
  testOutput.value = ''
  variables.value.forEach((variable) => { variable.previewValue = '' })
  if (!selectedGenerationId.value) {
    contextLoading.value = false
    return
  }
  contextLoading.value = true
  try {
    const result = await adminApi.reportAiContext(selectedGenerationId.value, config.value, props.fieldCode, selectedRecordIndex.value)
    if (requestId !== contextRequest) return
    importedContext.value = result
    currentRecordOptions.value = result.records
    missingVariables.value = result.missing
    variables.value.forEach((variable) => { variable.previewValue = result.context[contextCode(variable)] || '' })
  } catch (error: any) {
    if (requestId === contextRequest) importError.value = error?.response?.data?.detail || '报告变量加载失败，请重试'
  } finally { if (requestId === contextRequest) contextLoading.value = false }
}
async function testGeneration() {
  testing.value = true
  testOutput.value = ''
  try {
    const values = Object.fromEntries(variables.value.map((item) => {
      const raw = item.previewValue || item.defaultValue
      const code = contextCode(item)
      // 保留快照中的原始类型，避免已格式化的计数、后缀被后端再次处理。
      if (importedContext.value && item.previewValue === importedContext.value.context[code]) {
        return [code, importedContext.value.values[code]]
      }
      if (!item.groupCode || !raw) return [code, raw]
      try { return [item.groupCode, JSON.parse(raw)] } catch { return [item.groupCode, raw] }
    }))
    const result = await adminApi.previewAiRule({ fieldCode: props.fieldCode, config: config.value, values, currentRecord: importedContext.value?.currentRecord, execute: true })
    testOutput.value = result.output
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || 'AI 测试生成失败')
  } finally { testing.value = false }
}
onMounted(loadRecentRecords)
watch(selectedGenerationId, () => {
  selectedRecordIndex.value = undefined
  currentRecordOptions.value = []
  void importSelectedRecords()
})
watch(selectedRecordIndex, importSelectedRecords)
watch(() => JSON.stringify(variables.value.map(({ previewValue, ...variable }) => variable)), () => {
  if (selectedGenerationId.value) void importSelectedRecords()
})
</script>

<template>
  <section class="ai-rule-editor">
    <div class="record-importer">
      <label for="ai-report-generation">测试用报告生成记录</label>
      <el-select id="ai-report-generation" v-model="selectedGenerationId" filterable clearable placeholder="选择最近一次报告生成记录" :loading="recordsLoading" :disabled="testing" no-data-text="暂无成功生成的报告">
        <el-option v-for="item in recordOptions" :key="item.id" :value="item.id" :label="recordLabel(item)" />
      </el-select>
      <el-button :loading="recordsLoading" :disabled="testing" @click="loadRecentRecords">刷新列表</el-button>
      <el-button :loading="contextLoading" :disabled="!selectedGenerationId || testing" @click="importSelectedRecords">重新导入变量</el-button>
    </div>
    <div v-if="selectedGenerationId && requiresCurrentRecord" class="current-record-picker">
      <label for="ai-current-record">测试用编组记录</label>
      <el-select id="ai-current-record" v-model="selectedRecordIndex" :loading="contextLoading" :disabled="testing" placeholder="请选择一条记录，生成该条记录的结论" no-data-text="该次生成没有编组记录">
        <el-option v-for="(record, index) in currentRecordOptions" :key="index" :value="index" :label="currentRecordLabel(record, index)" />
      </el-select>
    </div>
    <p class="report-help" aria-live="polite">{{ contextLoading ? '正在加载该次生成的变量…' : selectedGenerationId && requiresCurrentRecord && selectedRecordIndex === undefined ? '该规则按记录生成结论，请再选择一条测试用编组记录。' : selectedGenerationId && importedContext ? '已导入该次生成的变量，可以测试生成。' : '选择后自动使用该次生成的数据快照，支持 Excel 和 LIMS 报告。' }}</p>
    <el-alert v-if="importError" :title="importError" type="error" :closable="false" show-icon />
    <el-alert v-if="missingVariables.length" :title="`该次生成缺少必填变量：${missingVariables.join('、')}。请补充预览值或选择其他记录。`" type="warning" :closable="false" show-icon />
    <SystemContextVariables v-model="variables" :fields="props.fields" :groups="props.groups" insert-label="插入" @insert="insertVariable" />
    <el-form-item label="提示词模板"><el-input v-model="config.promptTemplate" type="textarea" :rows="7" placeholder="使用 {{系统字段编码}} 引用上下文" /></el-form-item>
    <p class="referenced-fields">已引用：{{ referenced.join('、') || '暂无' }}</p>
    <el-form-item label="预览用变量值（可选）">
      <div class="preview-values"><el-input v-for="item in variables" :key="contextCode(item)" v-model="item.previewValue" :readonly="item.mode === 'CURRENT_RECORD'" :placeholder="item.mode === 'CURRENT_RECORD' ? '请先选择测试用编组记录' : contextCode(item) || '请先选择字段'" /></div>
    </el-form-item>
    <div class="prompt-preview"><b>发送内容预览</b><pre>{{ preview }}</pre></div>
    <div class="ai-options"><el-input v-model="config.model" placeholder="模型；留空使用系统配置" /><el-input-number v-model="config.maxLength" :min="100" :max="8000" /><el-input-number v-model="config.temperature" :min="0" :max="2" :step="0.1" /></div>
    <div><el-button type="primary" :loading="testing" :disabled="contextLoading || (!!selectedGenerationId && !importedContext) || (requiresCurrentRecord && !importedContext?.currentRecord)" @click="testGeneration">测试生成</el-button></div>
    <div v-if="testOutput" class="prompt-preview"><b>测试结果</b><pre>{{ testOutput }}</pre></div>
  </section>
</template>

<style scoped>
.ai-rule-editor{display:grid;gap:12px}.ai-editor-head{display:flex;align-items:center;justify-content:space-between}.record-importer{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px}.record-importer label{grid-column:1/-1;font-weight:500}.record-importer .el-select{min-width:0}.report-help{margin:0;color:#64748b;font-size:12px;line-height:1.6}.variable-row{display:grid;grid-template-columns:2fr 1.2fr .7fr 1fr auto auto auto;gap:8px;align-items:center}.referenced-fields{margin:0;color:#64748b;font-size:12px}.preview-values{width:100%;display:grid;gap:8px;grid-template-columns:repeat(2,minmax(0,1fr))}.prompt-preview{padding:12px;border:1px solid #dbe5ee;border-radius:8px;background:#f8fafc}.prompt-preview pre{margin:8px 0 0;white-space:pre-wrap;font:12px/1.6 inherit}.ai-options{display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px}
.current-record-picker{display:grid;gap:8px;min-width:0}.current-record-picker label{font-weight:500}
@media(max-width:640px){.record-importer{grid-template-columns:1fr 1fr}.record-importer .el-select{grid-column:1/-1}.preview-values{grid-template-columns:1fr}}
</style>
