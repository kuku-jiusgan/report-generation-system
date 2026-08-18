<script setup lang="ts">
import { computed, ref } from 'vue'
import { Coin, Search } from '@element-plus/icons-vue'
import type { StandardField } from './admin-api'

const props = defineProps<{ modelValue?: string; fields: StandardField[] }>()
const emit = defineEmits<{ select: [field: StandardField]; open: [] }>()
const visible = ref(false)
const search = ref('')
const selected = computed(() => props.fields.find((item) => item.fieldCode === props.modelValue))
const filtered = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return props.fields
  return props.fields.filter((item) => `${item.label} ${item.fieldCode} ${item.dbTable} ${item.dbColumn}`.toLowerCase().includes(keyword))
})
const groupDisplay = (field: StandardField) => field.groupLabels?.length
  ? field.groupLabels.join(' / ')
  : field.groupLabel || field.groupCode || '未分组'
const dbLocation = (field: StandardField) =>
  `${field.dbTable}.${field.dbColumn}${field.jsonKey ? ` → ${field.jsonKey}` : ''}`

function choose(field: StandardField) {
  emit('select', field)
  visible.value = false
}
function openPicker() {
  search.value = ''
  emit('open')
  visible.value = true
}
</script>

<template>
  <el-button
    class="standard-field-button"
    type="primary"
    plain
    :icon="Coin"
    @click="openPicker"
  >{{ selected ? '重新选择系统标准字段' : '选择系统标准字段' }}</el-button>

  <el-dialog v-model="visible" title="选择系统标准字段" width="min(1080px, 96vw)" append-to-body class="standard-field-dialog">
    <el-input v-model="search" :prefix-icon="Search" placeholder="搜索业务名称、字段编码或数据库位置" clearable />
    <div class="field-catalog-list">
      <button v-for="field in filtered" :key="field.fieldCode" class="field-catalog-row" type="button" @dblclick="choose(field)">
        <span class="field-main"><b>{{ field.label }}</b><small>{{ groupDisplay(field) }}</small></span>
        <span class="field-code"><em>字段编码</em><code>{{ field.fieldCode }}</code></span>
        <span class="field-location"><em>数据库位置</em><code>{{ dbLocation(field) }}</code></span>
        <el-tag size="small" effect="plain">{{ field.cardinality === 'MANY' ? '一对多' : '单值' }}</el-tag>
        <el-button type="primary" link @click.stop="choose(field)">选择</el-button>
      </button>
      <el-empty v-if="!filtered.length" :image-size="52" description="没有匹配的系统标准字段" />
    </div>
  </el-dialog>
</template>

<style scoped>
.standard-field-button{width:100%;margin:0 0 10px}.field-catalog-list{max-height:430px;margin-top:14px;overflow:auto;border:1px solid #e0e7ef;border-radius:8px}.field-catalog-row{display:grid;grid-template-columns:minmax(140px,1fr) minmax(160px,1fr) minmax(190px,1.25fr) 72px 56px;align-items:center;gap:12px;width:100%;padding:10px 12px;border:0;border-bottom:1px solid #edf2f6;background:#fff;text-align:left;cursor:pointer}.field-catalog-row:last-child{border-bottom:0}.field-catalog-row:hover{background:#f5f9fc}.field-main,.field-code,.field-location{min-width:0}.field-main b,.field-main small,.field-code em,.field-location em,.field-code code,.field-location code{display:block}.field-main b{color:#243746;font-size:13px}.field-main small,.field-code em,.field-location em{color:#7a8b98;font-size:10px;font-style:normal}.field-code code,.field-location code{overflow-wrap:anywhere;color:#31594e;font-size:11px;line-height:1.45}@media (max-width:760px){.field-catalog-row{grid-template-columns:1fr 64px}.field-code,.field-location{grid-column:1 / -1}}
</style>
