<script setup lang="ts">
import { ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { downloadProtocolDocument, type ReportData } from './api'

defineProps<{ data: ReportData }>()
const loading = ref(false)

async function download(data: ReportData) {
  loading.value = true
  try {
    await downloadProtocolDocument(data)
  } catch (error) {
    console.error('[报告方案] 下载失败', error)
    ElMessage.error('方案下载失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div v-if="data.source_payloads?.PROTOCOL_DOCUMENT" class="protocol-attachment">
    <strong>Word 方案</strong>
    <span>{{ data.source_payloads.PROTOCOL_DOCUMENT.fileName }}</span>
    <el-button :icon="Download" :loading="loading" @click="download(data)">下载方案</el-button>
  </div>
</template>

<style scoped>
.protocol-attachment { display: grid; gap: 8px; padding: 12px 0; }
.protocol-attachment span { overflow-wrap: anywhere; color: var(--el-text-color-regular); font-size: 13px; }
.protocol-attachment .el-button { justify-self: start; }
</style>
