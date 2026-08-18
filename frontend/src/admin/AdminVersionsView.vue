<script setup lang="ts">
import { DocumentChecked } from '@element-plus/icons-vue'
import type { RuleVersion } from '../admin-api'

defineProps<{ versions: RuleVersion[] }>()
defineEmits<{ publish: [] }>()
</script>

<template>
  <main class="management-page">
    <div class="management-heading">
      <h1>模板与规则版本</h1>
      <el-button type="primary" @click="$emit('publish')">发布当前草稿</el-button>
    </div>
    <div class="version-list">
      <article v-for="item in versions" :key="item.id">
        <span>V{{ item.versionNo }}</span>
        <div>
          <h2>{{ item.note }}</h2>
          <p>{{ new Date(item.createdAt).toLocaleString('zh-CN') }} · 映射 {{ item.validationReport.statistics?.mapped ?? '未校验' }}</p>
        </div>
        <el-tag :type="item.status === 'PUBLISHED' ? 'success' : 'info'">
          {{ item.status === 'PUBLISHED' ? '已发布' : item.status === 'DRAFT' ? '草稿' : '历史版本' }}
        </el-tag>
      </article>
      <div v-if="!versions.length" class="version-empty"><DocumentChecked /><h2>还没有模板版本</h2></div>
    </div>
  </main>
</template>

<style scoped>
.management-page { height: calc(100vh - 64px); padding: 28px 34px; overflow: auto; }
.management-heading { max-width: 1250px; margin: 0 auto 20px; display: flex; align-items: flex-end; justify-content: space-between; }
.management-heading h1 { margin: 0; color: #263548; font-size: 23px; }
.version-list { max-width: 1250px; margin: 0 auto; display: grid; gap: 9px; }
.version-list article { padding: 16px; display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; align-items: center; gap: 14px; background: #fff; border: 1px solid #dae1de; }
.version-list article > span { width: 42px; height: 42px; display: grid; place-items: center; color: #fff; background: #246554; border-radius: 50%; font-size: 10px; }
.version-list h2 { margin: 0; color: #2c453e; font-size: 13px; }
.version-list p { margin: 6px 0; color: #808c87; font-size: 9px; }
.version-empty { padding: 70px; color: #78857f; background: #fff; border: 1px solid #dce2df; text-align: center; }
</style>
