<script setup lang="ts">
import type { ContentBlockKind, DesignerBlock, DesignerChapter } from '../admin-api'

defineProps<{ blockKindOptions: Array<{ value: ContentBlockKind; label: string }>; saving: boolean }>()
defineEmits<{ saveChapter: []; saveBlock: [] }>()
const chapterOpen = defineModel<boolean>('chapterOpen', { required: true })
const blockOpen = defineModel<boolean>('blockOpen', { required: true })
const chapter = defineModel<Partial<DesignerChapter>>('chapter', { required: true })
const block = defineModel<Partial<DesignerBlock> | undefined>('block', { required: true })
</script>

<template>
  <el-dialog v-model="chapterOpen" :title="chapter.id ? '编辑章节' : '新增章节'" width="520px">
    <el-form label-position="top">
      <div class="form-inline">
        <el-form-item label="章节编号"><el-input v-model="chapter.code" placeholder="例如 7.10" /></el-form-item>
        <el-form-item label="页码提示"><el-input-number v-model="chapter.pageHint" :min="1" /></el-form-item>
      </div>
      <el-form-item label="章节名称"><el-input v-model="chapter.title" /></el-form-item>
      <el-form-item label="排序号"><el-input-number v-model="chapter.orderNo" :min="0" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="chapterOpen = false">取消</el-button><el-button type="primary" @click="$emit('saveChapter')">保存章节</el-button></template>
  </el-dialog>

  <el-dialog v-model="blockOpen" :title="block?.id ? '编辑内容块' : '新增内容块'" width="680px">
    <el-form v-if="block" label-position="top">
      <div class="form-inline">
        <el-form-item label="内容块名称"><el-input v-model="block.title" placeholder="例如：对照品表格" /></el-form-item>
        <el-form-item label="内容块类型"><el-select v-model="block.kind"><el-option v-for="item in blockKindOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
      </div>
      <template v-if="['REPEATING_TABLE', 'MATRIX'].includes(block.kind || '')">
        <div class="form-inline">
          <el-form-item label="循环数据集合"><el-input v-model="block.sourcePath" placeholder="例如：$.referenceStandards[*]" /></el-form-item>
          <el-form-item label="Word 表格编号"><el-input v-model="block.tableNo" placeholder="例如：T5" /></el-form-item>
        </div>
        <div class="form-inline">
          <el-form-item label="Word 原型行位置"><el-input v-model="block.prototypeLocation" placeholder="例如：body.T5.dataRow" /></el-form-item>
          <el-form-item label="记录唯一键"><el-input v-model="block.repeatKey" placeholder="例如：recordId" /></el-form-item>
        </div>
        <div class="form-inline">
          <el-form-item label="去重字段"><el-input v-model="block.dedupKey" placeholder="例如：batchNo" /></el-form-item>
          <el-form-item label="排序规则"><el-input v-model="block.sortRule" placeholder="例如：name ASC, batchNo ASC" /></el-form-item>
        </div>
        <div class="form-inline">
          <el-form-item label="无数据时"><el-select v-model="block.emptyBehavior"><el-option label="保留一行并清空" value="KEEP" /><el-option label="隐藏数据行" value="HIDE" /></el-select></el-form-item>
          <el-form-item label="单元格合并"><el-select v-model="block.mergeRule"><el-option label="不自动合并" value="NONE" /><el-option label="相同值纵向合并" value="VERTICAL_BY_VALUE" /></el-select></el-form-item>
        </div>
      </template>
      <div class="form-inline">
        <el-form-item label="排序号"><el-input-number v-model="block.orderNo" :min="0" /></el-form-item>
        <el-form-item label="状态"><el-switch v-model="block.enabled" active-text="启用" /></el-form-item>
      </div>
    </el-form>
    <template #footer><el-button @click="blockOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="$emit('saveBlock')">保存内容块</el-button></template>
  </el-dialog>
</template>

<style scoped>
.form-inline { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
</style>
