import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type MappingRule, type TemplateDesigner } from '../admin-api'
import { adminErrorText as errorText } from '../admin/designer-formatters'
import { controlId, controlTag, type WordControl as Control } from './useAdminWordEditor'

type BindingOptions = {
  controls: Ref<Control[]>
  mappingDraft: Ref<Partial<MappingRule>>
  selectedMapping: Ref<MappingRule | undefined>
  designer: Ref<TemplateDesigner | undefined>
  pluginReady: Ref<boolean>
  hasConnector: () => boolean
  execWord: (name: string, args?: unknown[]) => Promise<unknown>
  refreshWordControls: () => Promise<void>
  requestWordBind: (alias: string, tag: string, oldInternalId: string) => Promise<{
    control: Control; selectedText: string; existing: boolean; objectType?: 'text' | 'image'
  }>
  requestPluginUnbind: (id?: string) => Promise<void>
  generateMappingIdentifiers: (mapping: Partial<MappingRule>) => {
    fieldCode: string; controlTag: string; locationId: string
  }
  reloadDesigner: () => Promise<void>
  locateInWord: (tag?: string) => Promise<void>
}

export function useAdminWordBinding(options: BindingOptions) {
  const bindingMappingId = ref<number>()
  const unbindingWord = ref(false)

  async function bindCurrentWordPosition(mapping: MappingRule) {
    if (!options.hasConnector() && !options.pluginReady.value)
      return ElMessage.warning('Word 编辑器尚未连接完成')
    if (bindingMappingId.value) return
    bindingMappingId.value = mapping.id
    let created: Control | undefined
    let createdNew = false
    try {
      const identifiers = options.generateMappingIdentifiers(mapping)
      const tag = identifiers.controlTag
      const oldControl = options.controls.value.find(
        (item) => controlTag(item) === mapping.controlTag,
      )
      let selectedText = ''
      let objectType: 'text' | 'image' = 'text'
      let existing = false
      if (options.hasConnector()) {
        const rawSelectionType = await options.execWord('GetSelectionType')
        const selectionType = normalizeSelectionType(rawSelectionType)
        console.info('[WordBinding]', { stage: 'selection-type', rawSelectionType, selectionType })
        if (!selectionType)
          throw new Error('Word 未返回可绑定的文字或图片选区，请重新选择后再试')
        objectType = selectionType === 'image' ? 'image' : 'text'
        if (objectType === 'text') {
          selectedText = String(
            (await options.execWord('GetSelectedText', [
              { Numbering: false, Math: true, ParaSeparator: '\n' },
            ])) || '',
          ).trim()
          if (!selectedText) {
            console.info('[WordBinding]', { stage: 'empty-text-selection', action: 'try-picture-control' })
            objectType = 'image'
          }
        }
        const current = (await options.execWord('GetCurrentContentControlPr')) as Control | null
        if (current && controlTag(current) === mapping.controlTag) existing = true
        else if (current && controlId(current))
          throw new Error('当前对象已属于其他内容控件，请改选未绑定的文字或图片')
        if (existing) created = current || undefined
        else {
          const properties = { Tag: tag, Alias: mapping.wordLabel, Lock: 3, Appearance: 1,
            Color: { R: 33, G: 122, B: 103 } }
          created = (await options.execWord(
            objectType === 'image' ? 'AddContentControlPicture' : 'AddContentControl',
            objectType === 'image' ? [properties] : [1, properties],
          )) as Control | undefined
          createdNew = true
        }
      } else {
        const result = await options.requestWordBind(mapping.wordLabel, tag, controlId(oldControl))
        created = result.control
        selectedText = result.selectedText
        existing = result.existing
        if (result.objectType && result.objectType !== 'text' && result.objectType !== 'image')
          throw new Error('Word 返回了无法识别的绑定对象类型，请重新选择后再试')
        objectType = result.objectType || 'text'
        createdNew = !existing
      }
      if (!created || controlTag(created) !== tag)
        throw new Error('Word 未能为当前选区创建内容控件，请重新选择文字或图片后再试')

      const updated = await adminApi.updateMapping(mapping.id, {
        fieldCode: identifiers.fieldCode,
        controlTag: tag,
        locationId: identifiers.locationId,
      })
      if (options.mappingDraft.value?.id === mapping.id) {
        options.mappingDraft.value.controlTag = updated.controlTag
        options.mappingDraft.value.locationId = updated.locationId
        options.mappingDraft.value.fieldCode = updated.fieldCode
      }
      if (oldControl && controlId(oldControl) !== controlId(created)) {
        if (options.hasConnector()) await options.execWord('RemoveContentControl', [controlId(oldControl)])
        else await options.requestPluginUnbind(controlId(oldControl))
      }
      if (options.hasConnector()) await options.refreshWordControls()
      await adminApi.forceSaveOnlyOffice()
      await options.reloadDesigner()
      const refreshed = flatten(options.designer.value?.chapters || [])
        .flatMap((chapter) => chapter.blocks)
        .flatMap((block) => block.mappings)
        .find((item) => item.id === updated.id)
      if (refreshed) {
        options.selectedMapping.value = refreshed
        options.mappingDraft.value = JSON.parse(JSON.stringify(refreshed)) as Partial<MappingRule>
      }
      await options.locateInWord(tag)
      ElMessage.success(
        existing ? `该${objectType === 'image' ? '图片' : '文字'}已经绑定到当前字段` :
          objectType === 'image' ? '已绑定图片并保存' : `已绑定“${selectedText.slice(0, 30)}”并保存`,
      )
    } catch (error) {
      if (createdNew && created && controlId(created)) {
        try {
          if (options.hasConnector()) await options.execWord('RemoveContentControl', [controlId(created)])
          else await options.requestPluginUnbind(controlId(created))
        } catch { /* Preserve the original failure; the new control can be removed manually. */ }
      }
      ElMessage.error(errorText(error))
    } finally {
      bindingMappingId.value = undefined
    }
  }

  async function unbindCurrentWordPosition() {
    if (!options.hasConnector() && !options.pluginReady.value)
      return ElMessage.warning('Word 编辑器尚未连接完成')
    if (unbindingWord.value) return
    try {
      await ElMessageBox.confirm(
        '解除当前文字或图片的 Word 绑定？原内容和样式会保留，之后可以重新绑定。',
        '解除 Word 绑定',
        { type: 'warning', confirmButtonText: '解除绑定', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    unbindingWord.value = true
    try {
      if (options.hasConnector()) {
        const current = (await options.execWord('GetCurrentContentControlPr')) as Control | null
        const id = controlId(current)
        if (!id) throw new Error('请先在 Word 中点击要解除绑定的文字或图片')
        await options.execWord('RemoveContentControl', [id])
        await options.refreshWordControls()
      } else await options.requestPluginUnbind()
      if (options.selectedMapping.value) {
        await adminApi.updateMapping(options.selectedMapping.value.id, { controlTag: '', locationId: '' })
        await options.reloadDesigner()
      }
      ElMessage.success('已解除 Word 绑定，原内容和样式已保留')
    } catch (error) {
      ElMessage.error(errorText(error))
    } finally {
      unbindingWord.value = false
    }
  }

  return { bindingMappingId, unbindingWord, bindCurrentWordPosition, unbindCurrentWordPosition }
}

function flatten(items: TemplateDesigner['chapters']): TemplateDesigner['chapters'] {
  return items.flatMap((item) => [item, ...flatten(item.children)])
}

function normalizeSelectionType(value: unknown): 'text' | 'image' | '' {
  const raw = typeof value === 'object' && value !== null
    ? (value as { type?: unknown; Type?: unknown; value?: unknown }).type ??
      (value as { Type?: unknown }).Type ?? (value as { value?: unknown }).value
    : value
  const normalized = String(raw || '').trim().toLowerCase()
  if (normalized === 'text') return 'text'
  if (['drawing', 'image', 'picture'].includes(normalized)) return 'image'
  return ''
}
