<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { DocumentChecked, Lock, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { changePassword, currentUser, login, logout, type AuthUser } from './auth-api'
import zbriLogo from './assets/zbri-logo.png'

const props = defineProps<{ title: string; subtitle: string; requiredPermission: string; portal: 'report' | 'admin' }>()
const user = ref<AuthUser>()
const loading = ref(true)
const submitting = ref(false)
const username = ref('')
const password = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const formError = ref('')
const denied = computed(() => user.value && !user.value.permissions.includes(props.requiredPermission))
const portalCopy = computed(() => props.portal === 'admin' ? {
  name: '后台管理系统',
  heading: '让规则、权限与报告历史\n始终清晰可控',
  description: '统一管理报告模板、LIMS 标准字段、系统用户与生成记录，为报告生产提供稳定可信的配置基础。',
  promise: '统一配置 · 分级授权 · 全程留痕',
} : {
  name: '报告生成工作台',
  heading: '让每一份实验报告\n都有数据可循',
  description: '从 LIMS 数据识别、标准字段映射到 Word 报告生成，构建准确、规范、可追溯的报告生产流程。',
  promise: '标准提取 · 证据可追溯 · 版本可回溯',
})

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } }; message?: string }
  return value.response?.data?.detail || value.message || '操作失败，请稍后重试'
}

async function loadSession() {
  loading.value = true
  try { user.value = await currentUser(props.portal) } catch { user.value = undefined }
  finally { loading.value = false }
}

async function handleLogin() {
  if (!username.value.trim() || !password.value) return
  submitting.value = true
  formError.value = ''
  try {
    user.value = await login(username.value.trim(), password.value, props.portal)
    password.value = ''
  } catch (error) { formError.value = errorText(error) }
  finally { submitting.value = false }
}

async function handlePasswordChange() {
  formError.value = ''
  if (newPassword.value !== confirmPassword.value) {
    formError.value = '两次输入的新密码不一致'
    return
  }
  submitting.value = true
  try {
    user.value = await changePassword(currentPassword.value, newPassword.value, props.portal)
    currentPassword.value = ''; newPassword.value = ''; confirmPassword.value = ''
    ElMessage.success('密码已修改')
  } catch (error) { formError.value = errorText(error) }
  finally { submitting.value = false }
}

async function handleLogout() {
  await logout(props.portal).catch(() => undefined)
  user.value = undefined
  formError.value = ''
}

onMounted(() => { window.addEventListener('auth-expired', loadSession); void loadSession() })
onUnmounted(() => window.removeEventListener('auth-expired', loadSession))
</script>

