<script setup lang="ts">
import { computed } from "vue";
import ExcelCellAddressInput from "./ExcelCellAddressInput.vue";

type Source = Record<string, unknown>;
const props = defineProps<{ modelValue?: unknown }>();
const emit = defineEmits<{ "update:modelValue": [value: Source[]] }>();
const sources = computed<Source[]>(() => Array.isArray(props.modelValue) ? props.modelValue as Source[] : []);

function mode(source: Source): string {
  if ("literal" in source) return "literal";
  return "sheetSource" in source ? "dynamic" : "sheet";
}
function update(index: number, values: Source) {
  emit("update:modelValue", sources.value.map((source, position) =>
    position === index ? { ...source, ...values } : source));
}
function changeMode(index: number, value: string) {
  const source = value === "literal" ? { literal: "" } : {
    ...(value === "dynamic" ? { sheetSource: { sheet: "", row: 1, column: 1 } } : { sheet: "" }),
    row: 1, column: 1,
  };
  emit("update:modelValue", sources.value.map((item, position) => position === index ? source : item));
}
function changeSheetSource(index: number, values: Source) {
  update(index, { sheetSource: { ...(sources.value[index].sheetSource as Source || {}), ...values } });
}
function add() {
  emit("update:modelValue", [...sources.value, { sheet: "", row: 1, column: 1 }]);
}
function remove(index: number) {
  emit("update:modelValue", sources.value.filter((_, position) => position !== index));
}
</script>

<template>
  <div class="join-sources">
    <h3>拼接内容（按顺序）</h3>
    <div v-for="(source, index) in sources" :key="index" class="join-source">
      <div class="source-head">
        <strong>内容 {{ index + 1 }}</strong>
        <el-button type="danger" text size="small" @click="remove(index)">删除</el-button>
      </div>
      <div class="source-grid">
        <el-form-item label="内容来源">
          <el-select :model-value="mode(source)" @update:model-value="changeMode(index, $event)">
            <el-option label="固定文字" value="literal" />
            <el-option label="指定工作表" value="sheet" />
            <el-option label="从单元格读取工作表名称" value="dynamic" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="mode(source) === 'literal'" label="固定文字">
          <el-input :model-value="source.literal" placeholder="例如：技术员A" @update:model-value="update(index, { literal: $event })" />
        </el-form-item>
        <template v-else>
          <el-form-item v-if="mode(source) === 'sheet'" label="工作表">
            <el-input :model-value="source.sheet" placeholder="工作表名称" @update:model-value="update(index, { sheet: $event })" />
          </el-form-item>
          <template v-else>
            <el-form-item label="名称所在工作表">
              <el-input :model-value="(source.sheetSource as Source)?.sheet" placeholder="如：首页" @update:model-value="changeSheetSource(index, { sheet: $event })" />
            </el-form-item>
            <el-form-item label="名称所在单元格">
              <ExcelCellAddressInput :row="(source.sheetSource as Source)?.row" :column="(source.sheetSource as Source)?.column" placeholder="B9" @change="changeSheetSource(index, $event)" />
            </el-form-item>
            <el-form-item label="名称行步长">
              <el-input-number :model-value="(source.sheetSource as Source)?.rowStep ?? 0" :min="0" @update:model-value="changeSheetSource(index, { rowStep: $event })" />
            </el-form-item>
          </template>
          <el-form-item label="取值单元格">
            <ExcelCellAddressInput :row="source.row" :column="source.column" placeholder="A9" @change="update(index, $event)" />
          </el-form-item>
          <el-form-item label="取值行步长">
            <el-input-number :model-value="source.rowStep ?? 0" :min="0" @update:model-value="update(index, { rowStep: $event })" />
          </el-form-item>
          <el-form-item label="取值列步长">
            <el-input-number :model-value="source.columnStep ?? 0" :min="0" @update:model-value="update(index, { columnStep: $event })" />
          </el-form-item>
        </template>
      </div>
    </div>
    <el-button plain size="small" @click="add">添加拼接内容</el-button>
  </div>
</template>

<style scoped>
.join-sources{margin:4px 0 12px}.join-sources h3{margin:0 0 8px;color:#385248;font-size:12px}.join-source{margin-bottom:8px;padding:8px 10px;border:1px solid #e2e9e5;background:#fff}.source-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px;color:#53675e;font-size:11px}.source-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 10px}.source-grid :deep(.el-input-number),.source-grid :deep(.el-select){width:100%}@media(max-width:760px){.source-grid{grid-template-columns:1fr}}
</style>
