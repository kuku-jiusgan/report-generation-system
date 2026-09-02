<script setup lang="ts">
import type { MappingRule } from '../admin-api'

defineProps<{
  chapterLabel: string
  blockTitle: string
  linkState: 'CONNECTING' | 'READY' | 'LIMITED'
  loading: boolean
  error: string
  mapping?: MappingRule
}>()
defineEmits<{ reload: [] }>()
</script>

<template>
  <section class="word-panel">
    <div class="word-canvas" v-loading="loading">
      <div id="admin-onlyoffice-editor" class="onlyoffice-editor" />
      <el-result v-if="error" icon="error" title="模板编辑器加载失败" :sub-title="error"><template #extra><el-button type="primary" @click="$emit('reload')">重新加载</el-button></template></el-result>
    </div>
  </section>
</template>

<style scoped>
.word-panel { min-width: 0; min-height: 0; height: 100%; overflow: hidden; background: #e8eeeb; border-right: 1px solid #cfd8d4; }
.word-canvas { width: 100%; height: 100%; min-height: 0; position: relative; background: #dce5e1; }
.onlyoffice-editor { position: absolute; inset: 0; }
.word-canvas > :deep(.el-result) { position: absolute; inset: 0; z-index: 2; background: #fff; }
</style>