<template>
  <main v-if="loading" class="auth-loading" aria-live="polite">
    <span><DocumentChecked /></span><p>正在验证登录状态…</p>
  </main>

  <main v-else-if="!user || user.mustChangePassword || denied" class="auth-page">
    <section class="auth-brand" aria-label="报告自动生成系统介绍">
      <div class="brand-product"><span><DocumentChecked /></span><strong>报告自动生成系统</strong></div>
      <div class="brand-copy">
        <p>{{ portalCopy.name }}</p>
        <h1>{{ portalCopy.heading }}</h1>
        <div>{{ portalCopy.description }}</div>
      </div>
      <div class="brand-promise"><strong>{{ portalCopy.promise }}</strong><span>山东大学淄博生物医药研究院</span></div>
      <div class="brand-orbit" aria-hidden="true"><i /><i /><i /></div>
    </section>

    <section class="auth-panel">
      <div class="auth-form-wrap">
        <img class="institute-logo" :src="zbriLogo" alt="山东大学淄博生物医药研究院" />

        <template v-if="!user">
          <header class="form-heading"><h2>欢迎登录</h2><p>{{ title }}</p></header>
          <el-alert v-if="formError" :title="formError" type="error" show-icon :closable="false" />
          <el-form class="auth-form" label-position="top" @submit.prevent="handleLogin">
            <el-form-item label="账号">
              <el-input v-model="username" size="large" autocomplete="username" placeholder="请输入账号" :prefix-icon="User" autofocus @input="formError = ''" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="password" size="large" type="password" autocomplete="current-password" show-password placeholder="请输入密码" :prefix-icon="Lock" @input="formError = ''" />
            </el-form-item>
            <el-button class="auth-submit" type="primary" size="large" native-type="submit" :loading="submitting" :disabled="!username.trim() || !password">登录</el-button>
          </el-form>
          <p class="account-note"><Lock />账号由系统管理员统一开通和授权</p>
        </template>

        <template v-else-if="user.mustChangePassword">
          <header class="form-heading"><h2>设置新密码</h2><p>首次登录需要修改临时密码，完成后即可进入系统。</p></header>
          <el-alert v-if="formError" :title="formError" type="error" show-icon :closable="false" />
          <el-form class="auth-form" label-position="top" @submit.prevent="handlePasswordChange">
            <el-form-item label="当前密码"><el-input v-model="currentPassword" size="large" type="password" autocomplete="current-password" show-password :prefix-icon="Lock" /></el-form-item>
            <el-form-item label="新密码"><el-input v-model="newPassword" size="large" type="password" autocomplete="new-password" show-password placeholder="至少 8 个字符" :prefix-icon="Lock" /></el-form-item>
            <el-form-item label="确认新密码"><el-input v-model="confirmPassword" size="large" type="password" autocomplete="new-password" show-password :prefix-icon="Lock" /></el-form-item>
            <el-button class="auth-submit" type="primary" size="large" native-type="submit" :loading="submitting" :disabled="!currentPassword || newPassword.length < 8 || !confirmPassword">修改密码并进入系统</el-button>
          </el-form>
        </template>

        <template v-else>
          <div class="access-denied"><span><Lock /></span><h2>无权访问此入口</h2><p>账号 <strong>{{ user.displayName }}</strong> 没有访问{{ portalCopy.name }}的权限，请联系系统管理员调整角色。</p><el-button size="large" @click="handleLogout">退出当前账号</el-button></div>
        </template>
      </div>
      <footer>© 2026 山东大学淄博生物医药研究院</footer>
    </section>
  </main>

  <div v-else class="authenticated-app">
    <slot :user="user" :logout="handleLogout" />
  </div>
</template>

