<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { adminApi, type GenerationHistoryItem, type StandardField, type StandardFieldCatalog, type SystemFieldGroup } from './admin-api'
import SystemFieldCatalogTree from './SystemFieldCatalogTree.vue'

/** 一次生成的详情：逐字段列出取值与来源，而不是把整份快照当一坨 JSON 丢出来。 */
const props = defineProps<{ detail: GenerationHistoryItem }>()

const SOURCE_LABELS: Record<string, string> = {
  PROTOCOL: '方案', EXCEL: 'Excel', LIMS: 'LIMS', PDF: 'PDF', AI: 'AI 生成', CALCULATED: '系统计算',
  FIXED: '固定值', MANUAL: '人工录入', MANUAL_WORD: 'Word 人工编辑',
}
const labels = ref<Record<string, string>>({})
const catalog = ref<StandardFieldCatalog>()
const configuredRules = ref<Record<string, any>>({})
const selectedField = ref<StandardField>()
const selectedGroup = ref<SystemFieldGroup>()
const keyword = ref('')

watch(() => props.detail?.id, async () => {
  if (Object.keys(labels.value).length) return
  try {
    const [fields, directory] = await Promise.all([adminApi.allStandardFields(), adminApi.standardFieldCatalog()])
    labels.value = Object.fromEntries(fields.map((item: StandardField) => [item.fieldCode, item.label]))
    catalog.value = directory
    const rules = await Promise.all(fields.map(async (field: StandardField) => {
      try { return [field.fieldCode, (await adminApi.systemFieldRules(field.fieldCode)).find((rule) => rule.enabled)] as const }
      catch { return [field.fieldCode, undefined] as const }
    }))
    configuredRules.value = Object.fromEntries(rules.filter(([, rule]) => rule))
  } catch { labels.value = {} }
}, { immediate: true })

const snapshot = computed(() => (props.detail?.generation_snapshot || {}) as Record<string, any>)
const resolved = computed(() => (snapshot.value.resolved_data || {}) as Record<string, any>)
const context = computed(() => (props.detail?.generation_context || {}) as Record<string, any>)
function firstPopulatedMap(...values: unknown[]): Record<string, any> {
  const found = values.find((value) => value && typeof value === 'object' && Object.keys(value).length > 0)
  return (found && typeof found === 'object' ? found : {}) as Record<string, any>
}
const fieldSources = computed(() =>
  firstPopulatedMap(snapshot.value.field_sources, resolved.value.field_sources),
)
const originalValues = computed(() =>
  firstPopulatedMap(snapshot.value.original_values, resolved.value.original_values),
)

/** 一行 = 一个标准字段：取值 + 从哪来 + 用的哪条规则 */
const fieldRows = computed(() => {
  const sources = fieldSources.value
  const values = originalValues.value
  const catalogFields = catalog.value?.fields || []
  const catalogCodes = catalogFields.map((field) => field.fieldCode)
  const codes = Array.from(new Set([...catalogCodes, ...Object.keys(sources), ...Object.keys(values)])).sort()
  return codes.map((code) => {
    const source = sources[code] || {}
    const configured = configuredRules.value[code] || {}
    const config = configured.config && typeof configured.config === 'object' ? configured.config : {}
    const field = catalogFields.find((item) => item.fieldCode === code)
    const extractedValue = source.type === 'PROTOCOL' ? values[code] : hasValue(values[code]) ? values[code] : readResolvedValue(field?.legacyJsonPath || code)
    return {
      code, label: labels.value[code] || '',
      value: format(extractedValue),
      sourceType: String(source.type || configured.sourceType || ''),
      rule: String(source.ruleName || configured.name || source.record_id || ''),
      path: String(source.sourcePath || config.sourcePath || ''),
      message: String(source.message || ''),
    }
  })
})
const visibleFields = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return fieldRows.value
  return fieldRows.value.filter((row) => `${row.code}${row.label}${row.value}`.toLowerCase().includes(text))
})
const selectedFieldRow = computed(() => selectedField.value
  ? fieldRows.value.find((row) => row.code === selectedField.value?.fieldCode) || {
      code: selectedField.value.fieldCode,
      label: selectedField.value.label,
      value: format(readResolvedValue(selectedField.value.legacyJsonPath || selectedField.value.fieldCode)),
      sourceType: '', rule: '', path: selectedField.value.legacyJsonPath || '', message: '',
    } : undefined)
