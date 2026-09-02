import type { Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminApi, type DesignerBlock, type DesignerChapter, type MappingRule,
  type TableRule, type TemplateDesigner,
} from '../admin-api'
import { adminErrorText } from '../admin/designer-formatters'

interface MappingEditorOptions {
  designer: Ref<TemplateDesigner | undefined>
  selectedChapter: Ref<DesignerChapter | undefined>
  selectedBlock: Ref<DesignerBlock | undefined>
  selectedMapping: Ref<MappingRule | undefined>
  expandedBlockId: Ref<number | undefined>
  draft: Ref<Partial<MappingRule> | undefined>
  saving: Ref<boolean>
  reload: () => Promise<void>
  identifiers: (mapping: Partial<MappingRule>) => {
    fieldCode: string; controlTag: string; locationId: string
  }
  displayName: (mapping: Partial<MappingRule>) => string
  selectMapping: (mapping?: MappingRule, locate?: boolean) => void
}

function flatten(chapters: DesignerChapter[]): DesignerChapter[] {
  return chapters.flatMap((chapter) => [chapter, ...flatten(chapter.children)])
}

export function useMappingEditor(options: MappingEditorOptions) {
  function addMapping(block = options.selectedBlock.value, standardField?: { fieldCode: string; label: string }) {
    const chapter = options.selectedChapter.value
    if (!chapter || !block) return ElMessage.warning('请先新增或选择一个内容块')
    options.selectedBlock.value = block
    options.expandedBlockId.value = block.id
    options.selectedMapping.value = undefined
    const repeating = ['REPEATING_TABLE', 'MATRIX', 'TABLE_REPEAT'].includes(block.kind)
    options.draft.value = {
      chapterId: chapter.id, ...(block.id > 0 ? { blockId: block.id } : {}),
      locationId: `draft.block${block.id}.${Date.now()}`,
      sectionCode: chapter.code, tableNo: block.tableNo || 'TEXT', wordLabel: standardField?.label || '新字段',
      fieldCode: '', standardFieldCode: standardField?.fieldCode || '', dataType: 'string', sourceType: 'SYSTEM', sourcePath: '',
      repeatType: repeating ? 'ROW' : 'NONE', repeatKey: block.repeatKey || '',
      mergeRule: 'PRESERVE', fillRule: 'TEXT', calculationRule: '',
      calculationExpression: '', calculationDependencies: [],
      calculationScope: repeating ? 'CURRENT_ROW' : 'REPORT',
      calculationPrecision: 2, calculationNullBehavior: 'ERROR', controlTag: '',
      required: false, sourcePending: true, enabled: true,
    }
  }

  function validateCalculation(mapping: Partial<MappingRule>) {
    if (mapping.sourceType !== 'CALCULATED') return true
    const expression = mapping.calculationExpression?.trim() || ''
    const dependencies = mapping.calculationDependencies || []
    if (!expression) { ElMessage.warning('请填写计算公式'); return false }
    if (!dependencies.length) { ElMessage.warning('请至少选择一个引用字段'); return false }
    const references = Array.from(expression.matchAll(/\{([^{}]+)\}/g), (match) => match[1].trim())
    const missing = references.filter((code) => !dependencies.includes(code))
    if (missing.length) { ElMessage.warning(`请先选择公式引用字段：${missing.join('、')}`); return false }
    return true
  }

  async function saveMapping() {
    const draft = options.draft.value
    if (!draft || !validateCalculation(draft)) return
    const editingId = draft.id
    if (!editingId && !draft.standardFieldCode) return ElMessage.warning('请先选择系统标准字段')
    draft.wordLabel = options.displayName(draft)
    Object.assign(draft, options.identifiers(draft))
    options.saving.value = true
    try {
      const saved = editingId ? await adminApi.updateMapping(editingId, draft) : await adminApi.createMapping(draft)
      await options.reload()
      const chapter = flatten(options.designer.value?.chapters || []).find((item) => item.id === saved.chapterId)
      const block = chapter?.blocks.find((item) => item.id === saved.blockId)
      const mapping = block?.mappings.find((item) => item.id === saved.id)
      if (chapter && block && mapping) {
        options.selectedChapter.value = chapter
        options.selectedBlock.value = block
        options.expandedBlockId.value = block.id
        options.selectMapping(mapping, false)
      }
      ElMessage.success(editingId ? '字段修改已保存' : '字段映射已新增')
    } catch (error) {
      ElMessage.error(adminErrorText(error))
    } finally {
      options.saving.value = false
    }
  }

  async function removeMapping(mapping: MappingRule) {
    try {
      await ElMessageBox.confirm(`删除字段“${mapping.wordLabel}”？不会删除 Word 中的文字。`, '删除字段映射', { type: 'warning' })
      await adminApi.deleteMapping(mapping.id)
      await options.reload()
      ElMessage.success('字段映射已删除')
    } catch (error) {
      if (error !== 'cancel' && error !== 'close') ElMessage.error(adminErrorText(error))
    }
  }

  async function saveTableRule(table: TableRule) {
    options.saving.value = true
    try {
      await adminApi.updateTable(table.tableNo, table)
      await options.reload()
      ElMessage.success('表格区域已保存')
    } catch (error) {
      ElMessage.error(adminErrorText(error))
    } finally {
      options.saving.value = false
    }
  }

  return { addMapping, saveMapping, removeMapping, saveTableRule }
}
