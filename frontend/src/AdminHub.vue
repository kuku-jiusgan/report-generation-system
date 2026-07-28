<script setup lang="ts">
import { ref } from 'vue'
import { Clock, Coin, Document, Key, Setting, SwitchButton, User, Odometer } from '@element-plus/icons-vue'
import AdminPanel from './AdminPanel.vue'
import TemplateLibrary from './TemplateLibrary.vue'
import LimsFieldCatalog from './LimsFieldCatalog.vue'
import AdminOverviewView from './AdminOverviewView.vue'
import UserManagement from './UserManagement.vue'
import PermissionManagement from './PermissionManagement.vue'
import ReportHistoryManagement from './ReportHistoryManagement.vue'
import type { AdminTemplate, AdminTemplateVersion } from './admin-api'
import type { AuthUser } from './auth-api'

const props = defineProps<{ permissions: string[]; user: AuthUser }>()
const emit = defineEmits<{ logout: [] }>()
const can = (permission: string) => props.permissions.includes(permission)
const view = ref<'overview' | 'library' | 'designer' | 'lims-fields' | 'users' | 'permissions' | 'history'>('overview')
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
        <span><strong>后台管理系统</strong><small>报告自动生成系统</small></span>
      </div>

      <nav class="admin-nav" aria-label="后台管理菜单">
        <span class="admin-nav-label">系统管理</span>
        <button :class="{ active: view === 'overview' }" @click="view = 'overview'"><Odometer /><span><strong>系统概览</strong><small>配置与运行状态</small></span></button>
        <button v-if="can('RULES_MANAGE')"
          :class="{ active: view === 'library' }"
          :aria-current="view === 'library' ? 'page' : undefined"
          @click="view = 'library'"
        >
          <Document />
          <span><strong>报告模板与规则</strong><small>模板、版本与字段映射</small></span>
        </button>
        <button v-if="can('LIMS_FIELDS_MANAGE')"
          :class="{ active: view === 'lims-fields' }"
          :aria-current="view === 'lims-fields' ? 'page' : undefined"
          @click="view = 'lims-fields'"
        >
          <Coin />
          <span><strong>LIMS 标准字段</strong><small>字段字典与提取规则</small></span>
        </button>
        <button v-if="can('USERS_MANAGE')" :class="{ active: view === 'users' }" @click="view = 'users'"><User /><span><strong>用户管理</strong><small>账号、角色与状态</small></span></button>
        <button v-if="can('PERMISSIONS_MANAGE')" :class="{ active: view === 'permissions' }" @click="view = 'permissions'"><Key /><span><strong>权限管理</strong><small>角色权限矩阵</small></span></button>
        <button v-if="can('REPORT_HISTORY_VIEW')" :class="{ active: view === 'history' }" @click="view = 'history'"><Clock /><span><strong>报告生成历史</strong><small>生成记录与历史文件</small></span></button>
      </nav>

      <div class="admin-session">
        <span class="admin-session-avatar">{{ props.user.displayName.slice(0, 1) }}</span>
        <span class="admin-session-copy"><strong>{{ props.user.displayName }}</strong><small>{{ props.user.username }}</small></span>
        <button class="admin-session-exit" type="button" aria-label="退出登录" title="退出登录" @click="emit('logout')"><SwitchButton /></button>
      </div>
    </aside>

    <section class="admin-module">
      <AdminOverviewView v-if="view === 'overview'" />
      <TemplateLibrary v-else-if="view === 'library'" @open="openDesigner" />
      <LimsFieldCatalog v-else-if="view === 'lims-fields'" />
      <UserManagement v-else-if="view === 'users'" />
      <PermissionManagement v-else-if="view === 'permissions'" />
      <ReportHistoryManagement v-else />
    </section>
  </div>
  <AdminPanel
    v-else
    :catalog-template="activeTemplate"
    :catalog-version="activeVersion"
    :session-user="props.user"
    @back="view = 'library'"
    @logout="emit('logout')"
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
.admin-session {
  margin-top: auto;
  min-height: 64px;
  padding: var(--admin-space-md);
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) 36px;
  align-items: center;
  gap: var(--admin-space-sm);
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}
.admin-session-avatar {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  color: #173f36;
  background: #d4ad72;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
}
.admin-session-copy,
.admin-session-copy strong,
.admin-session-copy small {
  min-width: 0;
  display: block;
}
.admin-session-copy strong,
.admin-session-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.admin-session-copy strong { color: #eef5f3; font-size: 12px; font-weight: 600; }
.admin-session-copy small { margin-top: 3px; color: #93afa6; font-size: 10px; }
.admin-session-exit {
  width: 36px;
  height: 36px;
  padding: 0;
  display: grid;
  place-items: center;
  color: #c9d8d3;
  border: 1px solid #52756d;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: color 180ms ease-out, background-color 180ms ease-out, border-color 180ms ease-out;
}
.admin-session-exit svg { width: 17px; }
.admin-session-exit:hover,
.admin-session-exit:focus-visible {
  color: #fff;
  border-color: #8eaaa3;
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
  .admin-session-exit { transition: none; }
}
</style>
