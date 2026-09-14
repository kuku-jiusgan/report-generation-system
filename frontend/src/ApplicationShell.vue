<script setup lang="ts">
import { computed, ref } from 'vue'
import { DocumentChecked, Expand, Fold, SwitchButton } from '@element-plus/icons-vue'
import type { AuthUser } from './auth-api'
import type { ApplicationModule, ApplicationModuleId } from './application-menu'

const props = defineProps<{
  active: ApplicationModuleId
  modules: ApplicationModule[]
  user: AuthUser
}>()
const emit = defineEmits<{ select: [id: ApplicationModuleId]; logout: [] }>()
const expanded = ref(false)
const reportModules = computed(() => props.modules.filter((item) => item.group === 'reports'))
const systemModules = computed(() => props.modules.filter((item) => item.group === 'system'))
</script>

<template>
  <div class="application-shell" :class="{ expanded }">
    <aside class="application-sidebar">
      <header class="application-brand">
        <span><DocumentChecked /></span>
        <div><strong>智检报告系统</strong><small>报告自动生成系统</small></div>
      </header>

      <nav class="application-nav" aria-label="系统功能菜单">
        <template v-if="reportModules.length">
          <p>报告工作</p>
          <el-tooltip v-for="item in reportModules" :key="item.id" :content="item.label" placement="right" :disabled="expanded">
            <button :class="{ active: active === item.id }" :aria-current="active === item.id ? 'page' : undefined" @click="emit('select', item.id)">
              <component :is="item.icon" />
              <span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
            </button>
          </el-tooltip>
        </template>
        <template v-if="systemModules.length">
          <p>系统管理</p>
          <el-tooltip v-for="item in systemModules" :key="item.id" :content="item.label" placement="right" :disabled="expanded">
            <button :class="{ active: active === item.id }" :aria-current="active === item.id ? 'page' : undefined" @click="emit('select', item.id)">
              <component :is="item.icon" />
              <span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
            </button>
          </el-tooltip>
        </template>
      </nav>

      <button class="sidebar-toggle" type="button" :title="expanded ? '收起菜单' : '展开菜单'" @click="expanded = !expanded">
        <Fold v-if="expanded" /><Expand v-else /><span>{{ expanded ? '收起菜单' : '展开菜单' }}</span>
      </button>
      <footer class="application-session">
        <span class="session-avatar">{{ user.displayName.slice(0, 1) }}</span>
        <div><strong>{{ user.displayName }}</strong><small>{{ user.username }}</small></div>
        <button type="button" aria-label="退出登录" title="退出登录" @click="emit('logout')"><SwitchButton /></button>
      </footer>
    </aside>
    <section class="application-content"><slot /></section>
  </div>
</template>

<style scoped>
.application-shell{width:100%;height:100vh;min-width:1120px;display:grid;grid-template-columns:72px minmax(0,1fr);color:#263548;background:#f4f7fb;overflow:hidden;transition:grid-template-columns 240ms ease-out}
.application-shell.expanded{grid-template-columns:232px minmax(0,1fr)}
.application-sidebar{min-height:0;padding:14px 10px 10px;display:flex;flex-direction:column;overflow:hidden;color:#607087;background:#e8f2fb;border-right:1px solid #d7e5f2;transition:box-shadow 240ms ease-out}
.expanded .application-sidebar{padding-inline:12px;box-shadow:10px 0 28px rgba(31,67,111,.1)}
.application-brand{height:46px;display:grid;grid-template-columns:44px minmax(0,1fr);align-items:center;gap:10px;white-space:nowrap}
.application-brand>span{width:44px;height:44px;display:grid;place-items:center;color:#2167e8;background:#fff;border-radius:8px;box-shadow:0 8px 20px rgba(9,47,127,.12)}
.application-brand svg{width:20px}.application-brand div{display:none;min-width:0}.expanded .application-brand div{display:block}
.application-brand strong,.application-brand small{display:block;overflow:hidden;text-overflow:ellipsis}.application-brand strong{font-size:14px}.application-brand small{margin-top:3px;color:#74849a;font-size:10px}
.application-nav{min-height:0;margin-top:12px;padding:0;display:flex;flex:1;flex-direction:column;gap:4px;overflow-x:hidden;overflow-y:auto}
.application-nav p{display:none;margin:16px 8px 5px;color:#718299;font-size:10px;font-weight:600}.expanded .application-nav p{display:block}
.application-nav :deep(.el-tooltip__trigger){flex:0 0 auto}
.application-nav button{position:relative;width:46px;height:42px;margin:0 auto;padding:0;display:grid;place-items:center;color:#607087;background:transparent;border:0;border-radius:8px;cursor:pointer;transition:color 160ms ease-out,background-color 160ms ease-out,box-shadow 160ms ease-out}
.expanded .application-nav button{width:100%;padding:0 11px;grid-template-columns:24px minmax(0,1fr);place-items:center start;gap:10px;text-align:left}
.application-nav button:hover,.application-nav button:focus-visible{color:#2167e8;background:rgba(255,255,255,.72);outline:2px solid transparent}
.application-nav button.active{color:#2167e8;background:#fff;box-shadow:0 6px 18px rgba(31,93,175,.12)}
.application-nav button.active::before{content:"";position:absolute;left:-12px;width:3px;height:22px;background:#2167e8;border-radius:0 4px 4px 0}
.application-nav svg{width:18px}.application-nav button>span{display:none;min-width:0}.expanded .application-nav button>span{display:block}
.application-nav strong,.application-nav small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.application-nav strong{font-size:12px}.application-nav small{margin-top:3px;color:#7b899c;font-size:9px}
.sidebar-toggle{flex:0 0 38px;width:46px;margin:8px auto 0;padding:0;display:flex;align-items:center;justify-content:center;gap:8px;color:#607087;background:rgba(255,255,255,.62);border:0;border-radius:8px;cursor:pointer}.expanded .sidebar-toggle{width:100%}.sidebar-toggle:hover{color:#2167e8;background:#fff}.sidebar-toggle svg{width:17px}.sidebar-toggle span{display:none;font-size:12px}.expanded .sidebar-toggle span{display:inline}
.application-session{min-height:52px;margin-top:8px;padding-top:9px;display:grid;grid-template-columns:34px;justify-content:center;align-items:center;gap:7px;border-top:1px solid #d7e5f2}.expanded .application-session{grid-template-columns:34px minmax(0,1fr) 32px;justify-content:stretch}
.session-avatar{width:34px;height:34px;display:grid;place-items:center;color:#fff;background:#356fdb;border-radius:50%;font-size:12px;font-weight:700}.application-session div,.application-session>button{display:none}.expanded .application-session div,.expanded .application-session>button{display:block}
.application-session strong,.application-session small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.application-session strong{font-size:11px}.application-session small{margin-top:3px;color:#74849a;font-size:9px}
.application-session>button{width:32px;height:32px;padding:0;color:#607087;background:transparent;border:0;border-radius:8px;cursor:pointer}.application-session>button:hover,.application-session>button:focus-visible{color:#2167e8;background:#fff;outline:2px solid transparent}.application-session>button svg{width:17px}
.application-content{min-width:0;min-height:0;overflow:hidden}
@media(prefers-reduced-motion:reduce){.application-shell,.application-sidebar,.application-nav button{transition:none}}
</style>
