<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Connection, Refresh, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { adminApi, type AiServiceConfig } from './admin-api'

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const config = reactive<AiServiceConfig>({
  baseUrl: '', model: '', timeout: 60, apiKeyConfigured: false, apiKeyMasked: '', apiKey: '',
})

function errorText(error: any) {
  return error?.response?.data?.detail || error?.message || '请求失败'
}
async function load() {
  loading.value = true
  try { Object.assign(config, await adminApi.aiServiceConfig(), { apiKey: '' }) }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { loading.value = false }
}
async function save() {
  if (!config.baseUrl.trim() || !config.model.trim()) return ElMessage.warning('请填写接口地址和模型')
  saving.value = true
  try {
    Object.assign(config, await adminApi.saveAiServiceConfig(config), { apiKey: '' })
    ElMessage.success('AI 服务配置已保存')
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { saving.value = false }
}
async function test() {
  testing.value = true
  try {
    const result = await adminApi.testAiServiceConfig()
    ElMessage.success(`连接成功：${result.output}`)
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { testing.value = false }
}
onMounted(load)
</script>

<template>
  <div class="ai-settings" v-loading="loading">
    <header><div><Setting /><span><strong>AI 服务配置</strong><small>模型接口与连接状态</small></span></div><el-button :icon="Refresh" @click="load">刷新</el-button></header>
    <main>
      <el-form label-position="top">
        <el-form-item label="OpenAI 兼容接口地址"><el-input v-model="config.baseUrl" placeholder="例如 https://api.example.com/v1" /></el-form-item>
        <div class="form-row">
          <el-form-item label="模型"><el-input v-model="config.model" placeholder="模型名称" /></el-form-item>
          <el-form-item label="请求超时（秒）"><el-input-number v-model="config.timeout" :min="5" :max="300" controls-position="right" /></el-form-item>
        </div>
        <el-form-item label="API Key">
          <el-input v-model="config.apiKey" type="password" show-password :placeholder="config.apiKeyConfigured ? `已配置 ${config.apiKeyMasked}；留空保持不变` : '请输入 API Key'" autocomplete="new-password" />
        </el-form-item>
        <div class="status-line"><el-tag :type="config.apiKeyConfigured ? 'success' : 'warning'">{{ config.apiKeyConfigured ? '密钥已配置' : '密钥未配置' }}</el-tag></div>
        <footer><el-button :icon="Connection" :loading="testing" :disabled="!config.apiKeyConfigured" @click="test">测试连接</el-button><el-button type="primary" :loading="saving" @click="save">保存配置</el-button></footer>
      </el-form>
    </main>
  </div>
</template>

<style scoped>
.ai-settings{height:100%;background:#f4f7fb;color:#263731}.ai-settings>header{height:72px;padding:0 24px;display:flex;align-items:center;justify-content:space-between;background:#fff;border-bottom:1px solid #dce5ee}.ai-settings>header>div{display:flex;align-items:center;gap:12px}.ai-settings>header svg{width:24px;color:#2167e8}.ai-settings strong,.ai-settings small{display:block}.ai-settings small{margin-top:3px;color:#718096;font-size:11px}.ai-settings main{max-width:780px;padding:28px}.ai-settings form{padding:24px;background:#fff;border:1px solid #dce5ee;border-radius:8px}.form-row{display:grid;grid-template-columns:2fr 1fr;gap:16px}.status-line{margin-bottom:24px}.ai-settings footer{display:flex;justify-content:flex-end;gap:8px}
</style>
