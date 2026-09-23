<script setup lang="ts">
import { computed } from "vue";
import type { StandardField } from "./admin-api";
import ExcelCellAddressInput from "./ExcelCellAddressInput.vue";
import ExcelJoinSourcesEditor from "./ExcelJoinSourcesEditor.vue";

const props = defineProps<{ modelValue: Record<string, unknown>; fields: StandardField[] }>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();
const config = computed({ get: () => props.modelValue, set: (value) => emit("update:modelValue", value) });
const isChartMode = computed(() => ["CHART_IMAGE", "LINEAR_REGRESSION_CHART"].includes(String(config.value.mode)));
function repeatSource() { return (config.value.repeatCountSource || {}) as Record<string, unknown>; }
function valueSource() { return (config.value.repeatValueSource || {}) as Record<string, unknown>; }
function updateRepeatSource(values: Record<string, unknown>) {
  config.value.repeatCountSource = { ...repeatSource(), ...values };
}
function updateValueSource(values: Record<string, unknown>) {
  config.value.repeatValueSource = { ...valueSource(), ...values };
}
function pairColumns(): number[] {
  const columns = config.value.pairColumns;
  return Array.isArray(columns) && columns.length === 2
    ? columns.map((column) => Number(column))
    : [1, 2];
}
function updatePairColumn(index: number, value: number | undefined) {
  const columns = pairColumns();
  columns[index] = Number(value || 1);
  config.value.pairColumns = columns;
}
function updateAddress(value: { row: number; column: number }) { config.value.repeatCountSource = { ...repeatSource(), ...value }; }
function updateValueAddress(value: { row: number; column: number }) { config.value.repeatValueSource = { ...valueSource(), ...value }; }
function regions(): Array<Record<string, unknown>> {
  return Array.isArray(config.value.regions) ? config.value.regions as Array<Record<string, unknown>> : [];
}
function updateRegion(index: number, values: Record<string, unknown>) {
  config.value.regions = regions().map((region, position) => position === index ? { ...region, ...values } : region);
}
function addRegion() {
  config.value.regions = [...regions(), { label: `区域 ${regions().length + 1}`, rowStart: 1, rowEnd: 1 }];
}
function removeRegion(index: number) {
  config.value.regions = regions().filter((_, position) => position !== index);
}
</script>

