<script setup lang="ts">
import { computed } from 'vue'
import { Check, Coin, Cpu, DocumentChecked, MagicStick } from '@element-plus/icons-vue'

const props = defineProps<{ visible: boolean; stage: number; percentage: number; title: string; status: 'running' | 'success' | 'error'; message: string }>()
const stages = [
  { name: '整理数据源', detail: '合并实验记录与附件', icon: Coin },
  { name: '解析标准字段', detail: '校验编组与记录关系', icon: Cpu },
  { name: '生成智能内容', detail: '生成概述、目的等内容', icon: MagicStick },
  { name: '编译 Word 报告', detail: '填充字段并保持模板格式', icon: DocumentChecked },
]
const headline = computed(() => props.status === 'success' ? '报告已生成' : props.status === 'error' ? '报告生成未完成' : stages[Math.min(props.stage, 3)].name)
</script>

<template>
  <transition name="generation-fade">
    <section v-if="visible" class="generation-panel" :class="status" role="status" aria-live="polite">
      <header>
        <div class="generation-mark" :class="status"><el-icon><Check v-if="status === 'success'" /><MagicStick v-else /></el-icon></div>
        <div class="generation-summary"><b>{{ headline }}</b><p>{{ title || '新报告' }}<i />{{ message }}</p></div>
        <strong>{{ status === 'success' ? '已完成' : status === 'error' ? '生成失败' : '请保持页面开启' }}</strong>
      </header>
      <div class="generation-progress"><i :style="{ width: `${percentage}%` }" /></div>
      <div class="generation-meta"><span>报告生成进度</span><strong>{{ percentage }}%</strong></div>
      <ol class="generation-stages">
        <li v-for="(item, index) in stages" :key="item.name" :class="{ active: index === stage && status === 'running', done: index < stage || status === 'success' }">
          <span><el-icon><Check v-if="index < stage || status === 'success'" /><component :is="item.icon" v-else /></el-icon></span>
          <div><b>{{ item.name }}</b><small>{{ item.detail }}</small></div>
        </li>
      </ol>
    </section>
  </transition>
</template>

<style scoped>
.generation-panel{margin:0 0 18px;padding:16px 18px;border:1px solid #d8e4f1;border-radius:8px;background:#f7faff;color:#263b52}.generation-panel.success{border-color:#cce7da;background:#f4faf7}.generation-panel.error{border-color:#efd5d5;background:#fff8f8}.generation-panel header{display:flex;align-items:center;gap:12px}.generation-panel header>strong{margin-left:auto;flex:0 0 auto;color:#55718f;font-size:11px}.generation-panel.success header>strong{color:#217b55}.generation-panel.error header>strong{color:#ad4747}.generation-mark{position:relative;width:38px;height:38px;display:grid;place-items:center;flex:0 0 38px;border-radius:8px;background:#e3efff;color:#2167c7;font-size:18px}.generation-mark.running:before,.generation-mark.running:after{content:"";position:absolute;inset:-5px;border-radius:50%}.generation-mark.running:before{border:2px solid #c4d8ee}.generation-mark.running:after{padding:2px;background:conic-gradient(from 0deg,#1559b6 0deg,#3f82d5 90deg,#8eb9e8 180deg,#d4e3f3 270deg,#1559b6 360deg);-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude;animation:generationSpin 1.15s linear infinite}.generation-mark.success{background:#def3e8;color:#1b8758}.generation-mark.error{background:#f9e2e2;color:#b74747}.generation-summary{min-width:0}.generation-summary b,.generation-summary p{display:block;margin:0}.generation-summary b{font-size:14px}.generation-summary p{display:flex;align-items:center;gap:8px;min-width:0;margin-top:4px;color:#60748b;font-size:12px}.generation-summary p i{width:3px;height:3px;flex:0 0 3px;border-radius:50%;background:#9baabd}.generation-progress{height:5px;overflow:hidden;margin-top:14px;border-radius:4px;background:#dfe7f0}.generation-progress i{display:block;height:100%;border-radius:4px;background:#2474b7;transition:width .7s ease}.generation-meta{display:flex;justify-content:space-between;margin-top:7px;color:#718493;font-size:11px}.generation-meta strong{color:#315d7e}.generation-stages{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0 0;padding:0;list-style:none}.generation-stages li{min-width:0;display:flex;align-items:center;gap:7px;color:#8693a4}.generation-stages li>span{width:24px;height:24px;display:grid;place-items:center;flex:0 0 24px;border-radius:50%;background:#e7ecf2;color:#7d8998;font-size:11px}.generation-stages li b,.generation-stages li small{display:block}.generation-stages li b{font-size:11px}.generation-stages li small{margin-top:2px;font-size:10px;line-height:1.35}.generation-stages li.active{color:#255f9f}.generation-stages li.active>span{background:#2167c7;color:#fff}.generation-stages li.done{color:#2c7858}.generation-stages li.done>span{background:#dff2e8;color:#217b55}.generation-fade-enter-active,.generation-fade-leave-active{transition:opacity .2s cubic-bezier(.25,1,.5,1),transform .2s cubic-bezier(.25,1,.5,1)}.generation-fade-enter-from,.generation-fade-leave-to{opacity:0;transform:translateY(-6px)}@keyframes generationSpin{to{transform:rotate(360deg)}}@media(max-width:680px){.generation-panel header{align-items:flex-start}.generation-panel header>strong{display:none}.generation-summary p{align-items:flex-start;flex-direction:column;gap:3px}.generation-summary p i{display:none}.generation-stages{grid-template-columns:1fr 1fr;gap:10px}}@media(prefers-reduced-motion:reduce){.generation-mark.running:after{animation:none}.generation-fade-enter-active,.generation-fade-leave-active{transition:none}}
</style>
