<script setup lang="ts">
import { ref } from 'vue'
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
  <TemplateLibrary v-if="view === 'library'" @open="openDesigner" @fields="view = 'lims-fields'" @exit="$emit('exit')" />
  <LimsFieldCatalog v-else-if="view === 'lims-fields'" @templates="view = 'library'" @exit="$emit('exit')" />
  <AdminPanel v-else :catalog-template="activeTemplate" :catalog-version="activeVersion" @back="view = 'library'" @exit="$emit('exit')" />
</template>
