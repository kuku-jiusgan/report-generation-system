<script setup lang="ts">
import AiServiceSettings from './AiServiceSettings.vue'
import LimsFieldCatalog from './LimsFieldCatalog.vue'
import PermissionManagement from './PermissionManagement.vue'
import ReportHistoryManagement from './ReportHistoryManagement.vue'
import TemplateLibrary from './TemplateLibrary.vue'
import UserManagement from './UserManagement.vue'
import type { AdminTemplate, AdminTemplateVersion } from './admin-api'
import type { ApplicationModuleId } from './application-menu'

defineProps<{ view: ApplicationModuleId; permissions: string[] }>()
const emit = defineEmits<{ openDesigner: [template: AdminTemplate, version: AdminTemplateVersion] }>()

function openDesigner(template: AdminTemplate, version: AdminTemplateVersion) {
  emit('openDesigner', template, version)
}
</script>

<template>
  <TemplateLibrary v-if="view === 'templates'" @open="openDesigner" />
  <LimsFieldCatalog v-else-if="view === 'standard-fields'" />
  <AiServiceSettings v-else-if="view === 'ai-service'" />
  <UserManagement v-else-if="view === 'users'" />
  <PermissionManagement v-else-if="view === 'permissions'" />
  <ReportHistoryManagement v-else-if="view === 'history'" :can-download="permissions.includes('REPORT_HISTORY_DOWNLOAD')" />
</template>
