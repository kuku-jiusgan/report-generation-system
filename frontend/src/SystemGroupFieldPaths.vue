<script setup lang="ts">
import type { SystemFieldGroup } from './admin-api'

const props = defineProps<{ group: SystemFieldGroup }>()

function standardPath(fieldPath: string) {
  const base = String(props.group.itemPath || '').trim()
  if (!base) return fieldPath
  const prefix = props.group.cardinality === 'MANY' ? `${base}[*]` : base
  return fieldPath ? `${prefix}.${fieldPath.replace(/\.\[\*\]/g, '[*]')}` : prefix
}
</script>

<template>
  <section class="path-preview-band">
    <div class="path-preview-head">
      <div><b>字段写入位置</b><small>这些是系统自动生成的路径，无需手动填写。</small></div>
      <el-tag size="small" type="info">只读预览</el-tag>
    </div>
    <div v-if="props.group.fields.length" class="path-preview-list">
      <div v-for="field in props.group.fields" :key="field.fieldCode" class="path-preview-row">
        <span>{{ field.label }}</span><code>{{ standardPath(field.fieldPath) }}</code>
      </div>
    </div>
    <p v-else class="path-preview-empty">当前编组暂无字段。</p>
  </section>
</template>

<style scoped>
.path-preview-band{margin-top:16px;padding:14px 16px;border:1px solid #dbe5ee;border-radius:8px;background:#f8fafc}.path-preview-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}.path-preview-head b,.path-preview-head small{display:block}.path-preview-head b{color:#30483f;font-size:12px}.path-preview-head small{margin-top:3px;color:#7b8a84;font-size:10px}.path-preview-list{border:1px solid #e4ebf0;border-radius:6px;overflow:hidden;background:#fff}.path-preview-row{display:grid;grid-template-columns:minmax(120px,.7fr) minmax(0,1.8fr);gap:14px;align-items:center;min-height:36px;padding:5px 10px;border-top:1px solid #eef2f5}.path-preview-row:first-child{border-top:0}.path-preview-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#30483f;font-size:12px}.path-preview-row code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#426b9a;font:11px/1.4 Consolas,"SFMono-Regular",monospace}.path-preview-empty{margin:8px 0 2px;color:#8a9993;font-size:11px;text-align:center}
</style>
