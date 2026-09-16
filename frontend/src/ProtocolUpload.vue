<script setup lang="ts">
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, type UploadFile } from 'element-plus'

const model = defineModel<File | undefined>()
const files = ref<UploadFile[]>([])

function selectFile(file: UploadFile) {
  if (!file.raw) return
  if (!file.name.toLowerCase().endsWith('.docx')) {
    files.value = []
    model.value = undefined
    ElMessage.error('方案仅支持 DOCX 格式，请将 Word 文件另存为 DOCX 后上传')
    return
  }
  model.value = file.raw
  files.value = [file]
}
</script>

<template>
  <section class="create-report-section">
    <header><div><strong>上传方案（可选）</strong></div></header>
    <el-upload v-model:file-list="files" drag accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" :auto-upload="false" :limit="1" :on-change="selectFile" :on-remove="() => { model = undefined }" :on-exceed="() => ElMessage.warning('仅支持上传一份方案，请先移除已选文件')">
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text"><em>选择 DOCX 文件</em></div>
    </el-upload>
  </section>
</template>
