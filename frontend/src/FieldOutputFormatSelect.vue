<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ modelValue?: string; dataType?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const numeric = Array.from({ length: 7 }, (_, value) => ({ value: String(value), label: `固定 ${value} 位小数` }));
const options = computed(() => {
  if (props.dataType === "decimal") return [{ value: "", label: "保持原始精度" }, ...numeric];
  if (props.dataType === "date") return [
    { value: "", label: "默认日期格式" }, { value: "%Y-%m-%d", label: "年-月-日（2026-08-13）" },
    { value: "%Y/%m/%d", label: "年/月/日（2026/08/13）" }, { value: "%Y年%m月%d日", label: "中文日期（2026年08月13日）" },
  ];
  return [{ value: "", label: "不格式化" }];
});
const selectedOptions = computed(() => options.value.some((item) => item.value === props.modelValue)
  ? options.value : [{ value: props.modelValue || "", label: `现有格式：${props.modelValue}` }, ...options.value]);
</script>

<template>
  <el-select :model-value="modelValue || ''" @update:model-value="emit('update:modelValue', $event)">
    <el-option v-for="item in selectedOptions" :key="item.value" :label="item.label" :value="item.value" />
  </el-select>
</template>
