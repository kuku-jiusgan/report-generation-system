<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { ContentBlockKind, DesignerBlock, DesignerChapter } from '../admin-api'

defineProps<{ blockKindOptions: Array<{ value: ContentBlockKind; label: string }>; saving: boolean }>()
defineEmits<{ saveChapter: []; saveBlock: []; detectTable: [] }>()
const chapterOpen = defineModel<boolean>('chapterOpen', { required: true })
const blockOpen = defineModel<boolean>('blockOpen', { required: true })
const chapter = defineModel<Partial<DesignerChapter>>('chapter', { required: true })
const block = defineModel<Partial<DesignerBlock> | undefined>('block', { required: true })

// 表格统一按"向下填充"处理：哪一列填哪个字段由 Word 里的控件绑定决定，不在这里重复声明。
// 设了横向分组字段就额外向右扩列——一个分组占哪几列，取绑了该字段那一格的合并跨度。
const groupDraft = reactive({ groupField: '', groupColumnWidth: 'EQUAL' })
const groupMode = computed(() => block.value?.tableRule?.mode === 'ROW_REPEAT'
  || (block.value?.tableRule?.mode === 'TABLE_REPEAT' && block.value?.tableRule?.innerMode === 'ROW_REPEAT'))
const groupFields = computed(() => (block.value?.standardFields || [])
  .filter((item) => item.enabled !== false)
  .map((item) => ({ value: item.fieldPath || item.fieldCode, label: `${item.label} · ${item.fieldPath || item.fieldCode}` })))
function loadGroup() {
  let layout: any = {}
  try { layout = block.value?.tableRule?.matrixLayout ? JSON.parse(block.value.tableRule.matrixLayout) : {} } catch { layout = {} }
  groupDraft.groupField = String(layout.groupField || '')
  groupDraft.groupColumnWidth = String(layout.groupColumnWidth || 'EQUAL')
}
function saveGroup() {
  if (!block.value?.tableRule) return
  block.value.tableRule.matrixLayout = groupDraft.groupField
    ? JSON.stringify({ groupField: groupDraft.groupField, groupColumnWidth: groupDraft.groupColumnWidth }, null, 2)
    : ''
}
watch(groupMode, (active) => { if (active) loadGroup() }, { immediate: true })
watch(() => block.value?.standardGroupCode, () => { if (groupMode.value) loadGroup() })
watch(groupDraft, saveGroup, { deep: true })
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
              <small class="dialog-hint">已绑定字段时自动按字段所在表格定位；填写序号仅用于未绑定字段的旧模板。</small>
            </el-form-item>
            <el-form-item label="填充方式">
              <el-select v-model="block.tableRule.mode">
                <el-option label="不自动填充" value="STATIC" />
                <el-option label="按行向下扩展" value="ROW_REPEAT" />
                <el-option label="转置矩阵：一条记录占一列" value="MATRIX" />
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
                <el-option label="转置矩阵：一条记录占一列" value="MATRIX" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="清除表内图片">
            <el-switch v-model="block.tableRule.clearEmbeddedObjects" active-text="生成时清除该表中的图片与嵌入对象" />
          </el-form-item>
          <el-form-item v-if="block.tableRule.mode === 'ROW_REPEAT'" label="横向分组字段（可留空）">
            <el-select v-model="groupDraft.groupField" filterable clearable placeholder="留空表示只向下填充">
              <el-option v-for="item in groupFields" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <small class="dialog-hint">
              留空就是普通的向下填充：一条记录一行，哪一列填哪个字段由 Word 里的控件绑定决定。
              选了字段则在此基础上再向右扩：该字段在数据里有几个不同取值就扩几组，
              一个分组占哪几列取自 Word 里绑定该字段那一格的合并跨度，子列标题和控件整块复制，不用另外声明。
              非原型行里属于本编组的控件（例如 RSD 行）按分组各填一个值，组内取值必须唯一。
            </small>
          </el-form-item>
          <el-form-item v-if="block.tableRule.mode === 'ROW_REPEAT' && groupDraft.groupField" label="多个分组时的子列宽度">
            <el-select v-model="groupDraft.groupColumnWidth" style="width: 260px">
              <el-option label="各子列等宽" value="EQUAL" />
              <el-option label="按 Word 原型的列宽比例" value="PROTOTYPE" />
            </el-select>
            <small class="dialog-hint">扩列后保持表格总宽度不变。标题长的窄列在多分组时容易被挤成三行，选等宽即可。</small>
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
.matrix-structure-hint { margin-bottom: 8px; color: var(--el-text-color-secondary); line-height: 1.5; font-size: 12px; }
.readonly-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:14px 0; }
.readonly-grid div { background:var(--el-fill-color-light); padding:8px 10px; border-radius:4px; }
.readonly-grid span, .field-list > span { display:block; color:var(--el-text-color-secondary); font-size:12px; margin-bottom:4px; }
.field-list { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px; }
</style>
