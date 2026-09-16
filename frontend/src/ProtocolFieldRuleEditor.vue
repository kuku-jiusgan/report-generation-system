<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type SystemFieldGroup, type SystemGroupSourceMapping } from './admin-api'
import SystemGroupSourceMappings from './SystemGroupSourceMappings.vue'
import { loadProtocolMetadata, previewProtocolRule, type ProtocolMetadata, type ProtocolPreview } from './protocol-api'
const config = defineModel<Record<string, unknown>>({ required: true })
const props = defineProps<{ groups: SystemFieldGroup[]; fieldCode: string; transform: string }>()
const emit = defineEmits<{ 'group-updated': [group: SystemFieldGroup]; 'mapping-dirty': [dirty: boolean] }>()
const sharedDraft = ref<SystemGroupSourceMapping[]>([])
const savedMappings = ref('[]')
const mappingSaving = ref(false)
const mappingError = ref('')
const selectedGroup = computed(() => props.groups.find(group => group.groupCode === config.value.groupCode))
const mappingDirty = computed(() => config.value.mode === 'TABLE_ROWS' && JSON.stringify(sharedDraft.value) !== savedMappings.value)
watch(selectedGroup, (group, previous) => {
  const keepDraft = previous?.groupCode === group?.groupCode && mappingDirty.value
  const mappings = JSON.parse(JSON.stringify(group?.sourceMappings.filter(item => item.sourceType === 'PROTOCOL') || []))
  savedMappings.value = JSON.stringify(mappings)
  if (!keepDraft) sharedDraft.value = mappings
  mappingError.value = ''
}, { immediate: true })
watch(mappingDirty, dirty => emit('mapping-dirty', dirty), { immediate: true })
async function saveMapping() {
  if (!selectedGroup.value || mappingSaving.value) return
  mappingSaving.value = true; mappingError.value = ''
  try {
    const submitted = JSON.parse(JSON.stringify(sharedDraft.value)) as SystemGroupSourceMapping[]
    const sourceMappings = [...selectedGroup.value.sourceMappings.filter(item => item.sourceType !== 'PROTOCOL'), ...submitted]
    const group = await adminApi.updateFieldGroup(selectedGroup.value.groupCode, { ...selectedGroup.value, sourceMappings })
    savedMappings.value = JSON.stringify(group.sourceMappings.filter(item => item.sourceType === 'PROTOCOL'))
    emit('group-updated', group)
    ElMessage.success('编组提取条件已保存')
  } catch (cause) { mappingError.value = errorText(cause); console.error('[方案规则] 保存编组提取条件失败', cause) }
  finally { mappingSaving.value = false }
}
const metadata = ref<ProtocolMetadata>()
const loading = ref(false)
const previewing = ref(false)
const error = ref('')
const previewError = ref('')
const documentId = ref('')
const result = ref<ProtocolPreview>()
let requestVersion = 0
const mode = computed(() => metadata.value?.modes.find(item => item.value === config.value.mode))
const availableGroups = computed(() => props.groups.filter(group => group.enabled && group.cardinality === 'MANY' && group.fields.some(field => field.fieldCode === props.fieldCode)))
function errorText(cause: unknown) {
  const response = cause as { response?: { data?: { detail?: string } }; message?: string }
  return response.response?.data?.detail || response.message || '操作失败，请重试'
}
async function load() {
  loading.value = true; error.value = ''
  try { metadata.value = await loadProtocolMetadata() }
  catch (cause) { error.value = errorText(cause); console.error('[方案规则] 加载失败', cause) }
  finally { loading.value = false }
}
async function preview() {
  if (!documentId.value) return ElMessage.warning('请选择已上传的方案')
  const version = ++requestVersion
  previewing.value = true; previewError.value = ''; result.value = undefined
  try {
    const output = await previewProtocolRule({ documentId: documentId.value, fieldCode: props.fieldCode, config: config.value, transform: props.transform,
      ...(config.value.mode === 'TABLE_ROWS' ? { sourceMappings: sharedDraft.value } : {}) })
    if (version === requestVersion) result.value = output
  }
  catch (cause) { if (version === requestVersion) previewError.value = errorText(cause); console.error('[方案规则] 试提取失败', cause) }
  finally { previewing.value = false }
}
watch(() => config.value.mode, () => {
  config.value = { mode: config.value.mode, required: config.value.required !== false }
})
watch([config, documentId, () => props.transform], () => { requestVersion++; result.value = undefined; previewError.value = '' }, { deep: true })
watch(sharedDraft, () => { requestVersion++; result.value = undefined; previewError.value = ''; mappingError.value = '' }, { deep: true })
onMounted(load)
onBeforeUnmount(() => emit('mapping-dirty', false))
</script>
<template>
  <section v-loading="loading" class="protocol-rule-editor" aria-label="方案提取配置">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-button v-if="error" @click="load">重新加载方案配置</el-button>
    <template v-if="metadata">
      <el-alert title="仅提取方案原文。定位不唯一时提示错误，请先试提取核对。已有其他来源规则时，请先停用再保存方案规则。" type="info" :closable="false" />
      <div class="form-grid two">
        <el-form-item label="方案提取方式"><el-select v-model="config.mode"><el-option v-for="item in metadata.modes" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <el-form-item label="生成报告时是否必需"><el-switch :model-value="config.required !== false" active-text="必需" inactive-text="可选" @update:model-value="config.required = $event" /><small class="help">必需字段提取失败时阻止生成；可选字段显示未提取原因。</small></el-form-item>
      </div>
      <template v-for="key in mode?.inputs || []" :key="key">
        <el-form-item v-if="key === 'groupCode'" label="共享表格定位的编组">
          <el-select v-model="config.groupCode" placeholder="选择当前字段所属的多行编组"><el-option v-for="group in availableGroups" :key="group.groupCode" :value="group.groupCode" :label="group.label" /></el-select>
          <small class="help">在下方编辑章节、表头、列映射和分组键。共享条件保存在编组中，修改会影响引用该编组的方案字段。</small>
          <template v-if="selectedGroup">
            <SystemGroupSourceMappings v-model="sharedDraft" :fields="selectedGroup.fields" :levels="selectedGroup.levels" protocol-only expanded />
            <small class="help">试提取使用当前编辑内容；正式提取使用已保存的条件。请先保存编组提取条件，再保存字段规则。</small>
            <el-button :loading="mappingSaving" :disabled="!mappingDirty" @click="saveMapping">保存编组提取条件</el-button>
            <el-alert v-if="mappingError" :title="mappingError" type="error" :closable="false" show-icon role="alert" />
          </template>
        </el-form-item>
        <el-form-item v-else :label="metadata.inputs[key].label"><el-input :model-value="String(config[key] || '')" @update:model-value="config[key] = $event" /><small class="help">{{ metadata.inputs[key].help }}</small></el-form-item>
      </template>
      <div class="preview-area">
        <el-form-item label="试提取方案"><el-select v-model="documentId" filterable placeholder="选择已上传的 DOCX 方案"><el-option v-for="document in metadata.documents" :key="document.id" :label="document.fileName" :value="document.id" /></el-select></el-form-item>
        <p v-if="!metadata.documents.length" class="help">尚无方案文件，请先在报告创建页面上传方案，再重新打开规则配置。</p>
        <el-button :loading="previewing" :disabled="!config.mode || !documentId" @click="preview">试提取并核对原文</el-button>
        <el-alert v-if="previewError" :title="previewError" type="error" :closable="false" show-icon role="alert" />
        <div v-if="result" aria-live="polite">
          <details v-if="result.groups && Object.keys(result.groups).length" open><summary>查看编组结构与项目对应关系</summary><pre class="preview-value">{{ JSON.stringify(result.groups, null, 2) }}</pre></details>
          <div v-for="(field, code) in result.fields" :key="code">
            <el-alert v-if="field.status === 'ERROR'" :title="field.message" :type="config.required === false ? 'warning' : 'error'" :closable="false" show-icon />
            <template v-else>
              <strong>提取成功</strong><pre class="preview-value">{{ typeof field.value === 'string' ? field.value : JSON.stringify(field.value, null, 2) }}</pre>
              <details><summary>查看原文位置</summary><div v-for="(location, index) in field.source.locations" :key="index" class="location"><b>{{ location.section }}</b><span v-if="location.paragraph"> · 段落 {{ location.paragraph }}</span><span v-if="location.table"> · 表格 {{ location.table }}，行 {{ location.row }}，列 {{ location.column }}</span><p v-if="location.parentValue">所属记录：{{ location.parentValue }}</p><p>{{ location.quote }}</p></div></details>
            </template>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
<style scoped>
.protocol-rule-editor{min-height:100px}.protocol-rule-editor>.el-alert{margin-bottom:20px}.help{display:block;margin-top:6px;color:#52635c;font-size:12px;line-height:1.6}.preview-area{margin-top:24px;padding-top:20px;border-top:1px solid #dce5e1}.preview-area>.el-alert,.preview-area>div{margin-top:16px}.preview-value{max-height:280px;overflow:auto;padding:12px;background:#f4f7fb;white-space:pre-wrap;overflow-wrap:anywhere;color:#263548;font:inherit}.location{padding:10px 0;border-bottom:1px solid #dce5e1}.location p{white-space:pre-wrap;overflow-wrap:anywhere}.form-grid{display:grid;gap:16px}.form-grid.two{grid-template-columns:1fr 1fr}details summary{cursor:pointer;color:#235c4d}@media(max-width:640px){.form-grid.two{grid-template-columns:1fr}}
</style>
