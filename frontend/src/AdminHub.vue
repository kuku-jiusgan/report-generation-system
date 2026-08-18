<script setup lang="ts">
import { computed, ref } from 'vue'
import { Clock, Coin, Cpu, Document, Expand, Fold, Key, Setting, SwitchButton, User, Odometer } from '@element-plus/icons-vue'
import AdminPanel from './AdminPanel.vue'
import TemplateLibrary from './TemplateLibrary.vue'
import LimsFieldCatalog from './LimsFieldCatalog.vue'
import AdminOverviewView from './AdminOverviewView.vue'
import UserManagement from './UserManagement.vue'
import PermissionManagement from './PermissionManagement.vue'
import ReportHistoryManagement from './ReportHistoryManagement.vue'
import AiServiceSettings from './AiServiceSettings.vue'
import type { AdminTemplate, AdminTemplateVersion } from './admin-api'
import type { AuthUser } from './auth-api'

const props = defineProps<{ permissions: string[]; user: AuthUser }>()
const emit = defineEmits<{ logout: [] }>()
const can = (permission: string) => props.permissions.includes(permission)
const view = ref<'overview' | 'library' | 'designer' | 'lims-fields' | 'ai-service' | 'users' | 'permissions' | 'history'>('overview')
const activeTemplate = ref<AdminTemplate>()
const activeVersion = ref<AdminTemplateVersion>()
const sidebarHovered = ref(false)
const sidebarPinned = ref(false)
const sidebarExpanded = computed(() => sidebarHovered.value || sidebarPinned.value)

function openDesigner(template: AdminTemplate, version: AdminTemplateVersion) {
  activeTemplate.value = template
  activeVersion.value = version
  view.value = 'designer'
}
</script>

