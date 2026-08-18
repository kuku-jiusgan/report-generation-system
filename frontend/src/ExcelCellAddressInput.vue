<script setup lang="ts">
import { ref, watch } from "vue";
import { columnLetters, columnNumber } from "./excelWorkbookLocation";
const props = defineProps<{ row?: unknown; column?: unknown; placeholder?: string }>();
const emit = defineEmits<{ change: [value: { row: number; column: number }] }>();
const text = ref("");
watch(() => [props.row, props.column], () => { text.value = props.row && props.column ? `${columnLetters(Number(props.column))}${props.row}` : ""; }, { immediate: true });
function commit() { const match = text.value.trim().toUpperCase().match(/^([A-Z]+)(\d+)$/); if (match) emit("change", { column: columnNumber(match[1]), row: Number(match[2]) }); }
</script>
<template><el-input v-model="text" :placeholder="placeholder" @blur="commit" @keyup.enter="commit" /></template>
