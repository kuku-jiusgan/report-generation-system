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

  <el-dialog v-model="blockOpen" :title="block?.standardGroupCode ? '配置模板布局' : (block?.id ? '编辑内容块' : '新增内容块')" width="760px">
    <el-form v-if="block" label-position="top">
      <div v-if="!block.standardGroupCode" class="form-inline">
        <el-form-item label="内容块名称"><el-input v-model="block.title" placeholder="例如：对照品表格" /></el-form-item>
        <el-form-item label="内容块类型"><el-select v-model="block.kind"><el-option v-for="item in blockKindOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
      </div>
      <template v-if="block.standardGroupCode || ['REPEATING_TABLE', 'MATRIX', 'TABLE_REPEAT'].includes(block.kind || '')">
        <div v-if="!block.standardGroupCode" class="form-inline">
          <el-form-item label="循环数据集合"><el-input v-model="block.sourcePath" placeholder="例如：$.referenceStandards[*]" /></el-form-item>
          <el-form-item label="Word 表格编号"><el-input v-model="block.tableNo" placeholder="例如：T5" /></el-form-item>
        </div>
        <div v-if="!block.standardGroupCode" class="form-inline">
          <el-form-item label="Word 原型行位置"><el-input v-model="block.prototypeLocation" placeholder="例如：body.T5.dataRow" /></el-form-item>
          <el-form-item label="记录唯一键"><el-input v-model="block.repeatKey" placeholder="例如：recordId" /></el-form-item>
        </div>
        <div v-if="!block.standardGroupCode" class="form-inline">
          <el-form-item label="去重字段"><el-input v-model="block.dedupKey" placeholder="例如：batchNo" /></el-form-item>
          <el-form-item label="排序规则"><el-input v-model="block.sortRule" placeholder="例如：name ASC, batchNo ASC" /></el-form-item>
        </div>
        <div v-if="!block.standardGroupCode" class="form-inline">
          <el-form-item label="无数据时"><el-select v-model="block.emptyBehavior"><el-option label="保留一行并清空" value="KEEP" /><el-option label="隐藏数据行" value="HIDE" /></el-select></el-form-item>
          <el-form-item label="单元格合并"><el-select v-model="block.mergeRule"><el-option label="不自动合并" value="NONE" /><el-option label="相同值纵向合并" value="VERTICAL_BY_VALUE" /></el-select></el-form-item>
        </div>
        <template v-if="block.tableRule">
          <div class="section-title">Word 表格布局</div>
          <div class="form-inline">
            <el-form-item label="Word 正文第几张表格">
              <el-input-number v-model="block.tableRule.physicalTableIndex" :min="0" />
              <small class="dialog-hint">0 表示未配置：编译时会跳过这张表并给出警告。</small>
            </el-form-item>
            <el-form-item label="填充方式">
              <el-select v-model="block.tableRule.mode">
                <el-option label="不自动填充" value="STATIC" />
                <el-option label="按行向下扩展" value="ROW_REPEAT" />
                <el-option label="矩阵填充" value="MATRIX" />
                <el-option label="按分组复制整表" value="TABLE_REPEAT" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="重建数据行时保留的汇总行">
            <el-select v-model="block.tableRule.preservedRowLabels" multiple filterable allow-create
              default-first-option placeholder="例如 RSD、结论、平均" />
            <small class="dialog-hint">首列以这些文字开头的行不会被删除，只清空未绑定的单元格。</small>
          </el-form-item>
          <div v-if="block.tableRule.mode === 'ROW_REPEAT'" class="form-inline">
            <el-form-item label="原型数据行位置"><el-input-number v-model="block.tableRule.dataRowStart" :min="1" /></el-form-item>
            <el-form-item label="数据行结束位置"><el-input-number v-model="block.tableRule.dataRowEnd" :min="1" /></el-form-item>
          </div>
          <div v-if="block.tableRule.mode === 'TABLE_REPEAT'" class="form-inline">
            <el-form-item label="整表分组字段">
              <el-input v-model="block.tableRule.groupKey" placeholder="例如 impurityId 或 impurityName" />
            </el-form-item>
            <el-form-item label="表内填充方式">
              <el-select v-model="block.tableRule.innerMode">
                <el-option label="按行重复" value="ROW_REPEAT" />
                <el-option label="矩阵填充" value="MATRIX" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="清除表内图片">
            <el-switch v-model="block.tableRule.clearEmbeddedObjects" active-text="生成时清除该表中的图片与嵌入对象" />
          </el-form-item>
          <el-form-item v-if="block.tableRule.mode === 'MATRIX' || (block.tableRule.mode === 'TABLE_REPEAT' && block.tableRule.innerMode === 'MATRIX')" label="矩阵布局配置（JSON）">
            <el-input v-model="block.tableRule.matrixLayout" type="textarea" :rows="6"
              placeholder='{"rowFields":[{"row":1,"field":"solutionName"}],"rowLabels":[],"scalarCells":[]}' />
            <small class="dialog-hint">行号与列号从 1 起算。留空时该表不会被填充，生成的报告里会保留 Word 原有内容并给出警告。</small>
          </el-form-item>
        </template>
      </template>
      <div v-if="!block.standardGroupCode" class="form-inline">
        <el-form-item label="排序号"><el-input-number v-model="block.orderNo" :min="0" /></el-form-item>
        <el-form-item label="状态"><el-switch v-model="block.enabled" active-text="启用" /></el-form-item>
      </div>
    </el-form>
    <template #footer><el-button @click="blockOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="$emit('saveBlock')">保存布局</el-button></template>
  </el-dialog>
</template>

<style scoped>
.form-inline { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.section-title { margin: 6px 0 10px; font-weight: 600; color: var(--el-text-color-primary); }
.dialog-hint { display: block; line-height: 1.5; color: var(--el-text-color-secondary); }
.readonly-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:14px 0; }
.readonly-grid div { background:var(--el-fill-color-light); padding:8px 10px; border-radius:4px; }
.readonly-grid span, .field-list > span { display:block; color:var(--el-text-color-secondary); font-size:12px; margin-bottom:4px; }
.field-list { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px; }
</style>