const selectedProtocolLocations = computed(() => fieldSources.value[selectedField.value?.fieldCode || '']?.type === 'PROTOCOL' ? fieldSources.value[selectedField.value?.fieldCode || ''].locations || [] : [])
const selectedGroupJson = computed(() => {
  if (!selectedGroup.value) return undefined
  const payloads = resolved.value.source_payloads
  if (!payloads || typeof payloads !== 'object') return undefined
  const path = `$.${selectedGroup.value.groupCode}`
  if (selectedGroup.value.fields.some(field => fieldSources.value[field.fieldCode]?.type === 'PROTOCOL')) return readValueAtPath(payloads.PROTOCOL, path)
  for (const sourceType of ['EXCEL', 'LIMS', 'PDF']) {
    const value = readValueAtPath(payloads[sourceType], path)
    if (value !== undefined) return value
  }
  return readValueAtPath(resolved.value, path)
})

function readResolvedValue(fieldCode: string): unknown {
  if (Object.prototype.hasOwnProperty.call(resolved.value, fieldCode)) return resolved.value[fieldCode]
  const direct = readValueAtPath(resolved.value, fieldCode)
  if (hasValue(direct)) return direct
  const payloads = resolved.value.source_payloads
  if (payloads && typeof payloads === 'object') {
    for (const sourceType of ['EXCEL', 'LIMS', 'PDF']) {
      const value = readValueAtPath(payloads[sourceType], fieldCode)
      if (hasValue(value)) return value
    }
  }
  return direct
}
function readValueAtPath(root: unknown, fieldCode: string): unknown {
  if (!root || typeof root !== 'object') return undefined
  const path = fieldCode.replace(/^\$\.?/, '').split('.').filter(Boolean)
  let values: any[] = [root]
  for (const rawSegment of path) {
    const isCollection = rawSegment.endsWith('[*]')
    const segment = isCollection ? rawSegment.slice(0, -3) : rawSegment
    values = values.flatMap((value) => {
      const next = value && typeof value === 'object' ? value[segment] : undefined
      return isCollection && Array.isArray(next) ? next : next === undefined ? [] : [next]
    })
  }
  return fieldCode.includes('[*]') ? values : values[0]
}
function hasValue(value: unknown): boolean {
  return value !== undefined && value !== null && value !== ''
    && !(Array.isArray(value) && value.length === 0)
}
function selectField(field: StandardField) {
  selectedGroup.value = undefined
  selectedField.value = field
}
function selectGroup(group: SystemFieldGroup) {
  selectedField.value = undefined
  selectedGroup.value = group
}

function format(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return JSON.stringify(value)
  if (typeof value === 'object') return `{${Object.keys(value as object).join('、')}}`
  return String(value)
}
</script>

