import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminApi, type DesignerBlock, type DesignerChapter, type TemplateDesigner,
} from '../admin-api'
import { adminErrorText } from '../admin/designer-formatters'

interface EditorOptions {
  designer: Ref<TemplateDesigner | undefined>
  selectedChapter: Ref<DesignerChapter | undefined>
  saving: Ref<boolean>
  reload: () => Promise<void>
  selectBlock: (chapter: DesignerChapter, block: DesignerBlock, locate?: boolean) => void
}

function flatten(chapters: DesignerChapter[]): DesignerChapter[] {
  return chapters.flatMap((chapter) => [chapter, ...flatten(chapter.children)])
}

export function useChapterBlockEditor(options: EditorOptions) {
  const chapterDraft = ref<Partial<DesignerChapter>>({})
  const chapterDialog = ref(false)
  const blockDialog = ref(false)
  const blockDraft = ref<Partial<DesignerBlock>>()

  function editChapter(chapter?: DesignerChapter, parent?: DesignerChapter) {
    chapterDraft.value = chapter ? JSON.parse(JSON.stringify(chapter)) : {
      parentId: parent?.id,
      code: '',
      title: '',
      pageHint: undefined,
      orderNo: (options.designer.value?.summary.chapters || 0) + 1,
      enabled: true,
    }
    chapterDialog.value = true
  }

  async function saveChapter() {
    if (!chapterDraft.value?.code || !chapterDraft.value.title) {
      return ElMessage.warning('章节编号和名称不能为空')
    }
    try {
      if (chapterDraft.value.id) await adminApi.updateChapter(chapterDraft.value.id, chapterDraft.value)
      else await adminApi.createChapter(chapterDraft.value)
      chapterDialog.value = false
      await options.reload()
      ElMessage.success('章节目录已保存')
    } catch (error) {
      ElMessage.error(adminErrorText(error))
    }
  }

  async function saveChapterFromInspector() {
    if (!options.selectedChapter.value) return
    options.saving.value = true
    try {
      await adminApi.updateChapter(options.selectedChapter.value.id, options.selectedChapter.value)
      await options.reload()
      ElMessage.success('章节属性已保存')
    } catch (error) {
      ElMessage.error(adminErrorText(error))
    } finally {
      options.saving.value = false
    }
  }

  async function removeChapter(chapter: DesignerChapter) {
    try {
      await ElMessageBox.confirm(`删除章节“${chapter.title}”？章节下内容块和字段规则会同时删除。`, '删除章节', { type: 'warning' })
      await adminApi.deleteChapter(chapter.id)
      await options.reload()
      ElMessage.success('章节已删除')
    } catch (error) {
      if (error !== 'cancel' && error !== 'close') ElMessage.error(adminErrorText(error))
    }
  }

  function editBlock(block?: DesignerBlock) {
    if (!options.selectedChapter.value) return ElMessage.warning('请先选择章节')
    blockDraft.value = block ? JSON.parse(JSON.stringify(block)) : {
      chapterId: options.selectedChapter.value.id,
      title: '新内容块',
      kind: 'MAPPED_FIELD',
      tableNo: '', sourcePath: '', repeatKey: '', prototypeLocation: '', dedupKey: '', sortRule: '',
      emptyBehavior: 'KEEP', mergeRule: 'NONE',
      orderNo: options.selectedChapter.value.blocks.length,
      enabled: true,
    }
    const draft = blockDraft.value
    if (block?.standardGroupCode && draft && !draft.tableRule) {
      draft.tableRule = {
        tableNo: '', sectionCode: options.selectedChapter.value.code, mode: 'STATIC',
        headerRows: 1, dataRowStart: 2, dataRowEnd: 2, footerRows: 0, recordKey: '', mergeFields: [],
        physicalTableIndex: 0, preservedRowLabels: [], clearEmbeddedObjects: false, matrixLayout: '',
        groupKey: block.standardGroupCode, innerMode: 'ROW_REPEAT', enabled: true, notes: '', updatedAt: '',
      }
    }
    blockDialog.value = true
  }

  // 横向分组要靠 Word 里那一格的合并跨度确定分组宽度，字段没绑就只能保留原样。
  function invalidMatrixLayout(draft: Partial<DesignerBlock>): string {
    const text = draft.tableRule?.matrixLayout?.trim()
    if (!text) return ''
    let layout: any
    try {
      layout = JSON.parse(text)
    } catch (error) {
      return `表格布局不是合法 JSON：${(error as Error).message}`
    }
    const policy = layout.columnPolicy
    if (policy !== undefined) {
      if (!policy || typeof policy !== 'object') return '矩阵横向扩展的 columnPolicy 必须是对象'
      if (String(policy.mode || 'DATA_LENGTH') !== 'DATA_LENGTH') return '矩阵横向扩展的 mode 只能是 DATA_LENGTH'
      if (policy.overflow !== 'HORIZONTAL') return '矩阵横向扩展的 overflow 只能是 HORIZONTAL'
      const minimum = Number(policy.minColumns)
      if (!Number.isInteger(minimum) || minimum < 1 || minimum > 1000) return '矩阵横向扩展的最少列数必须是 1 到 1000 的整数'
      if (!['PROTOTYPE', 'PRESERVE_TOTAL'].includes(String(policy.widthMode || 'PROTOTYPE'))) {
        return '矩阵横向扩展的列宽策略无效'
      }
      if (!Array.isArray(layout.rowFields) || !layout.rowFields.length) return '启用矩阵横向扩展时，逐列数据行配置不能为空'
      if (layout.rowFields.some((entry: any) => !entry || !Number.isInteger(Number(entry.row)) || Number(entry.row) < 1 || !String(entry.field || '').trim())) {
        return '逐列数据行配置必须包含正整数 row 和非空 field'
      }
    }
    if (!layout.groupField) return ''
    if (draft.tableRule?.mode !== 'ROW_REPEAT') return '横向分组字段只在“按行向下扩展”时生效'
    const bound = (draft.mappings || []).some(
      (item) => item.controlTag && String(item.sourcePath || '').endsWith(`.${layout.groupField}`),
    )
    if (!bound) return `横向分组字段 ${layout.groupField} 还没有绑定 Word 内容控件，请先把它绑到分组表头格`
    return ''
  }

  async function saveBlock() {
    if (!blockDraft.value?.standardGroupCode && !blockDraft.value?.title?.trim()) return ElMessage.warning('内容块名称不能为空')
    const layout = blockDraft.value.tableRule
    if (blockDraft.value.standardGroupCode && layout) {
      const mappedTable = (blockDraft.value.mappings || []).find((item) => /^T\d+$/.test(String(item.tableNo || "")))?.tableNo
      layout.tableNo = layout.tableNo || mappedTable || `GROUP:${blockDraft.value.standardGroupCode}`
      if (layout.mode !== 'STATIC') blockDraft.value.kind = layout.mode === 'MATRIX' ? 'MATRIX' : 'REPEATING_TABLE'
    }
    if (blockDraft.value.standardGroupCode && layout?.mode !== 'STATIC' && !layout?.physicalTableIndex) {
      const hasAnchor = (blockDraft.value.mappings || []).some((item) => item.controlTag)
      if (!hasAnchor) return ElMessage.warning('请先绑定该编组的字段，系统才能自动定位目标表格')
    }
    if (blockDraft.value.standardGroupCode && layout?.mode === 'ROW_REPEAT' && !layout.dataRowStart) {
      return ElMessage.warning('按行向下扩展必须设置原型数据行')
    }
    const repeating = !blockDraft.value.standardGroupCode && ['REPEATING_TABLE', 'MATRIX', 'TABLE_REPEAT'].includes(blockDraft.value.kind || '')
    if (repeating && !blockDraft.value.sourcePath?.trim()) return ElMessage.warning('循环表格必须设置数据集合')
    if (blockDraft.value.standardGroupCode && blockDraft.value.tableRule?.mode === 'TABLE_REPEAT' && !blockDraft.value.tableRule?.groupKey?.trim()) {
      return ElMessage.warning('按分组复制整表必须设置分组字段')
    }
    const layoutError = invalidMatrixLayout(blockDraft.value)
    if (layoutError) return ElMessage.warning(layoutError)
    options.saving.value = true
    try {
      // Word 表格布局与内容块一起保存，避免设计器里改了布局却没落库
      if (blockDraft.value.tableRule?.tableNo && !blockDraft.value.standardGroupCode) {
        await adminApi.updateTable(blockDraft.value.tableRule.tableNo, blockDraft.value.tableRule)
      }
      const saved = blockDraft.value.standardGroupCode
        ? await adminApi.saveTemplateBlock(blockDraft.value.standardGroupCode, blockDraft.value)
        : blockDraft.value.id
        ? await adminApi.updateContentBlock(blockDraft.value.id, blockDraft.value)
        : await adminApi.createContentBlock(blockDraft.value)
      blockDialog.value = false
      await options.reload()
      const chapter = flatten(options.designer.value?.chapters || []).find((item) => item.id === saved.chapterId)
      const block = chapter?.blocks.find((item) => item.id === saved.id || item.standardGroupCode === blockDraft.value?.standardGroupCode)
      if (chapter && block) options.selectBlock(chapter, block, false)
      ElMessage.success('模板布局已保存')
    } catch (error) {
      ElMessage.error(adminErrorText(error))
    } finally {
      options.saving.value = false
    }
  }

  async function removeBlock(block: DesignerBlock) {
    try {
      await ElMessageBox.confirm(
        `删除内容块“${block.title}”？块内 ${block.mappings.length} 个字段也会一并删除，但不会删除 Word 中的文字。`,
        '删除内容块', { type: 'warning' },
      )
      await adminApi.deleteContentBlock(block.id, true)
      await options.reload()
      ElMessage.success('内容块及其字段已删除')
    } catch (error) {
      if (error !== 'cancel' && error !== 'close') ElMessage.error(adminErrorText(error))
    }
  }

  return {
    chapterDraft, chapterDialog, blockDialog, blockDraft,
    editChapter, saveChapter, saveChapterFromInspector, removeChapter,
    editBlock, saveBlock, removeBlock,
  }
}
