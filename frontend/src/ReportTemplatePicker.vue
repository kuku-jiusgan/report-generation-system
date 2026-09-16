<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listReportTemplates } from './api'
import type { AdminTemplate } from './admin-api'

const model = defineModel<string>({ required: true })
const templates = ref<AdminTemplate[]>([])
const loading = ref(false)
const error = ref('')

async function loadTemplates() {
  loading.value = true
  error.value = ''
  model.value = ''
  try {
    templates.value = await listReportTemplates()
  } catch (cause) {
    console.error('[报告生成] 加载可用模板失败', cause)
    error.value = '报告模板加载失败，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadTemplates)
</script>

<template>
  <section class="report-template-picker">
    <label for="report-template-select">报告模板（必选）</label>
    <el-select id="report-template-select" v-model="model" aria-label="报告模板（必选）" filterable :loading="loading" :disabled="loading || Boolean(error)" :placeholder="loading ? '正在加载报告模板…' : '请选择报告模板'">
      <el-option v-for="item in templates" :key="item.id" :value="item.id" :label="`${item.name} · V${item.publishedVersion}`" />
    </el-select>
    <p v-if="error" role="alert">{{ error }} <el-button link type="primary" @click="loadTemplates">重新加载</el-button></p>
    <p v-else-if="!loading && !templates.length" role="status">暂无可用模板，请先在模板库中发布报告模板。</p>
  </section>
</template>

<style scoped>
.report-template-picker { margin-bottom: 24px; }
.report-template-picker label { display: block; margin-bottom: 8px; font-weight: 600; }
.report-template-picker .el-select { width: 100%; }
.report-template-picker p { margin: 8px 0 0; color: var(--el-text-color-regular); font-size: 13px; }
</style>
