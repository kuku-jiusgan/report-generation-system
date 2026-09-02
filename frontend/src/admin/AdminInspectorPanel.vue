<script setup lang="ts">
import { computed } from 'vue'
import { Delete, EditPen, Files, Link, Rank, Unlock } from '@element-plus/icons-vue'
import type { DesignerBlock, DesignerChapter, MappingRule, StandardField } from '../admin-api'
import StandardFieldPicker from '../StandardFieldPicker.vue'
import { blockTone, sourceTagType } from './designer-formatters'

const emit = defineEmits<{
  editBlock: [block?: DesignerBlock]
  startBlockDrag: [event: DragEvent, block: DesignerBlock]
  finishDrag: []
  toggleBlock: [chapter: DesignerChapter, block: DesignerBlock]
  addMapping: [block: DesignerBlock, field?: { fieldCode: string; label: string }]
  removeBlock: [block: DesignerBlock]
  dropBlock: [event: DragEvent, block: DesignerBlock]
  selectBlock: [chapter: DesignerChapter, block: DesignerBlock, locate?: boolean]
  selectMapping: [mapping: MappingRule, locate?: boolean]
  startMappingDrag: [event: DragEvent, mapping: MappingRule]
  dropMapping: [event: DragEvent, block: DesignerBlock, mapping: MappingRule]
  bindMapping: [mapping: MappingRule]
  removeMapping: [mapping: MappingRule]
  unbind: []
  sourceTypeChange: [sourceType: string]
  selectStandardField: [field: StandardField]
  refreshStandardFields: []
  calculationFunction: [name: string]
  calculationReference: [code: string]
  saveMapping: []
}>()
const selectedChapter = defineModel<DesignerChapter | undefined>('selectedChapter', { required: true })
const mappingDraft = defineModel<Partial<MappingRule>>('mappingDraft', { required: true })
const advancedOpen = defineModel<boolean>('advancedOpen', { required: true })
const dragOverBlockId = defineModel<number | undefined>('dragOverBlockId', { required: true })
const dragOverMappingId = defineModel<number | undefined>('dragOverMappingId', { required: true })
const props = defineProps<{
  selectedBlock?: DesignerBlock
  selectedMapping?: MappingRule
  expandedContentBlockId?: number
  draggingBlockId?: number
  draggingMappingId?: number
  bindingMappingId?: number
  unbindingWord: boolean
  saving: boolean
  standardFields: StandardField[]
  calculationFieldOptions: Array<{ code: string; label: string }>
}>()
const selectedStandardField = computed(() => props.standardFields.find(
  (field) => field.fieldCode === props.selectedMapping?.standardFieldCode,
))
const displayBlocks = computed<DesignerBlock[]>(() => {
  if (selectedChapter.value?.blocks?.length) return selectedChapter.value.blocks
  return (selectedChapter.value?.standardGroups || []).map((group, index) => ({
    id: -(selectedChapter.value!.id * 1000 + index + 1), chapterId: selectedChapter.value!.id,
    title: group.label, kind: 'MAPPED_FIELD', tableNo: '', sourcePath: '', repeatKey: '',
    prototypeLocation: '', dedupKey: '', sortRule: '', emptyBehavior: 'KEEP', mergeRule: 'NONE',
    orderNo: index, enabled: true, mappingIds: [], controlTags: [], sources: [], status: 'READY', mappings: [],
    standardFields: group.fields, standardGroupCode: group.groupCode,
  }))
})
const standardFieldFor = (mapping: MappingRule) => props.standardFields.find(
  (field) => field.fieldCode === mapping.standardFieldCode,
)

const sourceLabels: Record<string, string> = {
  SYSTEM: '系统标准字段',
  FIXED: '模板固定内容', LIMS: 'LIMS 数据', PDF: 'PDF 文档', AI: '大模型生成',
  CALCULATED: '系统计算', MANUAL: '人工录入',
}
const fillRuleOptions = [
  { value: 'TEXT', label: '按普通文本填充' },
  { value: 'PRESERVE_STYLE;EMPTY_AS_DASH', label: '保留样式，空值填短横线' },
  { value: 'VERSION_2_DIGITS', label: '格式化为两位版本号' },
  { value: 'WORD_FIELD', label: '保留为文档域' },
]
const mergeRuleOptions = [
  { value: 'PRESERVE', label: '保留模板原有结构' },
  { value: 'VERTICAL_BY_VALUE', label: '相同值纵向合并' },
]

