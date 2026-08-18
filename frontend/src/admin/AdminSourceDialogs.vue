<script setup lang="ts">
import type { DataSourceRule, LimsImport, LimsRecognitionTest } from '../admin-api'

defineProps<{ limsImports: LimsImport[]; testing: boolean; result?: LimsRecognitionTest }>()
defineEmits<{ saveSource: []; recognize: [] }>()
const sourceOpen = defineModel<boolean>('sourceOpen', { required: true })
const source = defineModel<DataSourceRule | undefined>('source', { required: true })
const sourceConfig = defineModel<string>('sourceConfig', { required: true })
const recognitionOpen = defineModel<boolean>('recognitionOpen', { required: true })
const recognitionResultOpen = defineModel<boolean>('recognitionResultOpen', { required: true })
const recognitionImport = defineModel<LimsImport | undefined>('recognitionImport', { required: true })
const recognitionIds = defineModel<string[]>('recognitionIds', { required: true })
</script>

<template>
  <el-dialog v-model="sourceOpen" title="数据源连接配置" width="640px">
    <el-form v-if="source" label-position="top">
      <div class="form-inline">
        <el-form-item label="名称"><el-input v-model="source.name" /></el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="source.priority" :min="1" /></el-form-item>
      </div>
      <el-form-item label="连接配置（JSON）"><el-input v-model="sourceConfig" type="textarea" :rows="12" /></el-form-item>
      <el-switch v-model="source.enabled" active-text="启用数据源" />
    </el-form>
    <template #footer><el-button @click="sourceOpen = false">取消</el-button><el-button type="primary" @click="$emit('saveSource')">保存配置</el-button></template>
  </el-dialog>

  <el-dialog v-model="recognitionOpen" title="选择 LIMS 试运行数据" width="760px">
    <el-form label-position="top"><el-form-item label="导入文件"><el-select v-model="recognitionImport" value-key="id"><el-option v-for="item in limsImports" :key="item.id" :label="item.fileName" :value="item" /></el-select></el-form-item></el-form>
    <el-checkbox-group v-if="recognitionImport" v-model="recognitionIds" class="recognition-picker">
      <el-checkbox v-for="instance in recognitionImport.summary.instances" :key="instance.instanceId" :value="instance.instanceId"><span>{{ instance.title }}</span><small>{{ instance.instanceId }} · {{ instance.rowCount }} 行</small></el-checkbox>
    </el-checkbox-group>
    <template #footer><el-button @click="recognitionOpen = false">取消</el-button><el-button type="primary" :disabled="!recognitionIds.length" :loading="testing" @click="$emit('recognize')">运行识别预览</el-button></template>
  </el-dialog>

  <el-dialog v-model="recognitionResultOpen" title="LIMS 识别试运行结果" width="760px">
    <div v-if="result" class="result-metrics">
      <span><b>{{ result.recognizedTotal }}</b>结构化记录</span><span><b>{{ result.coverage.recognizedTables }}</b>已识别表格</span><span><b>{{ result.duplicateCount }}</b>自动去重</span><span><b>{{ result.conflicts.length }}</b>待处理冲突</span>
    </div>
    <template #footer><el-button @click="recognitionResultOpen = false">关闭</el-button></template>
  </el-dialog>
</template>

<style scoped>
.form-inline { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.recognition-picker { max-height: 390px; display: grid; gap: 7px; overflow: auto; }
.recognition-picker :deep(.el-checkbox) { width: 100%; height: auto; margin: 0; padding: 10px; border: 1px solid #dce2df; }
.recognition-picker span, .recognition-picker small { display: block; }
.recognition-picker small { margin-top: 3px; color: #84908b; font-size: 9px; }
.result-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.result-metrics span { padding: 18px 10px; color: #72807a; background: #f1f6f4; text-align: center; }
.result-metrics b { display: block; color: #246554; font-size: 24px; }
</style>
