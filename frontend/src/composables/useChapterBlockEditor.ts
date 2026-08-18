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
    blockDialog.value = true
  }

  async function saveBlock() {
    if (!blockDraft.value?.title?.trim()) return ElMessage.warning('内容块名称不能为空')
    const repeating = ['REPEATING_TABLE', 'MATRIX'].includes(blockDraft.value.kind || '')
    if (repeating && !blockDraft.value.sourcePath?.trim()) return ElMessage.warning('循环表格必须设置数据集合')
    options.saving.value = true
    try {
      const saved = blockDraft.value.id
        ? await adminApi.updateContentBlock(blockDraft.value.id, blockDraft.value)
        : await adminApi.createContentBlock(blockDraft.value)
      blockDialog.value = false
      await options.reload()
      const chapter = flatten(options.designer.value?.chapters || []).find((item) => item.id === saved.chapterId)
      const block = chapter?.blocks.find((item) => item.id === saved.id)
      if (chapter && block) options.selectBlock(chapter, block, false)
      ElMessage.success(blockDraft.value.id ? '内容块已保存' : '内容块已新增')
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
