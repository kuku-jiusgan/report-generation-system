<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { StandardField } from './admin-api'

/** 上下文变量：AI 提示词和计算规则的文本模板共用同一套取值方式。 */
export type ContextVariable = {
  fieldCode: string; required: boolean; mode: 'FIRST' | 'JOIN_UNIQUE' | 'COUNT_UNIQUE';
  separator: string; suffix: string; defaultValue: string; previewValue?: string
}

const props = defineProps<{ fields: StandardField[]; insertLabel?: string }>()
const emit = defineEmits<{ insert: [code: string] }>()
const variables = defineModel<ContextVariable[]>({ required: true })

const modes = [
  { value: 'FIRST', label: '取第一个值' },
  { value: 'JOIN_UNIQUE', label: '列表去重拼接' },
  { value: 'COUNT_UNIQUE', label: '去重计数' },
]
const fieldOptions = computed(() => props.fields)

function addVariable() {
  variables.value = [...variables.value, {
    fieldCode: '', required: true, mode: 'FIRST', separator: '、', suffix: '', defaultValue: '', previewValue: '',
  }]
}
function removeVariable(index: number) {
  variables.value = variables.value.filter((_, current) => current !== index)
}
</script>

<template>
  <div class="context-variables">
    <div class="context-head"><b>上下文变量</b><el-button plain :icon="Plus" @click="addVariable">添加变量</el-button></div>
    <div v-for="(item, index) in variables" :key="index" class="variable-row">
      <el-select v-model="item.fieldCode" filterable placeholder="选择系统字段">
        <el-option v-for="field in fieldOptions" :key="field.fieldCode" :label="`${field.label} · ${field.fieldCode}`" :value="field.fieldCode" />
      </el-select>
      <el-select v-model="item.mode">
        <el-option v-for="mode in modes" :key="mode.value" :label="mode.label" :value="mode.value" />
      </el-select>
      <el-input v-if="item.mode === 'JOIN_UNIQUE'" v-model="item.separator" placeholder="连接符" />
      <el-input v-if="item.mode !== 'COUNT_UNIQUE'" v-model="item.suffix" placeholder="每个值的后缀" />
      <el-input v-model="item.defaultValue" placeholder="缺失默认值" />
      <el-checkbox v-model="item.required">必填</el-checkbox>
      <el-button v-if="insertLabel" link type="primary" @click="emit('insert', item.fieldCode)">{{ insertLabel }}</el-button>
      <el-button link type="danger" :icon="Delete" @click="removeVariable(index)" />
    </div>
    <small class="context-hint">
      取值方式决定成组字段怎么拼成一句话：去重拼接得到“1.4%、0.3%、0.5%”，取值全相同时自动收敛成一个；去重计数得到条数。
    </small>
  </div>
</template>

<style scoped>
.context-variables{display:grid;gap:8px}
.context-head{display:flex;align-items:center;justify-content:space-between}
.variable-row{display:grid;grid-template-columns:2fr 1.2fr .8fr .8fr 1fr auto auto auto;gap:8px;align-items:center}
.context-hint{color:#64748b;line-height:1.6}
</style>
