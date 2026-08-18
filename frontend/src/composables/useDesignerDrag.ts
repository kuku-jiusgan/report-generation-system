import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type DesignerBlock, type DesignerChapter, type MappingRule } from '../admin-api'
import { adminErrorText } from '../admin/designer-formatters'

export function useDesignerDrag(
  selectedChapter: Ref<DesignerChapter | undefined>,
  reload: () => Promise<void>,
) {
  const draggingBlockId = ref<number>()
  const dragOverBlockId = ref<number>()
  const draggingMappingId = ref<number>()
  const dragOverMappingId = ref<number>()
  const reordering = ref(false)

  function moveByDrop<T extends { id: number }>(
    items: T[], sourceId: number, targetId: number, after: boolean,
  ) {
    const source = items.find((item) => item.id === sourceId)
    if (!source || sourceId === targetId) return items
    const result = items.filter((item) => item.id !== sourceId)
    const targetIndex = result.findIndex((item) => item.id === targetId)
    result.splice(targetIndex + (after ? 1 : 0), 0, source)
    return result
  }

  function dropAfter(event: DragEvent) {
    const target = event.currentTarget as HTMLElement | null
    if (!target) return false
    const bounds = target.getBoundingClientRect()
    return event.clientY > bounds.top + bounds.height / 2
  }

  function startBlockDrag(event: DragEvent, block: DesignerBlock) {
    draggingBlockId.value = block.id
    event.dataTransfer?.setData('text/plain', `block:${block.id}`)
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
  }

  async function dropBlock(event: DragEvent, target: DesignerBlock) {
    event.preventDefault()
    const chapter = selectedChapter.value
    const sourceId = draggingBlockId.value
    if (!chapter || !sourceId || reordering.value) return
    const ordered = moveByDrop(chapter.blocks, sourceId, target.id, dropAfter(event))
    if (ordered === chapter.blocks) return
    ordered.forEach((item, orderNo) => { item.orderNo = orderNo })
    chapter.blocks = ordered
    reordering.value = true
    try {
      await adminApi.reorderContentBlocks(chapter.id, ordered.map((item) => item.id))
      ElMessage.success('内容块顺序已保存')
    } catch (error) {
      await reload()
      ElMessage.error(adminErrorText(error))
    } finally {
      draggingBlockId.value = undefined
      dragOverBlockId.value = undefined
      reordering.value = false
    }
  }

  function startMappingDrag(event: DragEvent, mapping: MappingRule) {
    draggingMappingId.value = mapping.id
    event.dataTransfer?.setData('text/plain', `mapping:${mapping.id}`)
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
  }

  async function dropMapping(event: DragEvent, block: DesignerBlock, target: MappingRule) {
    event.preventDefault()
    event.stopPropagation()
    const sourceId = draggingMappingId.value
    if (!sourceId || reordering.value) return
    const ordered = moveByDrop(block.mappings, sourceId, target.id, dropAfter(event))
    if (ordered === block.mappings) return
    block.mappings = ordered
    block.mappingIds = ordered.map((item) => item.id)
    reordering.value = true
    try {
      await adminApi.reorderBlockMappings(block.id, block.mappingIds)
      ElMessage.success('字段顺序已保存')
    } catch (error) {
      await reload()
      ElMessage.error(adminErrorText(error))
    } finally {
      draggingMappingId.value = undefined
      dragOverMappingId.value = undefined
      reordering.value = false
    }
  }

  function finishDrag() {
    draggingBlockId.value = undefined
    dragOverBlockId.value = undefined
    draggingMappingId.value = undefined
    dragOverMappingId.value = undefined
  }

  return {
    draggingBlockId, dragOverBlockId, draggingMappingId, dragOverMappingId, reordering,
    startBlockDrag, dropBlock, startMappingDrag, dropMapping, finishDrag,
  }
}