const editBlock = (block?: DesignerBlock) => emit('editBlock', block)
const startBlockDrag = (event: DragEvent, block: DesignerBlock) => emit('startBlockDrag', event, block)
const finishDrag = () => emit('finishDrag')
const toggleContentBlock = (chapter: DesignerChapter, block: DesignerBlock) => emit('toggleBlock', chapter, block)
const addMapping = (block: DesignerBlock, field?: { fieldCode: string; label: string }) => emit('addMapping', block, field)
const removeBlock = (block: DesignerBlock) => emit('removeBlock', block)
const dropBlock = (event: DragEvent, block: DesignerBlock) => emit('dropBlock', event, block)
const selectBlock = (chapter: DesignerChapter, block: DesignerBlock, locate = true) => emit('selectBlock', chapter, block, locate)
const selectMapping = (mapping: MappingRule, locate = true) => emit('selectMapping', mapping, locate)
const startMappingDrag = (event: DragEvent, mapping: MappingRule) => emit('startMappingDrag', event, mapping)
const dropMapping = (event: DragEvent, block: DesignerBlock, mapping: MappingRule) => emit('dropMapping', event, block, mapping)
const bindCurrentWordPosition = (mapping: MappingRule) => emit('bindMapping', mapping)
const removeMapping = (mapping: MappingRule) => emit('removeMapping', mapping)
const unbindCurrentWordPosition = () => emit('unbind')
const selectStandardField = (field: StandardField) => emit('selectStandardField', field)
const saveMapping = () => emit('saveMapping')
</script>

