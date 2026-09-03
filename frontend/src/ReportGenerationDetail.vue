<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { adminApi, type GenerationHistoryItem, type StandardField } from './admin-api'

/** 一次生成的详情：逐字段列出取值与来源，而不是把整份快照当一坨 JSON 丢出来。 */
const props = defineProps<{ detail: GenerationHistoryItem }>()

const SOURCE_LABELS: Record<string, string> = {
  EXCEL: 'Excel', LIMS: 'LIMS', PDF: 'PDF', AI: 'AI 生成', CALCULATED: '系统计算',
  FIXED: '固定值', MANUAL: '人工录入', MANUAL_WORD: 'Word 人工编辑',
}
// resolved_data 里这些键是机器用的，不算"报告字段"
const INTERNAL_KEYS = new Set([
  'source_payloads', 'field_sources', 'original_values', 'warnings',
  'template_id', 'template_name', 'template_code', 'template_version',
  'template_revision', 'template_catalog_version_id',
])

const labels = ref<Record<string, string>>({})
const keyword = ref('')
const showRaw = ref(false)

watch(() => props.detail?.id, async () => {
  if (Object.keys(labels.value).length) return
  try {
    const fields = await adminApi.allStandardFields()
    labels.value = Object.fromEntries(fields.map((item: StandardField) => [item.fieldCode, item.label]))
  } catch { labels.value = {} }
}, { immediate: true })

const snapshot = computed(() => (props.detail?.generation_snapshot || {}) as Record<string, any>)
const resolved = computed(() => (snapshot.value.resolved_data || {}) as Record<string, any>)
const context = computed(() => (props.detail?.generation_context || {}) as Record<string, any>)
const warnings = computed<string[]>(() => snapshot.value.warnings || resolved.value.warnings || [])

/** 一行 = 一个标准字段：取值 + 从哪来 + 用的哪条规则 */
const fieldRows = computed(() => {
  const sources = (snapshot.value.field_sources || {}) as Record<string, any>
  const values = (snapshot.value.original_values || {}) as Record<string, any>
  const codes = Array.from(new Set([...Object.keys(sources), ...Object.keys(values)])).sort()
  return codes.map((code) => {
    const source = sources[code] || {}
    return {
      code, label: labels.value[code] || '',
      value: format(values[code]),
      sourceType: String(source.type || ''),
      rule: String(source.ruleName || source.record_id || ''),
      path: String(source.sourcePath || ''),
    }
  })
})
const visibleFields = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return fieldRows.value
  return fieldRows.value.filter((row) => `${row.code}${row.label}${row.value}`.toLowerCase().includes(text))
})

/** 报告本身的固定字段（报告编号、委托单位等） */
const reportFields = computed(() => Object.entries(resolved.value)
  .filter(([key, value]) => !INTERNAL_KEYS.has(key) && !Array.isArray(value)
    && (value === null || typeof value !== 'object'))
  .map(([key, value]) => ({ key, value: format(value) })))

/** 提取到的数据集合：编组数组长什么样、有几条 */
const collections = computed(() => {
  const payloads = (resolved.value.source_payloads || {}) as Record<string, any>
  const result: Array<{ origin: string; name: string; rows: any[] }> = []
  for (const [origin, payload] of Object.entries(payloads)) {
    if (!payload || typeof payload !== 'object') continue
    for (const [name, value] of Object.entries(payload as Record<string, any>)) {
      if (Array.isArray(value) && value.length && typeof value[0] === 'object') {
        result.push({ origin, name, rows: value })
      }
    }
  }
  return result
})

function columnsOf(rows: any[]) {
  return Array.from(new Set(rows.flatMap((row) => Object.keys(row || {})))).filter((key) => key !== '_evidence')
}
function format(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return `${value.length} 条`
  if (typeof value === 'object') return `{${Object.keys(value as object).join('、')}}`
  return String(value)
}
function cell(row: any, key: string): string {
  return format(row?.[key])
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

    <template v-if="warnings.length">
      <h3>生成警告 <small>{{ warnings.length }} 条</small></h3>
      <ul class="warning-list"><li v-for="(item, index) in warnings" :key="index">{{ item }}</li></ul>
    </template>

    <h3>字段取值与来源 <small>{{ fieldRows.length }} 个字段</small></h3>
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

    <template v-if="collections.length">
      <h3>提取到的数据集合 <small>{{ collections.length }} 个</small></h3>
      <el-collapse>
        <el-collapse-item v-for="item in collections" :key="`${item.origin}.${item.name}`"
          :name="`${item.origin}.${item.name}`">
          <template #title>
            <span class="collection-title">{{ item.name }}</span>
            <el-tag size="small" type="info">{{ item.origin }}</el-tag>
            <span class="collection-count">{{ item.rows.length }} 条</span>
          </template>
          <el-table :data="item.rows" size="small" max-height="300">
            <el-table-column v-for="key in columnsOf(item.rows)" :key="key" :label="key" min-width="130"
              show-overflow-tooltip>
              <template #default="{ row }">{{ cell(row, key) }}</template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </template>

    <template v-if="reportFields.length">
      <h3>报告字段</h3>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item v-for="item in reportFields" :key="item.key" :label="item.key">
          {{ item.value || '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </template>

    <div class="raw-toggle">
      <el-button text type="primary" @click="showRaw = !showRaw">
        {{ showRaw ? '收起原始快照' : '查看原始快照 JSON' }}
      </el-button>
    </div>
    <pre v-if="showRaw" class="raw-snapshot">{{ JSON.stringify(snapshot, null, 2) }}</pre>
  </div>
</template>

<style scoped>
.generation-detail{display:grid;gap:6px}
.generation-detail h3{margin:16px 0 6px;color:#234c41;font-size:14px}
.generation-detail h3 small{margin-left:6px;color:#8a9993;font-size:11px;font-weight:400}
.failure{color:#c45656}
.warning-list{margin:0;padding-left:18px;color:#a86a2c;font-size:12px;line-height:1.7}
.field-filter{margin-bottom:6px}
.collection-title{margin-right:8px;font-weight:600}
.collection-count{margin-left:auto;padding-right:12px;color:#7d918a;font-size:11px}
.raw-toggle{margin-top:12px}
.raw-snapshot{margin:0;max-height:320px;overflow:auto;padding:10px;white-space:pre-wrap;
  border:1px solid #dbe5ee;border-radius:6px;background:#f8fafc;color:#41564e;font:11px/1.6 Consolas,monospace}
</style>
