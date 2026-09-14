<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AdminPanel from './AdminPanel.vue'
import AdminWorkspace from './AdminWorkspace.vue'
import App from './App.vue'
import ApplicationShell from './ApplicationShell.vue'
import ReportHub from './ReportHub.vue'
import type { AdminTemplate, AdminTemplateVersion } from './admin-api'
import { availableApplicationModules, type ApplicationModuleId } from './application-menu'
import type { AuthUser } from './auth-api'

const props = defineProps<{ user: AuthUser }>()
const emit = defineEmits<{ logout: [] }>()
const activeReportId = ref<string>()
const activeTemplate = ref<AdminTemplate>()
const activeVersion = ref<AdminTemplateVersion>()
const modules = computed(() => availableApplicationModules(props.user.permissions))
const activeModuleStorageKey = `report-generation-system:active-module:${props.user.id}`

function readStoredActiveModule(): ApplicationModuleId {
  if (typeof window === 'undefined') return 'reports'

  try {
    const storedModule = window.localStorage.getItem(activeModuleStorageKey)
    const isAvailable = modules.value.some((item) => item.id === storedModule)
    return isAvailable ? (storedModule as ApplicationModuleId) : 'reports'
  } catch (error) {
    console.warn('读取上次菜单位置失败，将使用默认菜单', error)
    return 'reports'
  }
}

function persistActiveModule(module: ApplicationModuleId) {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.setItem(activeModuleStorageKey, module)
  } catch (error) {
    console.warn('保存菜单位置失败，本次刷新后可能无法恢复', error)
  }
}

const activeModule = ref<ApplicationModuleId>(readStoredActiveModule())

watch(modules, (items) => {
  if (!items.some((item) => item.id === activeModule.value)) activeModule.value = items[0].id
}, { immediate: true })

watch(activeModule, persistActiveModule)

function openDesigner(template: AdminTemplate, version: AdminTemplateVersion) {
  activeTemplate.value = template
  activeVersion.value = version
}
</script>

<template>
  <App
    v-if="activeReportId"
    :key="activeReportId"
    :session-user="user"
    :initial-report-id="activeReportId"
    @back="activeReportId = undefined"
    @logout="emit('logout')"
  />
  <AdminPanel
    v-else-if="activeTemplate && activeVersion"
    :catalog-template="activeTemplate"
    :catalog-version="activeVersion"
    :session-user="user"
    @back="activeTemplate = undefined; activeVersion = undefined"
    @logout="emit('logout')"
  />
  <ApplicationShell v-else :active="activeModule" :modules="modules" :user="user" @select="activeModule = $event" @logout="emit('logout')">
    <ReportHub v-if="activeModule === 'reports'" :session-user="user" @open="activeReportId = $event" />
    <AdminWorkspace v-else :view="activeModule" :permissions="user.permissions" @open-designer="openDesigner" />
  </ApplicationShell>
</template>
