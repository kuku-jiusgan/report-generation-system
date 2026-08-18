<script setup lang="ts">
import { Tickets } from '@element-plus/icons-vue'
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
    <div class="word-toolbar">
      <div class="breadcrumb"><span>{{ chapterLabel }}</span><i>/</i><b>{{ blockTitle }}</b></div>
      <div class="word-state" :class="linkState.toLowerCase()"><i />{{ linkState === 'READY' ? 'Word 双向定位已连接' : linkState === 'LIMITED' ? 'Word 可编辑，定位能力受限' : '正在连接 Word' }}</div>
    </div>
    <div class="word-canvas" v-loading="loading">
      <div id="admin-onlyoffice-editor" class="onlyoffice-editor" />
      <el-result v-if="error" icon="error" title="模板编辑器加载失败" :sub-title="error"><template #extra><el-button type="primary" @click="$emit('reload')">重新加载</el-button></template></el-result>
    </div>
    <footer class="word-footer"><b v-if="mapping"><Tickets />{{ mapping.wordLabel }} · {{ mapping.controlTag || '锚点待建立' }}</b></footer>
  </section>
</template>

<style scoped>
.word-panel { min-width: 0; display: grid; grid-template-rows: 42px minmax(0, 1fr) 28px; background: #e8eeeb; border-right: 1px solid #cfd8d4; }
.word-toolbar { padding: 0 13px; display: flex; align-items: center; justify-content: space-between; background: #fff; border-bottom: 1px solid #d9e0dd; }
.breadcrumb { display: flex; align-items: center; gap: 7px; min-width: 0; }
.breadcrumb span, .breadcrumb b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }
.breadcrumb span { color: #74817c; }.breadcrumb i { color: #adb6b2; }.breadcrumb b { color: #28443c; }
.word-state { display: flex; align-items: center; gap: 6px; color: #6f7d77; font-size: 9px; }
.word-state > i { width: 7px; height: 7px; border-radius: 50%; background: #c49b50; }
.word-state.ready > i { background: #3f9477; }.word-state.limited > i { background: #d69542; }
.word-canvas { min-height: 0; position: relative; background: #dce5e1; }
.onlyoffice-editor { position: absolute; inset: 0; }
.word-canvas > :deep(.el-result) { position: absolute; inset: 0; z-index: 2; background: #fff; }
.word-footer { padding: 0 12px; display: flex; align-items: center; color: #6d7b75; background: #fff; border-top: 1px solid #d9e0dd; font-size: 8px; }
.word-footer b { display: flex; align-items: center; gap: 5px; }.word-footer svg { width: 12px; }
</style>
