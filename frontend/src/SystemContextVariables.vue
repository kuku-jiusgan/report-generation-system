<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { StandardField } from './admin-api'

/** 上下文变量：AI 提示词和计算规则的文本模板共用同一套取值方式。 */
export type ContextVariable = {
  fieldCode?: string; groupCode?: string; required: boolean; mode: 'FIRST' | 'JOIN_UNIQUE' | 'COUNT_UNIQUE' | 'CURRENT_RECORD';
  separator: string; suffix: string; defaultValue: string; previewValue?: string
}

const props = defineProps<{ fields: StandardField[]; groups?: Array<{ groupCode: string; label: string; fields: Array<{ fieldCode: string }> }>; insertLabel?: string }>()
const emit = defineEmits<{ insert: [code: string] }>()
const variables = defineModel<ContextVariable[]>({ required: true })

const modes = [
  { value: 'FIRST', label: '取第一个值' },
  { value: 'JOIN_UNIQUE', label: '列表去重拼接' },
  { value: 'COUNT_UNIQUE', label: '去重计数' },
  { value: 'CURRENT_RECORD', label: '当前记录' },
]

// 构建选择项：优先显示编组，没有编组的字段单独显示
const selectOptions = computed(() => {
  const groups = props.groups || []
  const result: Array<{ type: 'group' | 'field'; code: string; label: string; groupLabel?: string }> = []

  // 添加所有编组
  groups.forEach(group => {
    if (group.fields.length > 0) {
      result.push({ type: 'group', code: group.groupCode, label: `${group.label}（编组）`, groupLabel: group.label })
    }
  })

  // 找出没有编组的字段
  const groupedFieldCodes = new Set(groups.flatMap(g => g.fields.map(f => f.fieldCode)))
  props.fields.forEach(field => {
    if (!groupedFieldCodes.has(field.fieldCode)) {
      result.push({ type: 'field', code: field.fieldCode, label: `${field.label} · ${field.fieldCode}` })
    }
  })

  return result
})

function addVariable() {
  variables.value = [...variables.value, {
    fieldCode: '', groupCode: '', required: true, mode: 'FIRST', separator: '、', suffix: '', defaultValue: '', previewValue: '',
  }]
}
function removeVariable(index: number) {
  variables.value = variables.value.filter((_, current) => current !== index)
}
function getVariableCode(item: ContextVariable) {
  return item.groupCode || item.fieldCode || ''
}
function setVariableCode(item: ContextVariable, code: string) {
  const option = selectOptions.value.find(opt => opt.code === code)
  if (option?.type === 'group') {
    item.groupCode = code
    item.fieldCode = ''
  } else {
    item.fieldCode = code
    item.groupCode = ''
  }
}
</script>

<template>
  <div class="context-variables">
    <div class="context-head"><b>上下文变量</b><el-button plain :icon="Plus" @click="addVariable">添加变量</el-button></div>
    <div v-for="(item, index) in variables" :key="index" class="variable-row">
      <el-select :model-value="getVariableCode(item)" @update:model-value="setVariableCode(item, $event)" filterable placeholder="选择编组或字段">
        <el-option v-for="option in selectOptions" :key="option.code" :label="option.label" :value="option.code" />
      </el-select>
      <el-select v-model="item.mode">
        <el-option v-for="mode in modes" :key="mode.value" :label="mode.label" :value="mode.value" />
      </el-select>
      <el-input v-if="item.mode === 'JOIN_UNIQUE'" v-model="item.separator" placeholder="连接符" />
      <el-input v-if="item.mode !== 'COUNT_UNIQUE' && item.mode !== 'CURRENT_RECORD'" v-model="item.suffix" placeholder="每个值的后缀" />
      <el-input v-model="item.defaultValue" placeholder="缺失默认值" />
      <el-checkbox v-model="item.required">必填</el-checkbox>
      <el-button v-if="insertLabel" link type="primary" @click="emit('insert', getVariableCode(item))">{{ insertLabel }}</el-button>
      <el-button link type="danger" :icon="Delete" @click="removeVariable(index)" />
    </div>
    <small class="context-hint">
      编组会传递整个编组的数据（对象或数组），单字段传递字段值。取值方式决定成组字段怎么拼成一句话：去重拼接得到"1.4%、0.3%、0.5%"，取值全相同时自动收敛成一个；去重计数得到条数；<strong>当前记录</strong>用于AI字段在编组内部，按每条记录生成（如每个杂质生成一个结论）。
    </small>
  </div>
</template>

<style scoped>
.context-variables{display:grid;gap:8px}
.context-head{display:flex;align-items:center;justify-content:space-between}
.variable-row{display:grid;grid-template-columns:2fr 1.2fr .8fr .8fr 1fr auto auto auto;gap:8px;align-items:center}
.context-hint{color:#64748b;line-height:1.6}
</style>
