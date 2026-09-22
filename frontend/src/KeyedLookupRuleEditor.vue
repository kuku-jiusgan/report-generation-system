<script setup lang="ts">
import { computed } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import type { StandardField } from './admin-api'

type LookupItem = { matchValue: string; sourceFieldCode: string; aggregation: 'FIRST' | 'JOIN_UNIQUE'; separator: string }
const props = defineProps<{ fields: StandardField[]; fieldCode: string }>()
const config = defineModel<Record<string, any>>({ required: true })
const isLookup = computed(() => String(config.value.operation || '').toUpperCase() === 'KEYED_LOOKUP')
const candidates = computed(() => props.fields.filter(field => field.fieldCode !== props.fieldCode))
const mappings = computed<LookupItem[]>({
  get: () => Array.isArray(config.value.mappings) ? config.value.mappings : [],
  set: value => { config.value.mappings = value },
})
function enableLookup() {
  config.value = {
    operation: 'KEYED_LOOKUP', matchFieldCode: '', mappings: [],
  }
}
function disableLookup() {
  config.value = {}
}
function addMapping() {
  mappings.value = [...mappings.value, { matchValue: '', sourceFieldCode: '', aggregation: 'FIRST', separator: '\n' }]
}
function removeMapping(index: number) {
  mappings.value = mappings.value.filter((_, current) => current !== index)
}
</script>

<template>
  <el-form-item label="计算类型">
    <el-select :model-value="isLookup ? 'KEYED_LOOKUP' : 'FORMULA'" @update:model-value="$event === 'KEYED_LOOKUP' ? enableLookup() : disableLookup()">
      <el-option label="普通计算或文本拼接" value="FORMULA" />
      <el-option label="按项目组装汇总结论" value="KEYED_LOOKUP" />
    </el-select>
  </el-form-item>
  <template v-if="isLookup">
    <el-alert type="info" :closable="false" show-icon title="按汇总表的验证项目匹配章节结论；所有项目和字段均来自当前配置。" />
    <el-form-item label="汇总行匹配字段">
      <el-select v-model="config.matchFieldCode" filterable placeholder="选择验证项目字段">
        <el-option v-for="field in candidates" :key="field.fieldCode" :label="`${field.label} · ${field.fieldCode}`" :value="field.fieldCode" />
      </el-select>
    </el-form-item>
    <div class="mapping-head"><b>项目与结论来源</b><el-button plain :icon="Plus" @click="addMapping">添加映射</el-button></div>
    <div v-for="(item, index) in mappings" :key="index" class="mapping-row">
      <el-input v-model="item.matchValue" placeholder="方案中的验证项目名称" />
      <el-select v-model="item.sourceFieldCode" filterable placeholder="章节结论字段">
        <el-option v-for="field in candidates" :key="field.fieldCode" :label="`${field.label} · ${field.fieldCode}`" :value="field.fieldCode" />
      </el-select>
      <el-select v-model="item.aggregation" aria-label="结论聚合方式">
        <el-option label="取第一条" value="FIRST" />
        <el-option label="去重后换行拼接" value="JOIN_UNIQUE" />
      </el-select>
      <el-input v-if="item.aggregation === 'JOIN_UNIQUE'" v-model="item.separator" placeholder="连接符" />
      <el-button link type="danger" :icon="Delete" @click="removeMapping(index)" />
    </div>
  </template>
  <template v-else>
    <el-form-item label="依赖系统字段"><el-select v-model="config.dependencies" multiple filterable><el-option v-for="item in candidates" :key="item.fieldCode" :label="`${item.label} · ${item.fieldCode}`" :value="item.fieldCode" /></el-select></el-form-item>
    <el-form-item label="计算表达式"><el-input v-model="config.expression" placeholder="例如 {sample.weight} / {sample.volume}" /></el-form-item>
    <el-form-item label="文本拼接模板"><el-input v-model="config.textTemplate" type="textarea" :rows="4" placeholder="例如 {sample.name}（批号：{sample.batchNo}）" /></el-form-item>
  </template>
</template>

<style scoped>
.mapping-head{display:flex;align-items:center;justify-content:space-between;margin:8px 0}.mapping-row{display:grid;grid-template-columns:1.1fr 2fr 1fr 1fr auto;gap:8px;align-items:center;margin-bottom:8px}
@media(max-width:760px){.mapping-row{grid-template-columns:1fr}.mapping-row .el-button{justify-self:end}}
</style>
