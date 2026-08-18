<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ config: Record<string, unknown> }>();
const location = computed(() => props.config.workbookLocation as Record<string, unknown> | undefined);
</script>

<template>
  <el-descriptions v-if="location" title="工作簿定位" :column="1" border class="excel-location">
    <el-descriptions-item label="工作簿格式">{{ config.workbookFormat || "-" }}</el-descriptions-item>
    <el-descriptions-item label="来源 Sheet">{{ location.sheet || "-" }}</el-descriptions-item>
    <el-descriptions-item label="匹配维度">{{ location.matchBy || "-" }}</el-descriptions-item>
    <el-descriptions-item label="取值列">{{ location.valueColumn || "-" }}</el-descriptions-item>
    <el-descriptions-item label="单元格范围">{{ location.cells || "-" }}</el-descriptions-item>
  </el-descriptions>
</template>