<template>
  <div class="excel-rule-editor">
    <section class="excel-rule-section">
      <h3>基础定位</h3>
      <div class="excel-grid base"><el-form-item label="标准 JSON 路径"><el-input v-model="config.sourcePath" placeholder="$.systemSuitability[*].sequence" /></el-form-item><el-form-item label="来源 Sheet"><el-input v-model="config.sheet" placeholder="系统适用性" /></el-form-item><el-form-item label="提取模式"><el-select v-model="config.mode"><el-option label="固定单元格" value="FIXED_CELL" /><el-option label="重复区域" value="REPEAT_BLOCK" /><el-option label="图表图片" value="CHART_IMAGE" /><el-option label="线性回归图" value="LINEAR_REGRESSION_CHART" /></el-select></el-form-item></div>
    </section>
    <section v-if="config.mode === 'FIXED_CELL'" class="excel-rule-section"><h3>单元格位置</h3><div class="excel-grid three"><el-form-item label="行号"><el-input-number v-model="config.row" :min="1" /></el-form-item><el-form-item label="列号"><el-input-number v-model="config.column" :min="1" /></el-form-item><el-form-item label="必填"><el-switch v-model="config.required" /></el-form-item></div></section>
    <section v-else-if="isChartMode" class="excel-rule-section">
      <h3>图表选择</h3>
      <div class="excel-grid three"><el-form-item label="每张图使用次数"><el-input-number v-model="config.pointsPerTest" :min="1" :max="1000" /></el-form-item><el-form-item label="起始序号"><el-input-number v-model="config.chartStartIndex" :min="0" /></el-form-item><el-form-item label="选择步长"><el-input-number v-model="config.chartStep" :min="1" /></el-form-item></div>
    </section>
    <template v-else>
      <section class="excel-rule-section"><h3>重复区域</h3><div class="excel-grid five"><el-form-item label="起始行"><el-input-number v-model="config.rowStart" :min="1" /></el-form-item><el-form-item label="结束行"><el-input-number v-model="config.rowEnd" :min="1" /></el-form-item><el-form-item label="起始列"><el-input-number v-model="config.startColumn" :min="1" /></el-form-item><el-form-item label="列步长"><el-input-number v-model="config.columnStep" :min="0" /></el-form-item><el-form-item label="行步长"><el-input-number v-model="config.rowStep" :min="0" /></el-form-item></div><div class="excel-grid four"><el-form-item label="固定重复组数"><el-input-number v-model="config.repeatCount" :min="0" :max="1000" /></el-form-item><el-form-item label="数量来源 Sheet"><el-input :model-value="repeatSource().sheet" placeholder="可选" @update:model-value="updateRepeatSource({ sheet: $event })" /></el-form-item><el-form-item label="数量来源单元格"><ExcelCellAddressInput :row="repeatSource().row" :column="repeatSource().column" placeholder="可选" @change="updateAddress" /></el-form-item><el-form-item label="最大重复组"><el-input-number v-model="config.maxRepeat" :min="1" :max="1000" /></el-form-item></div>
        <div v-if="regions().length" class="region-list"><div v-for="(region, index) in regions()" :key="index" class="region-item"><strong>{{ region.label || `区域 ${index + 1}` }}</strong><el-input :model-value="region.sheet || config.sheet" placeholder="工作表" @update:model-value="updateRegion(index, { sheet: $event })" /><el-input :model-value="region.label" placeholder="区域名称" @update:model-value="updateRegion(index, { label: $event })" /><el-input-number :model-value="region.rowStart" :min="1" @update:model-value="updateRegion(index, { rowStart: $event })" /><el-input-number :model-value="region.rowEnd" :min="1" @update:model-value="updateRegion(index, { rowEnd: $event })" /><el-input-number :model-value="region.startColumn" :min="1" @update:model-value="updateRegion(index, { startColumn: $event })" /><el-input-number :model-value="region.rowStep ?? config.rowStep" :min="0" @update:model-value="updateRegion(index, { rowStep: $event })" /><el-button type="danger" text @click="removeRegion(index)">删除区域</el-button></div></div><el-button plain size="small" @click="addRegion">添加提取区域</el-button>
      </section>
      <section class="excel-rule-section"><h3>字段取值</h3><div class="excel-grid three"><el-form-item label="取值方式"><el-select v-model="config.valueMode"><el-option label="读取区域单元格" value="CELL" /><el-option label="横向读取单元格" value="HORIZONTAL_CELL" /><el-option label="读取合并单元格" value="MERGED_CELL" /><el-option label="拼接两个单元格" value="CELL_PAIR" /><el-option label="每个重复组使用同一来源值" value="REPEAT_VALUE" /><el-option label="按行生成序号" value="INDEX" /></el-select></el-form-item><el-form-item label="同值展开次数"><el-input-number v-model="config.broadcastRepeat" :min="1" :max="1000" /></el-form-item><template v-if="config.valueMode === 'REPEAT_VALUE'"><el-form-item label="来源 Sheet"><el-input :model-value="valueSource().sheet" @update:model-value="updateValueSource({ sheet: $event })" /></el-form-item><el-form-item label="起始单元格"><ExcelCellAddressInput :row="valueSource().row" :column="valueSource().column" placeholder="A2" @change="updateValueAddress" /></el-form-item></template></div><div v-if="config.valueMode === 'CELL_PAIR'" class="excel-grid three"><el-form-item label="第一个列号"><el-input-number :model-value="pairColumns()[0]" :min="1" @update:model-value="updatePairColumn(0, $event)" /></el-form-item><el-form-item label="第二个列号"><el-input-number :model-value="pairColumns()[1]" :min="1" @update:model-value="updatePairColumn(1, $event)" /></el-form-item><el-form-item label="拼接分隔符"><el-input v-model="config.pairSeparator" placeholder="，" /></el-form-item></div><div v-if="config.valueMode === 'REPEAT_VALUE'" class="excel-grid two"><el-form-item label="来源行步长"><el-input-number :model-value="valueSource().rowStep" :min="0" @update:model-value="updateValueSource({ rowStep: $event })" /></el-form-item><el-form-item label="来源列步长"><el-input-number :model-value="valueSource().columnStep" :min="0" @update:model-value="updateValueSource({ columnStep: $event })" /></el-form-item></div><div v-if="config.valueMode === 'HORIZONTAL_CELL'" class="excel-grid three"><el-form-item label="横向列数来源"><el-select v-model="config.valueCountMode"><el-option label="按配置列数" value="CONFIGURED" /><el-option label="读取到首个空列" value="UNTIL_BLANK" /></el-select></el-form-item><el-form-item v-if="config.valueCountMode === 'CONFIGURED'" label="每组列数"><el-input-number v-model="config.valueCount" :min="1" :max="1000" /></el-form-item><el-form-item v-else label="最大扫描列数"><el-input-number v-model="config.maxValueCount" :min="1" :max="10000" /></el-form-item></div></section>
      <section class="excel-rule-section"><div class="excel-grid three"><el-form-item label="多个单元格拼接"><el-switch :model-value="config.valueMode === 'JOIN_CELLS'" @change="config.valueMode = $event ? 'JOIN_CELLS' : 'CELL'" /></el-form-item><el-form-item label="显示小数位"><el-input-number v-model="config.displayDecimals" :min="0" :max="10" /></el-form-item><el-form-item label="来源必填"><el-switch v-model="config.required" /></el-form-item></div><template v-if="config.valueMode === 'JOIN_CELLS'"><ExcelJoinSourcesEditor v-model="config.valueSources" /><el-form-item label="拼接分隔符"><el-input v-model="config.joinSeparator" /></el-form-item></template></section>
      <section class="excel-rule-section sequence"><div class="sequence-heading"><div><h3>序号生成</h3><small>用于 NO 等不直接读取单元格的字段</small></div><el-switch v-model="config.generateSequence" active-text="启用" /></div><div v-if="config.generateSequence" class="excel-grid two"><el-form-item label="序号依据字段"><el-select v-model="config.sequenceDependency" filterable><el-option v-for="field in fields" :key="field.fieldCode" :label="`${field.label} · ${field.fieldCode}`" :value="field.fieldCode" /></el-select></el-form-item><div class="sequence-note">仅对依据字段的非空值连续编号，每个重复组从 1 开始。</div></div></section>
    </template>
  </div>
