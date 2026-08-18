<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'
import type { DataSourceRule, LimsImport } from '../admin-api'
import { formatBytes, sourceTagType } from './designer-formatters'

defineProps<{ sources: DataSourceRule[]; limsImports: LimsImport[] }>()
defineEmits<{
  configure: [source: DataSourceRule]
  recognize: []
}>()

const sourceLabels: Record<string, string> = {
  FIXED: '模板固定内容', LIMS: 'LIMS 数据', PDF: 'PDF 文档', AI: '大模型生成',
  CALCULATED: '系统计算', MANUAL: '人工录入',
}
</script>

<template>
  <main class="management-page">
    <div class="management-heading">
      <h1>数据源与识别入口</h1>
      <el-button :disabled="!limsImports.length" @click="$emit('recognize')">使用 LIMS 数据试运行</el-button>
    </div>
    <div class="source-list">
      <article v-for="item in sources.filter((source) => source.sourceType !== 'MANUAL')" :key="item.code">
        <span class="source-symbol"><Connection /></span>
        <div>
          <h2>{{ item.name }}</h2>
          <p>{{ sourceLabels[item.sourceType] || '其他来源' }} · 优先级 {{ item.priority }} · {{ item.enabled ? '已启用' : '已停用' }}</p>
          <code>{{ item.code }}</code>
        </div>
        <el-tag :type="sourceTagType(item.sourceType) as any">{{ sourceLabels[item.sourceType] || '其他来源' }}</el-tag>
        <el-button @click="$emit('configure', item)">配置连接</el-button>
      </article>
    </div>
    <section class="lims-history">
      <h2>测试环境 LIMS 导入记录</h2>
      <el-table :data="limsImports" stripe>
        <el-table-column prop="fileName" label="文件" min-width="260" />
        <el-table-column label="SQL 行" width="100"><template #default="scope">{{ scope.row.summary.rowCount }}</template></el-table-column>
        <el-table-column label="实验实例" width="100"><template #default="scope">{{ scope.row.summary.instanceCount }}</template></el-table-column>
        <el-table-column label="大小" width="100"><template #default="scope">{{ formatBytes(scope.row.size) }}</template></el-table-column>
      </el-table>
    </section>
  </main>
</template>

<style scoped>
.management-page { height: calc(100vh - 64px); padding: 28px 34px; overflow: auto; }
.management-heading { max-width: 1250px; margin: 0 auto 20px; display: flex; align-items: flex-end; justify-content: space-between; }
.management-heading h1 { margin: 0; color: #263548; font-size: 23px; }
.source-list, .lims-history { max-width: 1250px; margin: 0 auto; }
.source-list { display: grid; gap: 9px; }
.source-list article { padding: 16px; display: grid; grid-template-columns: 42px minmax(0, 1fr) auto auto; align-items: center; gap: 14px; background: #fff; border: 1px solid #dae1de; }
.source-symbol { width: 42px; height: 42px; display: grid; place-items: center; color: #fff; background: #2c7d69; }
.source-list h2, .lims-history h2 { margin: 0; color: #2c453e; font-size: 13px; }
.source-list p { margin: 5px 0; color: #7c8883; font-size: 9px; }
.source-list code { color: #8f9995; font-size: 8px; }
.lims-history { margin-top: 18px; padding: 18px; background: #fff; border: 1px solid #dae1de; }
.lims-history :deep(.el-table) { margin-top: 14px; }
</style>
