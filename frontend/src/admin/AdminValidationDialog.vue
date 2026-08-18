<script setup lang="ts">
import type { ValidationReport } from '../admin-api'
defineProps<{ validation?: ValidationReport }>()
const open = defineModel<boolean>('open', { required: true })
</script>

<template>
  <el-dialog v-model="open" title="模板校验" width="760px">
    <el-result v-if="validation" :icon="validation.valid ? 'success' : 'error'"
      :title="validation.valid ? '校验通过，可以发布' : `发现 ${validation.errors.length} 个错误`"
      :sub-title="`成功定位 ${validation.statistics.mapped} 项，警告 ${validation.warnings.length} 项`" />
    <el-alert v-if="validation && !validation.valid" type="error" :closable="false"
      title="以下规则阻止发布" class="validation-errors">
      <div v-for="(item, index) in validation.errors" :key="`${item.code}-${item.locationId}-${index}`" class="validation-error">
        <b>{{ item.fieldCode || item.locationId || '未命名规则' }}</b>
        <code>{{ item.code }}</code>
        <span>{{ item.message || '校验失败' }}</span>
      </div>
    </el-alert>
    <el-alert v-if="validation?.warnings.length" type="warning" :closable="false"
      title="校验警告" class="validation-errors">
      <div v-for="(item, index) in validation.warnings" :key="`warning-${item.code}-${index}`" class="validation-error">
        <b>{{ item.fieldCode || item.locationId || '未命名规则' }}</b><span>{{ item.message || item.code }}</span>
      </div>
    </el-alert>
    <template #footer><el-button @click="open = false">关闭</el-button></template>
  </el-dialog>
</template>

<style scoped>
.validation-errors { margin-top: 12px; }
.validation-error { display: grid; grid-template-columns: minmax(150px, 1fr) auto 2fr; gap: 10px; padding: 7px 0; align-items: start; }
.validation-error + .validation-error { border-top: 1px solid var(--el-border-color-lighter); }
.validation-error b, .validation-error span { overflow-wrap: anywhere; }
.validation-error code { color: var(--el-color-danger); }
</style>