<template>
  <div class="generation-detail">
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="报告">{{ detail.title }}</el-descriptions-item>
      <el-descriptions-item label="操作">{{ context.phase || '-' }}</el-descriptions-item>
      <el-descriptions-item label="生成人">{{ detail.display_name || detail.username || '-' }}</el-descriptions-item>
      <el-descriptions-item label="生成时间">{{ detail.generated_at }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="detail.status === 'SUCCESS' ? 'success' : detail.status === 'FAILED' ? 'danger' : 'warning'" size="small">
          {{ detail.status === 'SUCCESS' ? '成功' : detail.status === 'FAILED' ? '失败' : '生成中' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="模板">{{ context.template_name || '-' }} {{ context.template_version || '' }}</el-descriptions-item>
      <el-descriptions-item v-if="detail.error_message" label="失败原因" :span="2">
        <span class="failure">{{ detail.error_message }}</span>
      </el-descriptions-item>
    </el-descriptions>

    <h3>字段取值与来源 <small>{{ fieldRows.length }} 个字段</small></h3>
    <div v-if="catalog" class="field-directory">
      <SystemFieldCatalogTree :chapters="catalog.chapters" :groups="catalog.groups" :fields="catalog.fields"
        :selected-code="selectedField?.fieldCode" :selected-group="selectedGroup?.groupCode"
        @select="selectField" @group="selectGroup" />
      <section class="field-inspector">
        <template v-if="selectedField">
          <h4>{{ selectedField.label }} <small>{{ selectedField.fieldCode }}</small></h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item v-if="selectedFieldRow?.message" label="未提取原因">{{ selectedFieldRow.message }}</el-descriptions-item>
            <el-descriptions-item label="提取值">{{ selectedFieldRow?.value || '-' }}</el-descriptions-item>
            <el-descriptions-item label="来源">{{ SOURCE_LABELS[selectedFieldRow?.sourceType || ''] || selectedFieldRow?.sourceType || '-' }}</el-descriptions-item>
            <el-descriptions-item label="规则 / 路径">{{ selectedFieldRow?.rule || selectedFieldRow?.path || '-' }}</el-descriptions-item>
          </el-descriptions>
          <details v-if="selectedProtocolLocations.length"><summary>查看方案原文位置</summary><div v-for="(location, index) in selectedProtocolLocations" :key="index"><b>{{ location.section }}</b><span v-if="location.paragraph"> · 段落 {{ location.paragraph }}</span><span v-if="location.table"> · 表格 {{ location.table }}，行 {{ location.row }}，列 {{ location.column }}</span><pre class="group-json">{{ location.quote }}</pre></div></details>
        </template>
        <template v-else-if="selectedGroup">
          <h4>{{ selectedGroup.label }} <small>{{ selectedGroup.groupCode }}</small></h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="标准 JSON 路径">{{ `$.${selectedGroup.groupCode}` }}</el-descriptions-item>
          </el-descriptions>
          <pre class="group-json">{{ selectedGroupJson === undefined ? '-' : JSON.stringify(selectedGroupJson, null, 2) }}</pre>
        </template>
        <el-empty v-else description="从左侧标准字段目录选择字段或编组查看本次提取结果" :image-size="50" />
      </section>
    </div>
    <template v-else>
    <el-input v-model="keyword" placeholder="按字段名称或编码筛选" clearable size="small" class="field-filter" />
    <el-table v-if="visibleFields.length" :data="visibleFields" size="small" max-height="330">
      <el-table-column label="字段" min-width="150">
        <template #default="{ row }">{{ row.label || row.code.split('.').pop() }}</template>
      </el-table-column>
      <el-table-column prop="code" label="字段编码" min-width="180" show-overflow-tooltip />
      <el-table-column prop="value" label="取值" min-width="150" show-overflow-tooltip />
      <el-table-column label="来源" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.sourceType" size="small" disable-transitions>
            {{ SOURCE_LABELS[row.sourceType] || row.sourceType }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="规则 / 路径" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ row.rule || row.path || '-' }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-else :description="fieldRows.length ? '没有匹配的字段' : '该记录没有字段来源信息'" :image-size="50" />
    </template>
  </div>
</template>

<style scoped>
.generation-detail{display:grid;gap:6px}
.generation-detail h3{margin:16px 0 6px;color:#234c41;font-size:14px}
.generation-detail h3 small{margin-left:6px;color:#8a9993;font-size:11px;font-weight:400}
.failure{color:#c45656}
.field-filter{margin-bottom:6px}
.field-directory{display:grid;grid-template-columns:minmax(280px,36%) minmax(0,1fr);height:min(620px,calc(100vh - 250px));min-height:380px;overflow:hidden;border:1px solid #dbe5ee;border-radius:6px;background:#fff}
.field-directory :deep(.catalog-tree){height:100%;min-height:0;overflow:auto;padding:8px;border-right:1px solid #dbe5ee}
.field-inspector{min-height:0;overflow:auto;padding:14px}.field-inspector h4{margin:0 0 12px;font-size:14px}.field-inspector h4 small{margin-left:6px;color:#8a9993;font-weight:400}
.group-json{margin:10px 0 0;max-height:420px;overflow:auto;padding:10px;white-space:pre-wrap;border:1px solid #dbe5ee;border-radius:6px;background:#f8fafc;color:#41564e;font:11px/1.6 Consolas,monospace}
@media (max-width: 760px){.field-directory{grid-template-columns:1fr;grid-template-rows:260px minmax(260px,1fr);height:min(660px,calc(100vh - 180px));min-height:520px}.field-directory :deep(.catalog-tree){border-right:0;border-bottom:1px solid #dbe5ee}}
</style>
