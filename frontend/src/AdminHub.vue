<script setup lang="ts">
import { ref } from 'vue'
import { ArrowLeft, Coin, Document, Setting } from '@element-plus/icons-vue'
import AdminPanel from './AdminPanel.vue'
import TemplateLibrary from './TemplateLibrary.vue'
import LimsFieldCatalog from './LimsFieldCatalog.vue'
import type { AdminTemplate, AdminTemplateVersion } from './admin-api'

defineEmits<{ exit: [] }>()
const view = ref<'library' | 'designer' | 'lims-fields'>('library')
const activeTemplate = ref<AdminTemplate>()
const activeVersion = ref<AdminTemplateVersion>()

function openDesigner(template: AdminTemplate, version: AdminTemplateVersion) {
  activeTemplate.value = template
  activeVersion.value = version
  view.value = 'designer'
}
</script>

<template>
  <div v-if="view !== 'designer'" class="admin-shell">
    <aside class="admin-sidebar">
      <div class="admin-brand">
        <span class="admin-brand-icon"><Setting /></span>
        <span><strong>规则后台</strong><small>报告生成系统</small></span>
      </div>

      <nav class="admin-nav" aria-label="后台管理菜单">
        <span class="admin-nav-label">规则管理</span>
        <button
          :class="{ active: view === 'library' }"
          :aria-current="view === 'library' ? 'page' : undefined"
          @click="view = 'library'"
        >
          <Document />
          <span><strong>报告模板规则</strong><small>模板、版本与字段映射</small></span>
        </button>
        <button
          :class="{ active: view === 'lims-fields' }"
          :aria-current="view === 'lims-fields' ? 'page' : undefined"
          @click="view = 'lims-fields'"
        >
          <Coin />
          <span><strong>LIMS 标准字段</strong><small>字段字典与提取规则</small></span>
        </button>
      </nav>

      <button class="admin-exit" @click="$emit('exit')">
        <ArrowLeft />
        <span>返回报告工作台</span>
      </button>
    </aside>

    <section class="admin-module">
      <TemplateLibrary v-if="view === 'library'" @open="openDesigner" />
      <LimsFieldCatalog v-else />
    </section>
  </div>
  <AdminPanel
    v-else
    :catalog-template="activeTemplate"
    :catalog-version="activeVersion"
    @back="view = 'library'"
    @exit="$emit('exit')"
  />
</template>

<style scoped>
.admin-shell {
  --admin-space-xs: 4px;
  --admin-space-sm: 8px;
  --admin-space-md: 12px;
  --admin-space-lg: 16px;
  --admin-space-xl: 24px;
  height: 100vh;
  min-width: 1120px;
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr);
  color: #263731;
  background: #edf0ee;
  overflow: hidden;
}
.admin-sidebar {
  min-height: 0;
  display: flex;
  flex-direction: column;
  color: #eef5f3;
  background: #123f36;
  border-right: 1px solid #31594f;
}
.admin-brand {
  min-height: 72px;
  padding: 0 var(--admin-space-lg);
  display: flex;
  align-items: center;
  gap: var(--admin-space-md);
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.admin-brand-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  color: #173f36;
  background: #d4ad72;
  border-radius: 6px;
}
.admin-brand-icon svg {
  width: 19px;
}
.admin-brand strong,
.admin-brand small,
.admin-nav button strong,
.admin-nav button small {
  display: block;
}
.admin-brand strong {
  font-size: 15px;
}
.admin-brand small {
  margin-top: var(--admin-space-xs);
  color: #abc1ba;
  font-size: 11px;
}
.admin-nav {
  padding: var(--admin-space-xl) var(--admin-space-md);
  display: flex;
  flex-direction: column;
  gap: var(--admin-space-xs);
}
.admin-nav-label {
  margin: 0 var(--admin-space-sm) var(--admin-space-sm);
  color: #93afa6;
  font-size: 11px;
}
.admin-nav button,
.admin-exit {
  width: 100%;
  border: 0;
  color: #c9d8d3;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: color 180ms ease-out, background-color 180ms ease-out;
}
.admin-nav button {
  min-height: 56px;
  padding: var(--admin-space-sm) var(--admin-space-md);
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: center;
  gap: var(--admin-space-md);
  border-radius: 6px;
}
.admin-nav button > svg,
.admin-exit > svg {
  width: 18px;
}
.admin-nav button strong {
  color: inherit;
  font-size: 13px;
  font-weight: 600;
}
.admin-nav button small {
  margin-top: var(--admin-space-xs);
  color: #97afa7;
  font-size: 10px;
}
.admin-nav button:hover,
.admin-nav button:focus-visible {
  color: #fff;
  background: rgba(255, 255, 255, 0.07);
  outline: none;
}
.admin-nav button.active {
  color: #fff;
  background: #246252;
}
.admin-nav button.active > svg {
  color: #e2bd83;
}
.admin-nav button.active small {
  color: #c5d7d1;
}
.admin-exit {
  min-height: 52px;
  margin-top: auto;
  padding: 0 var(--admin-space-xl);
  display: flex;
  align-items: center;
  gap: var(--admin-space-md);
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  font-size: 12px;
}
.admin-exit:hover,
.admin-exit:focus-visible {
  color: #fff;
  background: rgba(255, 255, 255, 0.07);
  outline: none;
}
.admin-module {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
@media (prefers-reduced-motion: reduce) {
  .admin-nav button,
  .admin-exit {
    transition: none;
  }
}
</style>