<style scoped>
.auth-loading{min-height:100vh;display:grid;place-content:center;justify-items:center;gap:14px;color:#4d615a;background:#f5f7f6}.auth-loading span{width:48px;height:48px;display:grid;place-items:center;color:#fff;background:#174b3f;border-radius:12px;animation:auth-pulse 1.5s ease-in-out infinite}.auth-loading svg{width:24px}.auth-loading p{margin:0;font-size:13px}.auth-page{min-height:100vh;display:grid;grid-template-columns:minmax(560px,1.16fr) minmax(440px,.84fr);font-family:"Inter","PingFang SC","Microsoft YaHei",sans-serif;color:#23352f;background:#fff}.auth-brand{position:relative;isolation:isolate;overflow:hidden;min-height:100vh;padding:48px 64px;color:#fff;background:radial-gradient(circle at 78% 18%,rgba(208,174,112,.42),transparent 25%),radial-gradient(circle at 4% 84%,rgba(63,142,118,.7),transparent 29%),linear-gradient(138deg,#0c342c 0%,#145345 58%,#257562 100%)}.brand-product{position:relative;z-index:2;display:flex;align-items:center;gap:12px}.brand-product span{width:40px;height:40px;display:grid;place-items:center;color:#19493e;background:#f2d3a0;border-radius:9px}.brand-product svg{width:21px}.brand-product strong{font-size:16px;font-weight:650}.brand-copy{position:relative;z-index:2;max-width:650px;margin-top:clamp(110px,16vh,180px)}.brand-copy>p{margin:0;color:#d9bd8f;font-size:14px;font-weight:650}.brand-copy h1{max-width:620px;margin:18px 0 22px;white-space:pre-line;font-size:48px;line-height:1.3;letter-spacing:-.025em;text-wrap:balance}.brand-copy>div{max-width:610px;color:#d7e8e2;font-size:17px;line-height:1.85;text-wrap:pretty}.brand-promise{position:absolute;z-index:2;left:64px;bottom:58px;display:flex;flex-direction:column;gap:8px}.brand-promise strong{font-size:15px}.brand-promise span{color:#b7d3ca;font-size:12px}.brand-orbit i{position:absolute;z-index:1;border:1px solid rgba(255,255,255,.14);border-radius:50%}.brand-orbit i:nth-child(1){width:620px;height:620px;right:-220px;top:48px}.brand-orbit i:nth-child(2){width:380px;height:380px;right:-10px;top:178px}.brand-orbit i:nth-child(3){width:11px;height:11px;right:166px;top:286px;border:0;background:#f0cf98;box-shadow:0 0 0 7px rgba(240,207,152,.15)}.auth-panel{min-height:100vh;padding:44px 56px 28px;display:flex;flex-direction:column;justify-content:center;align-items:center;background:#fff}.auth-form-wrap{width:min(100%,380px);margin:auto}.institute-logo{display:block;width:100%;max-width:310px;height:auto;margin:0 0 34px}.form-heading{margin-bottom:28px}.form-heading h2{margin:0 0 8px;color:#1e302a;font-size:30px;letter-spacing:-.02em}.form-heading p{margin:0;color:#66756f;font-size:14px;line-height:1.7}.auth-form{margin-top:22px}.auth-form :deep(.el-form-item){margin-bottom:20px}.auth-form :deep(.el-form-item__label){padding-bottom:7px;color:#344740;font-size:13px;font-weight:600}.auth-form :deep(.el-input__wrapper){min-height:48px;padding:1px 14px;background:#f7f9f8;box-shadow:0 0 0 1px #d8e0dc inset;border-radius:8px;transition:box-shadow 180ms ease,background-color 180ms ease}.auth-form :deep(.el-input__wrapper:hover){box-shadow:0 0 0 1px #9cb4ab inset}.auth-form :deep(.el-input__wrapper.is-focus){background:#fff;box-shadow:0 0 0 2px #246252 inset}.auth-form :deep(.el-input__inner::placeholder){color:#687771}.auth-submit{width:100%;height:48px;margin-top:6px;font-size:15px;font-weight:650;--el-button-bg-color:#246252;--el-button-border-color:#246252;--el-button-hover-bg-color:#2e7562;--el-button-hover-border-color:#2e7562;--el-button-active-bg-color:#174b3f;--el-button-active-border-color:#174b3f}.auth-panel :deep(.el-alert){margin-bottom:4px;border-radius:8px}.account-note{margin:22px 0 0;display:flex;align-items:center;justify-content:center;gap:6px;color:#63726c;font-size:12px}.account-note svg{width:13px;color:#246252}.auth-panel footer{margin-top:auto;color:#7b8782;font-size:11px}.access-denied{text-align:center}.access-denied>span{width:52px;height:52px;margin:0 auto 20px;display:grid;place-items:center;color:#8b5b18;background:#fbf1df;border-radius:12px}.access-denied svg{width:25px}.access-denied h2{margin:0 0 10px;font-size:25px}.access-denied p{margin:0 0 26px;color:#63726c;line-height:1.75}.authenticated-app{min-height:100vh}
.authenticated-app{width:100%;height:100%}
@keyframes auth-pulse{50%{transform:scale(.94);opacity:.72}}
@media(max-width:900px){.auth-page{grid-template-columns:1fr}.auth-brand{min-height:230px;padding:28px 32px}.brand-copy{margin-top:48px}.brand-copy>p,.brand-copy>div,.brand-promise{display:none}.brand-copy h1{margin:0;max-width:560px;font-size:32px;line-height:1.3}.brand-orbit i:nth-child(1){width:360px;height:360px;right:-140px;top:-50px}.brand-orbit i:nth-child(2){display:none}.auth-panel{min-height:calc(100vh - 230px);padding:38px 24px 24px}.institute-logo{max-width:270px;margin-bottom:25px}.auth-panel footer{margin-top:42px}}
@media(max-width:520px){.auth-brand{min-height:190px;padding:24px}.brand-product strong{font-size:14px}.brand-copy{margin-top:34px}.brand-copy h1{font-size:27px}.auth-panel{min-height:calc(100vh - 190px);padding:30px 22px 22px;justify-content:flex-start}.form-heading h2{font-size:26px}}
@media(prefers-reduced-motion:reduce){.auth-loading span{animation:none}.auth-form :deep(.el-input__wrapper){transition:none}}
</style>