<template>
  <div v-if="view !== 'designer'" class="admin-shell" :class="{ 'sidebar-expanded': sidebarExpanded }">
    <aside class="admin-sidebar" @mouseenter="sidebarHovered = true" @mouseleave="sidebarHovered = false">
      <div class="admin-sidebar-compact">
        <span class="admin-compact-brand"><Setting /></span>
        <nav class="admin-compact-nav">
          <button :class="{ active: view === 'overview' }" title="系统概览" @click="view = 'overview'"><Odometer /></button>
          <button v-if="can('RULES_MANAGE')" :class="{ active: view === 'library' }" title="报告模板与规则" @click="view = 'library'"><Document /></button>
          <button v-if="can('LIMS_FIELDS_MANAGE')" :class="{ active: view === 'lims-fields' }" title="系统标准字段" @click="view = 'lims-fields'"><Coin /></button>
          <button v-if="can('RULES_MANAGE')" :class="{ active: view === 'ai-service' }" title="AI 服务配置" @click="view = 'ai-service'"><Cpu /></button>
          <button v-if="can('USERS_MANAGE')" :class="{ active: view === 'users' }" title="用户管理" @click="view = 'users'"><User /></button>
          <button v-if="can('PERMISSIONS_MANAGE')" :class="{ active: view === 'permissions' }" title="权限管理" @click="view = 'permissions'"><Key /></button>
          <button v-if="can('REPORT_HISTORY_VIEW')" :class="{ active: view === 'history' }" title="报告生成历史" @click="view = 'history'"><Clock /></button>
        </nav>
        <button class="admin-collapse-button" type="button" title="固定展开菜单" aria-label="固定展开菜单" @click.stop="sidebarPinned = true"><Expand /></button>
        <span class="admin-session-avatar">{{ props.user.displayName.slice(0, 1) }}</span>
      </div>
      <div class="admin-sidebar-wide">
       <div class="admin-brand"><span class="admin-brand-icon"><Setting /></span><span><strong>后台管理系统</strong><small>报告自动生成系统</small></span></div>
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
          <span><strong>系统标准字段</strong><small>字段目录与统一来源规则</small></span>
        </button>
        <button v-if="can('RULES_MANAGE')" :class="{ active: view === 'ai-service' }" @click="view = 'ai-service'">
          <Cpu /><span><strong>AI 服务配置</strong><small>接口、模型与连接测试</small></span>
        </button>
        <button v-if="can('USERS_MANAGE')" :class="{ active: view === 'users' }" @click="view = 'users'"><User /><span><strong>用户管理</strong><small>账号、角色与状态</small></span></button>
        <button v-if="can('PERMISSIONS_MANAGE')" :class="{ active: view === 'permissions' }" @click="view = 'permissions'"><Key /><span><strong>权限管理</strong><small>角色权限矩阵</small></span></button>
        <button v-if="can('REPORT_HISTORY_VIEW')" :class="{ active: view === 'history' }" @click="view = 'history'"><Clock /><span><strong>报告生成历史</strong><small>生成记录与历史文件</small></span></button>
       </nav>
       <button class="admin-collapse-button wide" type="button" title="收起菜单" aria-label="收起菜单" @click.stop="sidebarPinned = false; sidebarHovered = false"><Fold /><span>收起菜单</span></button>
       <div class="admin-session">
        <span class="admin-session-avatar">{{ props.user.displayName.slice(0, 1) }}</span>
        <span class="admin-session-copy"><strong>{{ props.user.displayName }}</strong><small>{{ props.user.username }}</small></span>
        <button class="admin-session-exit" type="button" aria-label="退出登录" title="退出登录" @click="emit('logout')"><SwitchButton /></button>
       </div>
      </div>
    </aside>

    <section class="admin-module">
      <AdminOverviewView v-if="view === 'overview'" />
      <TemplateLibrary v-else-if="view === 'library'" @open="openDesigner" />
      <LimsFieldCatalog v-else-if="view === 'lims-fields'" />
      <AiServiceSettings v-else-if="view === 'ai-service'" />
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
  grid-template-columns: 72px minmax(0, 1fr);
  color: #263731;
  background: #f4f7fb;
  overflow: hidden;
  transition: grid-template-columns 240ms ease;
}
.admin-shell.sidebar-expanded {
  grid-template-columns: 220px minmax(0, 1fr);
}
.admin-sidebar {
  position: relative;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #617289;
  background: linear-gradient(180deg, #eaf4ff, #e0effb);
  border-right: 1px solid #dbe9f6;
  transition: box-shadow 240ms ease;
}
.sidebar-expanded .admin-sidebar { box-shadow: 12px 0 26px rgba(31,67,111,.12); }
.admin-brand {
  min-height: 72px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  gap: var(--admin-space-md);
  border-bottom: 1px solid #dbe9f6;
  white-space: nowrap;
}
.admin-brand-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  color: #2167e8;
  background: #ffffff;
  border-radius: 10px;
  box-shadow: 0 8px 20px rgba(9,47,127,.12);
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
.admin-brand > span:last-child,
.admin-nav-label,
.admin-nav button > span,
.admin-session-copy { display: none; }
.sidebar-expanded .admin-brand > span:last-child,
.sidebar-expanded .admin-nav-label,
.sidebar-expanded .admin-nav button > span,
.sidebar-expanded .admin-session-copy { display: block; }
.admin-brand strong {
  font-size: 15px;
}
.admin-brand small {
  margin-top: var(--admin-space-xs);
  color: #8290a3;
  font-size: 11px;
}
.admin-nav {
  padding: var(--admin-space-xl) 12px;
  display: flex;
  flex-direction: column;
  gap: var(--admin-space-xs);
}
.admin-nav-label {
  margin: 0 var(--admin-space-sm) var(--admin-space-sm);
  color: #8290a3;
  font-size: 11px;
}
.admin-nav button,
.admin-exit {
  width: 100%;
  border: 0;
  color: #617289;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: color 180ms ease-out, background-color 180ms ease-out;
}
.admin-nav button {
  width: 46px;
  min-height: 42px;
  margin: 0 auto;
  padding: 0;
  display: grid;
  place-items: center;
  align-items: center;
  gap: var(--admin-space-md);
  border-radius: 10px;
}
.sidebar-expanded .admin-nav button { width: 100%; margin: 0; padding: 0 12px; grid-template-columns: 24px minmax(0,1fr); place-items: center start; }
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
  color: #8290a3;
  font-size: 10px;
}
.admin-nav button:hover,
.admin-nav button:focus-visible {
  color: #2167e8;
  background: rgba(255,255,255,.7);
  outline: none;
}
.admin-nav button.active {
  position: relative;
  color: #2167e8;
  background: #fff;
  box-shadow: 0 6px 18px rgba(31,93,175,.12);
}
.admin-nav button.active:before { content: ""; position: absolute; left: -12px; width: 3px; height: 22px; background: #2167e8; border-radius: 0 4px 4px 0; }
.admin-nav button.active > svg {
  color: #2167e8;
}
.admin-nav button.active small {
  color: #8290a3;
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
  grid-template-columns: 32px;
  justify-content: center;
  align-items: center;
  gap: var(--admin-space-sm);
  border-top: 1px solid #dbe9f6;
}
.sidebar-expanded .admin-session { grid-template-columns: 32px minmax(0,1fr) 36px; justify-content: stretch; }
.admin-session-exit { display: none !important; }
.sidebar-expanded .admin-session-exit { display: grid !important; }
.admin-session-avatar {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg,#2d73ed,#6559e8);
  border-radius: 50%;
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
.admin-session-copy strong { color: #344158; font-size: 12px; font-weight: 600; }
.admin-session-copy small { margin-top: 3px; color: #8290a3; font-size: 10px; }
.admin-session-exit {
  width: 36px;
  height: 36px;
  padding: 0;
  display: grid;
  place-items: center;
  color: #617289;
  border: 0;
  background: transparent;
  border-radius: 9px;
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
.admin-sidebar-compact,
.admin-sidebar-wide { position: absolute; inset: 0; min-height: 100%; display: flex; flex-direction: column; }
.admin-sidebar-compact { width: 72px; align-items: center; gap: 8px; padding: 14px 10px; opacity: 1; visibility: visible; transition: opacity .08s ease .14s, visibility 0s .14s; }
.admin-sidebar-wide { width: 220px; gap: 8px; padding: 14px 12px; opacity: 0; visibility: hidden; transition: opacity .1s ease, visibility 0s .1s; }
.sidebar-expanded .admin-sidebar-compact { opacity: 0; visibility: hidden; transition: opacity .07s ease, visibility 0s .07s; }
.sidebar-expanded .admin-sidebar-wide { opacity: 1; visibility: visible; transition: opacity .11s ease .14s, visibility 0s .14s; }
.admin-compact-brand { width: 44px; height: 44px; flex: 0 0 44px; display: grid; place-items: center; color: #2167e8; background: #fff; border-radius: 11px; box-shadow: 0 8px 20px rgba(9,47,127,.12); }
.admin-compact-brand svg { width: 19px; }
.admin-compact-nav { width: 100%; min-height: 0; overflow: hidden auto; display: flex; flex-direction: column; gap: 5px; padding: 8px 0; }
.admin-compact-nav button { position: relative; flex: 0 0 42px; width: 46px; height: 42px; margin: 0 auto; padding: 0; display: grid; place-items: center; color: #617289; background: transparent; border: 0; border-radius: 10px; cursor: pointer; }
.admin-compact-nav button svg { width: 18px; }
.admin-compact-nav button.active { color: #2167e8; background: #fff; box-shadow: 0 6px 18px rgba(31,93,175,.12); }
.admin-compact-nav button.active::before { content: ""; position: absolute; left: -10px; width: 3px; height: 22px; background: #2167e8; border-radius: 0 4px 4px 0; }
.admin-sidebar-wide .admin-brand { min-height: 46px; padding: 0 2px; border-bottom: 0; }
.admin-sidebar-wide .admin-brand-icon { width: 44px; height: 44px; flex-basis: 44px; }
.admin-sidebar-wide .admin-brand > span:last-child,
.admin-sidebar-wide .admin-nav-label,
.admin-sidebar-wide .admin-nav button > span,
.admin-sidebar-wide .admin-session-copy { display: block; }
.admin-sidebar-wide .admin-nav { min-height: 0; overflow: hidden auto; padding: 8px 0; }
.admin-sidebar-wide .admin-nav button { width: 100%; margin: 0; padding: 0 12px; grid-template-columns: 24px minmax(0,1fr); place-items: center start; }
.admin-collapse-button { flex: 0 0 38px; width: 46px; height: 38px; margin-top: auto; padding: 0; display: flex; align-items: center; justify-content: center; gap: 8px; color: #60738a; background: rgba(255,255,255,.65); border: 0; border-radius: 9px; cursor: pointer; }
.admin-collapse-button:hover { color: #2167e8; background: #fff; }
.admin-collapse-button svg { width: 17px; }
.admin-collapse-button.wide { width: 100%; margin-top: auto; }
.admin-collapse-button.wide span { font-size: 12px; }
.admin-sidebar-compact > .admin-session-avatar { flex: 0 0 32px; }
.admin-sidebar-wide .admin-session { min-height: 52px; margin-top: 0; padding: 8px 4px 0; grid-template-columns: 32px minmax(0,1fr) 36px; justify-content: stretch; }
.admin-sidebar-wide .admin-session-exit { display: grid !important; }
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
