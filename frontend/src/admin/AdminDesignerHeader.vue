<script setup lang="ts">
import { ArrowLeft, Check, Connection, DocumentChecked, EditPen, Setting, SwitchButton } from '@element-plus/icons-vue'

export type AdminWorkspaceMode = 'designer' | 'sources' | 'versions'
defineProps<{
  workspace: AdminWorkspaceMode
  templateName?: string
  publishedVersion?: number
  userName: string
  validating: boolean
  publishing: boolean
}>()
defineEmits<{
  back: []; logout: []; validate: []; publish: []; workspace: [mode: AdminWorkspaceMode]
}>()
</script>

<template>
  <el-button class="library-back" :icon="ArrowLeft" @click="$emit('back')">模板库</el-button>
  <header class="designer-header">
    <div class="designer-brand"><Setting /><strong>报告模板设计器</strong></div>
    <div class="template-switcher">
      <span>报告模板</span>
      <el-select model-value="primary-report-template" disabled><el-option :label="templateName || '正在读取模板…'" value="primary-report-template" /></el-select>
      <el-tag type="warning" effect="plain">草稿</el-tag>
      <el-tag v-if="publishedVersion" type="success" effect="plain">已发布 V{{ publishedVersion }}</el-tag>
    </div>
    <nav class="header-modes">
      <button :class="{ active: workspace === 'designer' }" @click="$emit('workspace', 'designer')"><EditPen />模板设计</button>
      <button :class="{ active: workspace === 'sources' }" @click="$emit('workspace', 'sources')"><Connection />数据源</button>
      <button :class="{ active: workspace === 'versions' }" @click="$emit('workspace', 'versions')"><DocumentChecked />版本记录</button>
    </nav>
    <div class="header-actions">
      <el-button :icon="Check" :loading="validating" @click="$emit('validate')">校验</el-button>
      <el-button type="primary" :loading="publishing" @click="$emit('publish')">发布版本</el-button>
      <span class="designer-session-user">{{ userName }}</span>
      <el-button :icon="SwitchButton" @click="$emit('logout')">退出</el-button>
    </div>
  </header>
</template>

<style scoped>
.designer-header { height: 64px; padding: 0 18px; display: flex; align-items: center; gap: 20px; color: #fff; background: linear-gradient(110deg, #0739aa, #2775ed); border-bottom: 1px solid rgba(255,255,255,.18); }
.designer-brand { width: 245px; display: flex; align-items: center; gap: 10px; }
.designer-brand > svg { width: 25px; }
.designer-brand strong { font-size: 14px; }
.template-switcher { display: flex; align-items: center; gap: 8px; color: #b8cac5; font-size: 10px; }
.template-switcher .el-select { width: 190px; }
.template-switcher :deep(.el-select__wrapper) { min-height: 31px; background: rgba(255,255,255,.12); box-shadow: 0 0 0 1px rgba(255,255,255,.28) inset; }
.template-switcher :deep(.el-select__selected-item) { color: #fff; }
.header-modes { height: 100%; display: flex; align-items: stretch; gap: 2px; }
.header-modes button { padding: 0 11px; display: flex; align-items: center; gap: 6px; color: #b8cac5; border: 0; border-bottom: 2px solid transparent; background: transparent; font-size: 11px; cursor: pointer; }
.header-modes button.active { color: #fff; background: rgba(255,255,255,.12); border-bottom-color: #fff; }
.header-actions { margin-left: auto; display: flex; gap: 6px; }
.designer-session-user { margin-left: 6px; padding-left: 12px; display: flex; align-items: center; color: #d6e3df; border-left: 1px solid #52756d; font-size: 11px; font-weight: 600; white-space: nowrap; }
.header-actions :deep(.el-button) { margin: 0; border-color: #52756d; color: #ecf3f1; background: transparent; }
.header-actions :deep(.el-button--primary) { border-color: #fff; color: #2167e8; background: #fff; }
.library-back { position: fixed; z-index: 3; top: 16px; right: 388px; color: #eef5f3 !important; border-color: #52756d !important; background: transparent !important; }
@media (max-width: 1280px) { .template-switcher > span { display: none; } .header-modes button { padding: 0 8px; } }
</style>