</template>

<style scoped>
.excel-rule-editor{display:grid;gap:10px}.excel-rule-section{padding:12px 14px 2px;border:1px solid #dde5e1;background:#fafcfb}.excel-rule-section h3{margin:0 0 10px;color:#385248;font-size:12px}.excel-grid{display:grid;gap:0 10px}.excel-grid.base{grid-template-columns:2fr 1fr 1fr}.excel-grid.two{grid-template-columns:2fr 1fr}.excel-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.excel-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.excel-grid.five{grid-template-columns:repeat(5,minmax(0,1fr))}.excel-rule-section :deep(.el-form-item){margin-bottom:10px}.excel-rule-section :deep(.el-form-item__label){height:22px;padding:0;color:#61736c;font-size:10px;line-height:22px}.excel-rule-section :deep(.el-input-number),.excel-rule-section :deep(.el-select){width:100%}.sequence{padding-bottom:12px}.sequence-heading{display:flex;align-items:center;justify-content:space-between}.sequence-heading h3{margin-bottom:2px}.sequence-heading small,.sequence-note{color:#71817b;font-size:10px}.sequence-note{align-self:center;padding-top:12px;line-height:1.5}@media(max-width:760px){.excel-grid.base,.excel-grid.five,.excel-grid.four{grid-template-columns:repeat(2,minmax(0,1fr))}.excel-grid.two,.excel-grid.three{grid-template-columns:1fr}.excel-grid.base>:first-child{grid-column:1/-1}}
.region-list{display:grid;gap:8px;margin:8px 0}.region-item{display:grid;grid-template-columns:1fr 1.5fr 1.5fr repeat(3,minmax(80px,1fr)) auto;gap:8px;align-items:center;padding:8px;border:1px solid #e2e9e5;background:#fff}.region-item strong{font-size:11px;color:#53675e}.region-item :deep(.el-input-number){width:100%}@media(max-width:900px){.region-item{grid-template-columns:repeat(2,minmax(0,1fr))}.region-item strong{grid-column:1/-1}}
</style>
