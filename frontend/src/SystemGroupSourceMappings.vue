<script setup lang="ts">
import { computed } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import type { StandardField, SystemGroupSourceMapping } from './admin-api'

const props = defineProps<{
  modelValue: SystemGroupSourceMapping[]
  fields: Array<Pick<StandardField, 'fieldCode' | 'label' | 'jsonKey'>>
}>()
const emit = defineEmits<{ 'update:modelValue': [value: SystemGroupSourceMapping[]] }>()

const mappings = computed(() => props.modelValue || [])
function update(index: number, value: Partial<SystemGroupSourceMapping>) {
  const next = mappings.value.map((item, itemIndex) => itemIndex === index ? { ...item, ...value } : item)
  emit('update:modelValue', next)
}
function addMapping() {
  emit('update:modelValue', [...mappings.value, {
    sourceType: 'LIMS', sectionPattern: '', worksheetPattern: '', headerPattern: '', columnMappings: [],
  }])
}
function removeMapping(index: number) {
  emit('update:modelValue', mappings.value.filter((_, itemIndex) => itemIndex !== index))
}
function addColumn(index: number) {
  const mapping = mappings.value[index]
  update(index, { columnMappings: [...(mapping.columnMappings || []), { fieldCode: '', columnPattern: '' }] })
}
function updateColumn(index: number, columnIndex: number, value: Partial<{ fieldCode: string; columnPattern: string }>) {
  const mapping = mappings.value[index]
  const columns = (mapping.columnMappings || []).map((item, itemIndex) => itemIndex === columnIndex ? { ...item, ...value } : item)
  update(index, { columnMappings: columns })
}
function removeColumn(index: number, columnIndex: number) {
  const mapping = mappings.value[index]
  update(index, { columnMappings: (mapping.columnMappings || []).filter((_, itemIndex) => itemIndex !== columnIndex) })
}
</script>

<template>
  <details class="source-mappings">
    <summary class="mapping-head">
      <div><b>批量来源映射（可选）</b><small>只有一张表要同时生成多条记录时才需要配置；字段规则已能提取时请留空。</small></div>
      <span class="mapping-toggle">{{ mappings.length ? `已配置 ${mappings.length} 条` : '未配置' }}</span>
    </summary>
    <div class="mapping-body">
      <div class="mapping-actions"><span>按章节、工作表和表头识别表格，再把列写入当前编组字段。</span><el-button text type="primary" :icon="Plus" @click="addMapping">新增来源规则</el-button></div>
      <p v-if="!mappings.length" class="mapping-empty">没有配置时不会影响字段规则提取。</p>
      <div v-for="(mapping, index) in mappings" :key="index" class="mapping-card">
      <div class="mapping-card-head">
        <el-select :model-value="mapping.sourceType" @update:model-value="update(index, { sourceType: $event })">
          <el-option label="LIMS HTML 表格" value="LIMS" />
          <el-option label="Excel 工作表" value="EXCEL" />
        </el-select>
        <el-button text type="danger" :icon="Delete" @click="removeMapping(index)">删除规则</el-button>
      </div>
      <div class="form-grid three">
        <el-form-item label="章节匹配"><el-input :model-value="mapping.sectionPattern || ''" placeholder="正则，例如 检测限与定量限" @update:model-value="update(index, { sectionPattern: $event })" /></el-form-item>
        <el-form-item label="工作表匹配"><el-input :model-value="mapping.worksheetPattern || ''" placeholder="Excel 工作表名称正则" @update:model-value="update(index, { worksheetPattern: $event })" /></el-form-item>
        <el-form-item label="表头匹配"><el-input :model-value="mapping.headerPattern || ''" placeholder="正则，例如 检测限|定量限" @update:model-value="update(index, { headerPattern: $event })" /></el-form-item>
      </div>
      <div class="column-head"><b>列与标准字段</b><el-button text type="primary" :icon="Plus" @click="addColumn(index)">添加列</el-button></div>
      <div v-for="(column, columnIndex) in mapping.columnMappings || []" :key="columnIndex" class="column-row">
        <el-select :model-value="column.fieldCode" filterable placeholder="选择字段" @update:model-value="updateColumn(index, columnIndex, { fieldCode: $event })">
          <el-option v-for="field in fields" :key="field.fieldCode" :label="`${field.label} · ${field.jsonKey}`" :value="field.fieldCode" />
        </el-select>
        <el-input :model-value="column.columnPattern" placeholder="列名或正则" @update:model-value="updateColumn(index, columnIndex, { columnPattern: $event })" />
        <el-button text type="danger" :icon="Delete" aria-label="删除列" @click="removeColumn(index, columnIndex)" />
      </div>
      <p v-if="!(mapping.columnMappings || []).length" class="mapping-empty">至少添加一列字段映射。</p>
      </div>
    </div>
  </details>
</template>

<style scoped>
.source-mappings{margin-top:16px;padding:14px 16px;border:1px solid #e1e8e5;border-radius:8px;background:#f8fafb}.source-mappings>summary{list-style:none;cursor:pointer}.source-mappings>summary::-webkit-details-marker{display:none}.source-mappings[open]>summary{padding-bottom:10px;border-bottom:1px solid #e6ece9}.mapping-toggle{flex:none;color:#71817b;font-size:10px}.mapping-body{padding-top:10px}.mapping-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#71817b;font-size:10px;line-height:1.5}
.mapping-head,.mapping-card-head,.column-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
.mapping-head b,.column-head b{color:#30483f;font-size:12px}.mapping-head small{display:block;margin-top:3px;color:#7b8a84;font-size:11px}
.mapping-card{margin-top:10px;padding:12px;border:1px solid #e2eae6;border-radius:6px;background:#fff}.mapping-card-head{margin-bottom:8px}
.column-head{margin:2px 0 6px;color:#52655e;font-size:11px}.column-row{display:grid;grid-template-columns:1.1fr 1fr 34px;gap:8px;align-items:center;margin-top:6px}
.mapping-empty{margin:8px 0 0;color:#8a9993;font-size:11px}
</style>
