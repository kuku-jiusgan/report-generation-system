<script setup lang="ts">
import { computed } from "vue";
import type { StandardField } from "./admin-api";
import ExcelCellAddressInput from "./ExcelCellAddressInput.vue";

const props = defineProps<{ modelValue: Record<string, unknown>; fields: StandardField[] }>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const config = computed({ get: () => props.modelValue, set: (value) => emit("update:modelValue", value) });
function repeatSource() { return (config.value.repeatCountSource || {}) as Record<string, unknown>; }
function valueSource() { return (config.value.repeatValueSource || {}) as Record<string, unknown>; }
function updateRepeatSource(values: Record<string, unknown>) {
  config.value.repeatCountSource = { ...repeatSource(), ...values };
}
function updateValueSource(values: Record<string, unknown>) {
  config.value.repeatValueSource = { ...valueSource(), ...values };
}
function updateAddress(value: { row: number; column: number }) { config.value.repeatCountSource = { ...repeatSource(), ...value }; }
function updateValueAddress(value: { row: number; column: number }) { config.value.repeatValueSource = { ...valueSource(), ...value }; }
</script>

<template>
  <div class="excel-rule-editor">
    <section class="excel-rule-section">
      <h3>基础定位</h3>
      <div class="excel-grid base"><el-form-item label="标准 JSON 路径"><el-input v-model="config.sourcePath" placeholder="$.systemSuitability[*].sequence" /></el-form-item><el-form-item label="来源 Sheet"><el-input v-model="config.sheet" placeholder="系统适用性" /></el-form-item><el-form-item label="提取模式"><el-select v-model="config.mode"><el-option label="固定单元格" value="FIXED_CELL" /><el-option label="重复区域" value="REPEAT_BLOCK" /></el-select></el-form-item></div>
    </section>
    <section v-if="config.mode === 'FIXED_CELL'" class="excel-rule-section"><h3>单元格位置</h3><div class="excel-grid three"><el-form-item label="行号"><el-input-number v-model="config.row" :min="1" /></el-form-item><el-form-item label="列号"><el-input-number v-model="config.column" :min="1" /></el-form-item><el-form-item label="必填"><el-switch v-model="config.required" /></el-form-item></div></section>
    <template v-else>
      <section class="excel-rule-section"><h3>重复区域</h3><div class="excel-grid five"><el-form-item label="起始行"><el-input-number v-model="config.rowStart" :min="1" /></el-form-item><el-form-item label="结束行"><el-input-number v-model="config.rowEnd" :min="1" /></el-form-item><el-form-item label="起始列"><el-input-number v-model="config.startColumn" :min="1" /></el-form-item><el-form-item label="列步长"><el-input-number v-model="config.columnStep" :min="0" /></el-form-item><el-form-item label="行步长"><el-input-number v-model="config.rowStep" :min="0" /></el-form-item></div><div class="excel-grid three"><el-form-item label="数量来源 Sheet"><el-input :model-value="repeatSource().sheet" placeholder="首页" @update:model-value="updateRepeatSource({ sheet: $event })" /></el-form-item><el-form-item label="数量来源单元格"><ExcelCellAddressInput :row="repeatSource().row" :column="repeatSource().column" placeholder="B8" @change="updateAddress" /></el-form-item><el-form-item label="最大重复组"><el-input-number v-model="config.maxRepeat" :min="1" :max="100" /></el-form-item></div></section>
      <section class="excel-rule-section"><h3>字段取值</h3><div class="excel-grid three"><el-form-item label="取值方式"><el-select v-model="config.valueMode"><el-option label="读取区域单元格" value="CELL" /><el-option label="每个重复组使用同一来源值" value="REPEAT_VALUE" /><el-option label="按行生成序号" value="INDEX" /></el-select></el-form-item><template v-if="config.valueMode === 'REPEAT_VALUE'"><el-form-item label="来源 Sheet"><el-input :model-value="valueSource().sheet" @update:model-value="updateValueSource({ sheet: $event })" /></el-form-item><el-form-item label="起始单元格"><ExcelCellAddressInput :row="valueSource().row" :column="valueSource().column" placeholder="A2" @change="updateValueAddress" /></el-form-item></template></div><div v-if="config.valueMode === 'REPEAT_VALUE'" class="excel-grid two"><el-form-item label="来源行步长"><el-input-number :model-value="valueSource().rowStep" :min="0" @update:model-value="updateValueSource({ rowStep: $event })" /></el-form-item><el-form-item label="来源列步长"><el-input-number :model-value="valueSource().columnStep" :min="0" @update:model-value="updateValueSource({ columnStep: $event })" /></el-form-item></div></section>
      <section class="excel-rule-section sequence"><div class="sequence-heading"><div><h3>序号生成</h3><small>用于 NO 等不直接读取单元格的字段</small></div><el-switch v-model="config.generateSequence" active-text="启用" /></div><div v-if="config.generateSequence" class="excel-grid two"><el-form-item label="序号依据字段"><el-select v-model="config.sequenceDependency" filterable><el-option v-for="field in fields" :key="field.fieldCode" :label="`${field.label} · ${field.fieldCode}`" :value="field.fieldCode" /></el-select></el-form-item><div class="sequence-note">仅对依据字段的非空值连续编号，每个重复组从 1 开始。</div></div></section>
    </template>
  </div>
</template>

<style scoped>
.excel-rule-editor{display:grid;gap:10px}.excel-rule-section{padding:12px 14px 2px;border:1px solid #dde5e1;background:#fafcfb}.excel-rule-section h3{margin:0 0 10px;color:#385248;font-size:12px}.excel-grid{display:grid;gap:0 10px}.excel-grid.base{grid-template-columns:2fr 1fr 1fr}.excel-grid.two{grid-template-columns:2fr 1fr}.excel-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.excel-grid.five{grid-template-columns:repeat(5,minmax(0,1fr))}.excel-rule-section :deep(.el-form-item){margin-bottom:10px}.excel-rule-section :deep(.el-form-item__label){height:22px;padding:0;color:#61736c;font-size:10px;line-height:22px}.excel-rule-section :deep(.el-input-number),.excel-rule-section :deep(.el-select){width:100%}.sequence{padding-bottom:12px}.sequence-heading{display:flex;align-items:center;justify-content:space-between}.sequence-heading h3{margin-bottom:2px}.sequence-heading small,.sequence-note{color:#71817b;font-size:10px}.sequence-note{align-self:center;padding-top:12px;line-height:1.5}@media(max-width:760px){.excel-grid.base,.excel-grid.five{grid-template-columns:repeat(2,minmax(0,1fr))}.excel-grid.two,.excel-grid.three{grid-template-columns:1fr}.excel-grid.base>:first-child{grid-column:1/-1}}
</style>
