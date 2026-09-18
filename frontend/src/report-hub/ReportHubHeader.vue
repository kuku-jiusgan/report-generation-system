<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'

defineProps<{ canCreate: boolean; creating: boolean }>()
const emit = defineEmits<{ create: [] }>()
</script>

<template>
  <header class="hub-header">
    <div>
      <h1>报告管理大厅</h1>
      <p>集中查看、复核和交付检验报告</p>
    </div>
    <el-button
      v-if="canCreate"
      class="hub-create-button"
      type="primary"
      :icon="Plus"
      :loading="creating"
      @click="emit('create')"
    >
      新建报告
    </el-button>
  </header>
</template>
