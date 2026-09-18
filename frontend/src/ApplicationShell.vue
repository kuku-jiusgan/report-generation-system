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
const expanded = ref(true)
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
.application-shell{width:100%;height:100vh;display:grid;grid-template-columns:64px minmax(0,1fr);color:#202b3d;background:#f5f6f8;overflow:hidden;transition:grid-template-columns 180ms ease-out}
.application-shell.expanded{grid-template-columns:220px minmax(0,1fr)}
.application-sidebar{min-height:0;padding:12px 8px 10px;display:flex;flex-direction:column;overflow:hidden;color:#536075;background:#fff;border-right:1px solid #dfe3ea}
.expanded .application-sidebar{padding-inline:10px}
.application-brand{height:46px;display:grid;grid-template-columns:42px minmax(0,1fr);align-items:center;gap:9px;white-space:nowrap}
.application-brand>span{width:38px;height:38px;display:grid;place-items:center;color:#fff;background:#1456d9;border-radius:6px}
.application-brand svg{width:19px}.application-brand div{display:none;min-width:0}.expanded .application-brand div{display:block}
.application-brand strong,.application-brand small{display:block;overflow:hidden;text-overflow:ellipsis}.application-brand strong{color:#1f2a3d;font-size:14px;font-weight:650}.application-brand small{margin-top:2px;color:#5f6b7d;font-size:11px}
.application-nav{min-height:0;margin-top:10px;padding:0;display:flex;flex:1;flex-direction:column;gap:3px;overflow-x:hidden;overflow-y:auto}
.application-nav p{display:none;margin:16px 10px 5px;color:#5f6b7d;font-size:11px;font-weight:600}.expanded .application-nav p{display:block}
.application-nav :deep(.el-tooltip__trigger){flex:0 0 auto}
.application-nav button{position:relative;width:44px;height:40px;margin:0 auto;padding:0;display:grid;place-items:center;color:#5d697c;background:transparent;border:0;border-radius:5px;cursor:pointer;transition:color 140ms ease-out,background-color 140ms ease-out}
.expanded .application-nav button{width:100%;padding:0 10px;grid-template-columns:22px minmax(0,1fr);place-items:center start;gap:9px;text-align:left}
.application-nav button:hover,.application-nav button:focus-visible{color:#1456d9;background:#f1f4f9;outline:2px solid transparent}
.application-nav button:focus-visible{outline-color:#7aa4ee;outline-offset:-2px}
.application-nav button.active{color:#1456d9;background:#eaf1ff;box-shadow:inset 2px 0 #1456d9}
.application-nav svg{width:17px}.application-nav button>span{display:none;min-width:0}.expanded .application-nav button>span{display:block}
.application-nav strong,.application-nav small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.application-nav strong{font-size:12px;font-weight:600}.application-nav small{margin-top:2px;color:#5f6b7d;font-size:11px}
.sidebar-toggle{flex:0 0 36px;width:44px;margin:8px auto 0;padding:0;display:flex;align-items:center;justify-content:center;gap:8px;color:#68758a;background:transparent;border:0;border-radius:5px;cursor:pointer}.expanded .sidebar-toggle{width:100%}.sidebar-toggle:hover,.sidebar-toggle:focus-visible{color:#1456d9;background:#f1f4f9;outline:2px solid transparent}.sidebar-toggle:focus-visible{outline-color:#7aa4ee}.sidebar-toggle svg{width:16px}.sidebar-toggle span{display:none;font-size:12px}.expanded .sidebar-toggle span{display:inline}
.application-session{min-height:50px;margin-top:8px;padding-top:9px;display:grid;grid-template-columns:34px;justify-content:center;align-items:center;gap:7px;border-top:1px solid #e5e8ee}.expanded .application-session{grid-template-columns:34px minmax(0,1fr) 32px;justify-content:stretch}
.session-avatar{width:32px;height:32px;display:grid;place-items:center;color:#fff;background:#3e5f91;border-radius:50%;font-size:12px;font-weight:700}.application-session div,.application-session>button{display:none}.expanded .application-session div,.expanded .application-session>button{display:block}
.application-session strong,.application-session small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.application-session strong{color:#303c50;font-size:11px}.application-session small{margin-top:2px;color:#5f6b7d;font-size:11px}
.application-session>button{width:32px;height:32px;padding:0;color:#68758a;background:transparent;border:0;border-radius:5px;cursor:pointer}.application-session>button:hover,.application-session>button:focus-visible{color:#1456d9;background:#f1f4f9;outline:2px solid transparent}.application-session>button:focus-visible{outline-color:#7aa4ee}.application-session>button svg{width:16px}
.application-content{min-width:0;min-height:0;overflow:hidden}
@media(max-width:1180px){.application-shell,.application-shell.expanded{grid-template-columns:64px minmax(0,1fr)}.application-sidebar,.expanded .application-sidebar{padding-inline:8px}.expanded .application-brand div,.expanded .application-nav p,.expanded .application-nav button>span,.expanded .sidebar-toggle{display:none}.expanded .application-nav button{width:44px;padding:0;display:grid;grid-template-columns:1fr;place-items:center}.expanded .application-session{grid-template-columns:34px;grid-template-rows:34px 30px;justify-content:center}.expanded .application-session div{display:none}.expanded .application-session>button{display:block}.application-session{min-height:78px}}
@media(prefers-reduced-motion:reduce){.application-shell,.application-nav button{transition:none}}
</style>
