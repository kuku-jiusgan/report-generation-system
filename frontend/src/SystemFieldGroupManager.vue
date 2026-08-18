<script setup lang="ts">
import { computed, ref } from 'vue'
import { FolderAdd } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { adminApi, type StandardField, type SystemFieldGroup } from './admin-api'

const props = defineProps<{ groups: SystemFieldGroup[]; fields: StandardField[]; chapters: Array<{ id: number; code: string; title: string }> }>()
const chapterOptions = computed(() => {
  const result: Array<{ id: number; code: string; title: string; depth: number }> = []
  const visit = (items: Array<{ id: number; code: string; title: string; children?: any[] }>, depth = 0) => {
    items.forEach((chapter) => {
      result.push({ id: chapter.id, code: chapter.code, title: chapter.title, depth })
      if (chapter.children?.length) visit(chapter.children, depth + 1)
    })
  }
  visit(props.chapters)
  return result
})
const emit = defineEmits<{ changed: [] }>()
const visible = ref(false); const busy = ref(false); const groupCode = ref(''); const label = ref(''); const cardinality = ref<'ONE' | 'MANY'>('ONE'); const selectedField = ref(''); const fieldPath = ref(''); const chapterGroupCode = ref(''); const selectedChapter = ref<number>(); const editGroupCode = ref(''); const editLabel = ref(''); const editCardinality = ref<'ONE' | 'MANY'>('ONE'); const editDescription = ref(''); const editOrderNo = ref(0)
async function createGroup() {
  if (!groupCode.value.trim() || !label.value.trim()) return ElMessage.warning('请输入编组编码和名称')
  busy.value = true
  try { await adminApi.createFieldGroup({ groupCode: groupCode.value.trim(), label: label.value.trim(), cardinality: cardinality.value }); ElMessage.success('编组已创建'); emit('changed'); groupCode.value = ''; label.value = '' }
  catch (error: any) { ElMessage.error(error?.response?.data?.detail || error?.message || '创建编组失败') }
  finally { busy.value = false }
}
function loadGroupForEdit(code: string) {
  const group = props.groups.find((item) => item.groupCode === code)
  if (!group) return
  editLabel.value = group.label; editCardinality.value = group.cardinality; editDescription.value = group.description; editOrderNo.value = group.orderNo
}
async function saveGroup() {
  const group = props.groups.find((item) => item.groupCode === editGroupCode.value)
  if (!group || !editLabel.value.trim()) return ElMessage.warning('请选择编组并填写名称')
  try { await adminApi.updateFieldGroup(group.groupCode, { label: editLabel.value.trim(), cardinality: editCardinality.value, description: editDescription.value.trim(), orderNo: editOrderNo.value }); ElMessage.success('编组信息已更新'); emit('changed') }
  catch (error: any) { ElMessage.error(error?.response?.data?.detail || error?.message || '更新编组失败') }
}
async function assignField() {
  if (!selectedField.value || !groupCode.value) return ElMessage.warning('请选择编组和字段')
  try { await adminApi.assignFieldGroup(groupCode.value, selectedField.value, fieldPath.value.trim()); ElMessage.success('字段已加入编组'); fieldPath.value = ''; emit('changed') }
  catch (error: any) { ElMessage.error(error?.response?.data?.detail || error?.message || '加入编组失败') }
}
async function assignChapter() {
  if (!chapterGroupCode.value || !selectedChapter.value) return ElMessage.warning('请选择编组和章节')
  try { await adminApi.assignGroupChapter(chapterGroupCode.value, selectedChapter.value); ElMessage.success('编组已加入章节'); emit('changed') }
  catch (error: any) { ElMessage.error(error?.response?.data?.detail || error?.message || '加入章节失败') }
}
</script>
<template>
  <el-button plain :icon="FolderAdd" @click="visible = true">管理编组</el-button>
  <el-dialog v-model="visible" title="编组管理" width="680px">
    <el-form label-position="top"><div class="group-form"><el-form-item label="编组编码"><el-input v-model="groupCode" placeholder="例如 samples" /></el-form-item><el-form-item label="编组名称"><el-input v-model="label" placeholder="例如 样品信息" /></el-form-item><el-form-item label="数据关系"><el-select v-model="cardinality"><el-option label="单值" value="ONE" /><el-option label="数组/多行" value="MANY" /></el-select></el-form-item></div><el-button type="primary" :loading="busy" @click="createGroup">新增编组</el-button><el-divider /><div class="group-form edit-form"><el-form-item label="编辑现有编组"><el-select v-model="editGroupCode" filterable @change="loadGroupForEdit"><el-option v-for="group in props.groups" :key="group.groupCode" :label="group.label" :value="group.groupCode" /></el-select></el-form-item><el-form-item label="名称"><el-input v-model="editLabel" /></el-form-item><el-form-item label="数据关系"><el-select v-model="editCardinality"><el-option label="单值" value="ONE" /><el-option label="数组/多行" value="MANY" /></el-select></el-form-item><el-form-item label="说明"><el-input v-model="editDescription" /></el-form-item><el-form-item label="排序"><el-input-number v-model="editOrderNo" :min="0" /></el-form-item></div><el-button type="primary" plain @click="saveGroup">保存编组信息</el-button><el-divider /><div class="group-form"><el-form-item label="目标编组"><el-select v-model="groupCode" filterable><el-option v-for="group in props.groups" :key="group.groupCode" :label="group.label" :value="group.groupCode" /></el-select></el-form-item><el-form-item label="未映射字段"><el-select v-model="selectedField" filterable clearable><el-option v-for="field in props.fields" :key="field.fieldCode" :label="`${field.label} · ${field.fieldCode}`" :value="field.fieldCode" /></el-select></el-form-item><el-form-item label="字段相对路径"><el-input v-model="fieldPath" placeholder="例如 sampleName" /></el-form-item></div><el-button @click="assignField">将字段加入编组</el-button><el-divider /><div class="group-form"><el-form-item label="选择编组"><el-select v-model="chapterGroupCode" filterable><el-option v-for="group in props.groups" :key="group.groupCode" :label="group.label" :value="group.groupCode" /></el-select></el-form-item><el-form-item label="选择章节"><el-select v-model="selectedChapter" filterable><el-option v-for="chapter in chapterOptions" :key="chapter.id" :label="`${'　'.repeat(chapter.depth * 2)}${chapter.code} · ${chapter.title}`" :value="chapter.id" /></el-select></el-form-item></div><el-button type="primary" plain @click="assignChapter">挂到章节</el-button></el-form>
  </el-dialog>
</template>
<style scoped>.group-form{display:grid;grid-template-columns:1fr 1fr 120px;gap:10px}.group-form .el-form-item{min-width:0}</style>
