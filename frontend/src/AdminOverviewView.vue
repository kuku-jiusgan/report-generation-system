<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminApi, type AdminOverview } from './admin-api'
const overview = ref<AdminOverview>()
onMounted(async () => { overview.value = await adminApi.overview() })
</script>
<template>
  <section class="management-page" v-loading="!overview">
    <header><div><h1>系统概览</h1><p>报告配置、数据标准和运行状态</p></div></header>
    <div v-if="overview" class="metric-grid">
      <article><strong>{{ overview.mappingCount }}</strong><span>字段映射</span></article>
      <article><strong>{{ overview.enabledTables }}</strong><span>启用表格规则</span></article>
      <article><strong>{{ overview.pendingCount }}</strong><span>待完善配置</span></article>
      <article><strong>{{ overview.publishedVersion || '-' }}</strong><span>已发布版本</span></article>
    </div>
  </section>
</template>