<template>
      <aside class="inspector-panel">
        <div v-if="selectedChapter" class="inspector-head">
          <div class="inspector-path">
            模板目录 / {{ selectedChapter.code }}
          </div>
          <div class="inspector-title">
            <span class="kind-mark"><Files /></span>
            <div>
              <strong>{{ selectedChapter.title }}</strong>
            </div>
            <el-tag type="info" effect="plain">章节</el-tag>
          </div>
        </div>
        <div class="inspector-scroll">
          <div v-if="selectedChapter" class="inspector-subhead fields-head">
            <div>
              <strong>本章节内容块与字段配置</strong>
            </div>
          </div>
          <template v-for="block in displayBlocks" :key="block.id">
          <div
            class="field-block"
            :class="{
              expanded: expandedContentBlockId === block.id,
              selected: selectedBlock?.id === block.id,
              'drag-over': dragOverBlockId === block.id,
            }"
            @dragover="
              draggingBlockId && ($event.preventDefault(), dragOverBlockId = block.id)
            "
            @dragleave="dragOverBlockId === block.id && (dragOverBlockId = undefined)"
            @drop="dropBlock($event, block)"
          >
            <div
              class="field-block-head"
              :class="{ selected: selectedBlock?.id === block.id }"
            >
              <button
                class="drag-handle"
                type="button"
                draggable="true"
                aria-label="拖动内容块排序"
                title="拖动调整内容块顺序"
                @click.stop.prevent
                @dragstart.stop="startBlockDrag($event, block)"
                @dragend="finishDrag"
              ><Rank /></button>
              <button
                class="field-block-title"
                type="button"
                :aria-expanded="expandedContentBlockId === block.id"
                :aria-label="`${block.title}，${expandedContentBlockId === block.id ? '收起' : '展开'}`"
                @click="toggleContentBlock(selectedChapter!, block)"
              >
                <span :class="['kind-mark', blockTone(block)]"><Files /></span
                ><span
                  ><b>{{ block.title }}</b></span
                >
              </button>
              <div class="field-block-actions">
                <el-button
                  v-if="block.standardGroupCode || block.id > 0"
                  text
                  :icon="EditPen"
                  :aria-label="block.standardGroupCode ? '配置模板布局' : '编辑内容块'"
                  :title="block.standardGroupCode ? '配置模板布局' : '编辑内容块'"
                  @click="editBlock(block)"
                /><el-button
                  v-if="block.id > 0"
                  text
                  type="danger"
                  :icon="Delete"
                  aria-label="删除内容块"
                  title="删除内容块"
                  @click="removeBlock(block)"
                />
              </div>
            </div>
            <div
              v-if="expandedContentBlockId === block.id"
              class="field-block-body"
            >
              <div
                v-for="mapping in block.mappings.filter((item) => item.controlTag || !item.standardFieldCode)"
                :key="mapping.id"
                class="field-line"
                :class="{
                  selected: selectedMapping?.id === mapping.id,
                  'drag-over': dragOverMappingId === mapping.id,
                }"
                role="button"
                tabindex="0"
                @click="
                  selectBlock(selectedChapter!, block, false);
                  selectMapping(mapping, true);
                "
                @keydown.enter="
                  selectBlock(selectedChapter!, block, false);
                  selectMapping(mapping, true);
                "
                @dragover.prevent.stop="dragOverMappingId = mapping.id"
                @dragleave.stop="
                  dragOverMappingId === mapping.id && (dragOverMappingId = undefined)
                "
                @drop.stop="dropMapping($event, block, mapping)"
              >
                <button
                  class="drag-handle field-drag-handle"
                  type="button"
                  draggable="true"
                  aria-label="拖动字段排序"
                  title="拖动调整字段顺序"
                  @click.stop.prevent
                  @dragstart.stop="startMappingDrag($event, mapping)"
                  @dragend="finishDrag"
                ><Rank /></button>
                <span
                  ><b>{{ standardFieldFor(mapping)?.label || mapping.wordLabel }}</b
                  ><small
                    >{{ standardFieldFor(mapping)?.fieldCode || "未绑定标准字段" }} ·
                    {{ standardFieldFor(mapping) ? "系统标准字段" : "旧模板字段" }}</small
                  ></span
                ><el-tag
                  size="small"
                  :type="standardFieldFor(mapping) ? 'success' : 'warning'"
                  >{{ standardFieldFor(mapping) ? "标准字段" : "待清理" }}</el-tag
                ><span class="field-line-actions"
                  ><el-button
                    text
                    type="primary"
                    :icon="Link"
                    :loading="bindingMappingId === mapping.id"
                    aria-label="绑定当前 Word 位置"
                    title="先在 Word 中选择文字，再点击绑定"
                    @click.stop="bindCurrentWordPosition(mapping)"
                  /></span
                >
                <div v-if="selectedMapping?.id === mapping.id && mappingDraft" class="inline-field-settings" @click.stop>
                  <el-form label-position="top" class="inspector-form field-detail-form">
                    <div class="form-inline">
                      <el-form-item label="空值处理"><el-select v-model="mappingDraft.fillRule"><el-option v-for="item in fillRuleOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
                      <el-form-item label="冲突/合并行为"><el-select v-model="mappingDraft.mergeRule"><el-option v-for="item in mergeRuleOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
                    </div>
                    <div class="switches"><el-checkbox v-model="mappingDraft.required">生成前必须有值</el-checkbox><el-checkbox v-model="mappingDraft.enabled">启用</el-checkbox></div>
                    <div class="word-binding-actions">
                      <el-button type="primary" plain :icon="Link" :loading="bindingMappingId === mapping.id" @click="bindCurrentWordPosition(mapping)">绑定当前 Word 位置</el-button>
                      <el-button plain :icon="Unlock" :loading="unbindingWord" @click="unbindCurrentWordPosition">解除当前绑定</el-button>
                    </div>
                    <div class="field-detail-actions"><el-button type="primary" :loading="saving" @click="saveMapping">保存字段配置</el-button></div>
                  </el-form>
                </div>
              </div>
              <div v-if="block.standardFields?.length" class="standard-block-fields">
                <template v-for="field in block.standardFields" :key="field.fieldCode">
                  <div v-if="!block.mappings.some((mapping) => mapping.standardFieldCode === field.fieldCode && mapping.controlTag)" class="field-line standard-unbound-field" :class="{ selected: mappingDraft?.standardFieldCode === field.fieldCode }">
                    <span><b>{{ field.label }}</b><small>{{ field.fieldCode }}</small></span>
                    <el-tag size="small" type="info">未配置模板绑定</el-tag>
                    <span class="field-line-actions">
                      <el-button plain type="primary" :icon="Link" @click.stop="addMapping(block, field)">配置绑定</el-button>
                    </span>
                    <div v-if="mappingDraft?.standardFieldCode === field.fieldCode" class="inline-field-settings" @click.stop>
                      <el-form label-position="top" class="inspector-form field-detail-form">
                        <div class="form-inline">
                          <el-form-item label="空值处理"><el-select v-model="mappingDraft.fillRule"><el-option v-for="item in fillRuleOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
                          <el-form-item label="冲突/合并行为"><el-select v-model="mappingDraft.mergeRule"><el-option v-for="item in mergeRuleOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
                        </div>
                        <div class="switches"><el-checkbox v-model="mappingDraft.required">生成前必须有值</el-checkbox><el-checkbox v-model="mappingDraft.enabled">启用</el-checkbox></div>
                        <div class="word-binding-actions">
                          <el-button type="primary" plain :icon="Link" :loading="mappingDraft.id !== undefined && bindingMappingId === mappingDraft.id" @click="mappingDraft.id ? bindCurrentWordPosition(mappingDraft as MappingRule) : $emit('saveMapping')">{{ mappingDraft.id ? '绑定当前 Word 位置' : '保存后绑定 Word 位置' }}</el-button>
                        </div>
                        <div class="field-detail-actions"><el-button type="primary" :loading="saving" @click="saveMapping">保存字段配置</el-button></div>
                      </el-form>
                    </div>
                  </div>
                </template>
              </div>
              <div v-if="!block.mappings.length && !block.standardFields?.length && !mappingDraft" class="block-empty">
                当前内容块还没有字段
              </div>
            </div>
          </div>
          </template>
          <div v-if="selectedChapter && !displayBlocks.length" class="inspector-empty">
            <Files /><strong>本章节暂无系统标准编组</strong>
          </div>
        </div>
      </aside>
</template>

<style scoped src="./admin-inspector.css"></style>
