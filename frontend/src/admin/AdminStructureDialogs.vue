<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
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
type MatrixRowFieldDraft = { row: number; field: string }
type MatrixFieldOption = { value: string; label: string }
const matrixDraft = reactive({
  enabled: false,
  minColumns: 5,
  widthMode: 'PROTOTYPE',
  rowFields: [] as MatrixRowFieldDraft[],
})
const groupMode = computed(() => block.value?.tableRule?.mode === 'ROW_REPEAT'
  || (block.value?.tableRule?.mode === 'TABLE_REPEAT' && block.value?.tableRule?.innerMode === 'ROW_REPEAT'))
const groupFields = computed(() => (block.value?.standardFields || [])
  .filter((item) => item.enabled !== false)
  .map((item) => ({ value: item.fieldPath || item.fieldCode, label: `${item.label} · ${item.fieldPath || item.fieldCode}` })))
function fieldKey(value: unknown): string {
  const text = String(value || '').trim()
  if (!text) return ''
  const normalized = text.replace(/^\$\.?/, '')
  const segments = normalized.split('.').filter(Boolean)
  const collectionIndex = segments.findIndex((segment) => /\[\*?\]$/.test(segment))
  const segment = collectionIndex >= 0
    ? segments[collectionIndex + 1] || segments[collectionIndex]
    : segments[segments.length - 1] || normalized
  return segment.replace(/\[\*?\]$/g, '')
}
function sourceFieldKey(sourcePath: unknown, fieldCode: unknown): string {
  const source = String(sourcePath || '').trim()
  const code = String(fieldCode || '').trim()
  const sourceKey = source ? fieldKey(source) : ''
  // 映射的 sourcePath 可能尚未从标准字段目录解析出来；带集合标记的字段编码仍是可用的记录字段路径。
  if (sourceKey && !/\[\*?\]/.test(source) && /\[\*?\]/.test(code)) return fieldKey(code)
  return sourceKey || fieldKey(fieldCode)
}
const matrixFieldOptions = computed<MatrixFieldOption[]>(() => {
  const options = new Map<string, MatrixFieldOption>()
  for (const item of block.value?.mappings || []) {
    const value = sourceFieldKey(item.sourcePath, item.fieldCode)
    if (value && !options.has(value)) options.set(value, { value, label: `${item.wordLabel || value} · ${value}` })
  }
  for (const item of block.value?.standardFields || []) {
    const value = fieldKey(item.legacyJsonPath || item.fieldPath || item.jsonKey || item.fieldCode)
    if (value && !options.has(value)) options.set(value, { value, label: `${item.label || value} · ${value}` })
  }
  for (const item of matrixDraft.rowFields) {
    if (item.field && !options.has(item.field)) options.set(item.field, { value: item.field, label: `未找到字段 · ${item.field}` })
  }
  return [...options.values()]
})
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
function matrixLayout() {
  try {
    const value = block.value?.tableRule?.matrixLayout
    const parsed = value ? JSON.parse(value) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}
function loadMatrix() {
  const layout = matrixLayout()
  const policy = layout.columnPolicy && typeof layout.columnPolicy === 'object' ? layout.columnPolicy : {}
  matrixDraft.enabled = policy.overflow === 'HORIZONTAL'
  matrixDraft.minColumns = Number(policy.minColumns || 5)
  matrixDraft.widthMode = String(policy.widthMode || 'PROTOTYPE')
  matrixDraft.rowFields = Array.isArray(layout.rowFields)
    ? layout.rowFields.map((entry: any) => ({ row: Number(entry?.row || 0), field: String(entry?.field || '') }))
    : []
}
function saveMatrix() {
  if (!block.value?.tableRule || block.value.tableRule.mode !== 'MATRIX') return
  const layout = matrixLayout()
  if (matrixDraft.enabled) {
    layout.rowFields = matrixDraft.rowFields.map((entry) => ({ row: Number(entry.row), field: entry.field }))
    layout.columnPolicy = {
      mode: 'DATA_LENGTH', overflow: 'HORIZONTAL',
      minColumns: Number(matrixDraft.minColumns || 1), widthMode: matrixDraft.widthMode,
    }
  } else {
    delete layout.columnPolicy
  }
  block.value.tableRule.matrixLayout = JSON.stringify(layout, null, 2)
}
function addMatrixRowField() {
  const row = Math.max(0, ...matrixDraft.rowFields.map((item) => Number(item.row) || 0)) + 1
  matrixDraft.rowFields.push({ row, field: '' })
}
function removeMatrixRowField(index: number) {
  matrixDraft.rowFields.splice(index, 1)
}
watch(groupMode, (active) => { if (active) loadGroup() }, { immediate: true })
watch(() => block.value?.standardGroupCode, () => { if (groupMode.value) loadGroup() })
watch(groupDraft, saveGroup, { deep: true })
watch(() => block.value?.tableRule?.mode, (mode) => { if (mode === 'MATRIX') loadMatrix() }, { immediate: true })
watch(matrixDraft, saveMatrix, { deep: true })
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
                <el-option label="结果矩阵：一条记录占一列（可向右扩展）" value="MATRIX" />
                <el-option label="按分组复制整表" value="TABLE_REPEAT" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item v-if="block.tableRule.mode !== 'MATRIX'" label="按行扩展时保留的汇总行">
            <el-select v-model="block.tableRule.preservedRowLabels" multiple filterable allow-create
              default-first-option placeholder="例如 RSD、结论、平均" />
            <small class="dialog-hint">仅用于按行向下扩展：首列以这些文字开头的行不会被删除，只清空未绑定的单元格。矩阵横向扩展无需配置，未列入“逐列数据行配置”的行默认保留。</small>
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
          <template v-if="block.tableRule.mode === 'MATRIX'">
            <div class="section-title">矩阵横向扩展（当前矩阵类型的可选布局）</div>
            <div class="form-inline">
              <el-form-item label="按数据条数向右扩展">
                <el-switch v-model="matrixDraft.enabled" active-text="启用" />
              </el-form-item>
              <el-form-item v-if="matrixDraft.enabled" label="最少数据列数">
                <el-input-number v-model="matrixDraft.minColumns" :min="1" :max="1000" />
              </el-form-item>
            </div>
            <div v-if="matrixDraft.enabled" class="form-inline">
              <el-form-item label="列宽策略">
                <el-select v-model="matrixDraft.widthMode">
                  <el-option label="沿用原型列宽，表格向右增长" value="PROTOTYPE" />
                  <el-option label="保持表格总宽度" value="PRESERVE_TOTAL" />
                </el-select>
              </el-form-item>
              <el-form-item label="逐列数据行配置" class="matrix-row-fields-item">
                <div class="matrix-row-fields">
                  <div v-for="(entry, index) in matrixDraft.rowFields" :key="index" class="matrix-row-field">
                    <el-input-number v-model="entry.row" :min="1" controls-position="right" aria-label="Word行号" />
                    <el-select v-model="entry.field" filterable placeholder="选择字段">
                      <el-option v-for="option in matrixFieldOptions" :key="option.value" :label="option.label" :value="option.value" />
                    </el-select>
                    <el-button link type="danger" :icon="Delete" aria-label="删除数据行配置" @click="removeMatrixRowField(index)" />
                  </div>
                  <el-button text type="primary" :icon="Plus" @click="addMatrixRowField">添加数据行</el-button>
                  <small v-if="!matrixDraft.rowFields.length" class="dialog-hint">请添加需要随数据记录向右扩展的 Word 行。</small>
                </div>
              </el-form-item>
            </div>
            <small v-if="matrixDraft.enabled" class="dialog-hint">只扩展配置为逐列数据的行；回归方程、相关系数、结论等固定行保持原布局。字段名必须来自报告数据记录。保存后该配置写入当前表格规则，不会新增独立业务类型。</small>
          </template>
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
.matrix-row-fields-item { grid-column: 1 / -1; min-width: 0; }
.matrix-row-fields { display: grid; gap: 8px; width: 100%; }
.matrix-row-field { display: grid; grid-template-columns: 110px minmax(0, 1fr) 32px; gap: 8px; align-items: center; }
.matrix-row-field :deep(.el-select) { width: 100%; }
</style>
