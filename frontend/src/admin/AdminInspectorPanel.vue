<script setup lang="ts">
import { Delete, EditPen, Files, Link, Plus, Rank, Unlock } from '@element-plus/icons-vue'
import type { DesignerBlock, DesignerChapter, MappingRule, StandardField } from '../admin-api'
import StandardFieldPicker from '../StandardFieldPicker.vue'
import { blockTone, sourceTagType } from './designer-formatters'

defineProps<{
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
const emit = defineEmits<{
  saveChapter: []
  editBlock: [block?: DesignerBlock]
  startBlockDrag: [event: DragEvent, block: DesignerBlock]
  finishDrag: []
  toggleBlock: [chapter: DesignerChapter, block: DesignerBlock]
  addMapping: [block: DesignerBlock]
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
const mappingDraft = defineModel<Partial<MappingRule> | undefined>('mappingDraft', { required: true })
const advancedOpen = defineModel<boolean>('advancedOpen', { required: true })
const dragOverBlockId = defineModel<number | undefined>('dragOverBlockId', { required: true })
const dragOverMappingId = defineModel<number | undefined>('dragOverMappingId', { required: true })

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

const saveChapterFromInspector = () => emit('saveChapter')
const editBlock = (block?: DesignerBlock) => emit('editBlock', block)
const startBlockDrag = (event: DragEvent, block: DesignerBlock) => emit('startBlockDrag', event, block)
const finishDrag = () => emit('finishDrag')
const toggleContentBlock = (chapter: DesignerChapter, block: DesignerBlock) => emit('toggleBlock', chapter, block)
const addMapping = (block: DesignerBlock) => emit('addMapping', block)
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
          <el-form
            v-if="selectedChapter"
            label-position="top"
            class="inspector-form"
            ><div class="inspector-subhead">
              <strong>章节属性</strong>
            </div>
            <div class="form-inline">
              <el-form-item label="章节编号"
                ><el-input v-model="selectedChapter.code" /></el-form-item
              ><el-form-item label="页码提示"
                ><el-input-number
                  v-model="selectedChapter.pageHint"
                  :min="1"
                  controls-position="right"
              /></el-form-item>
            </div>
            <el-form-item label="章节名称"
              ><el-input v-model="selectedChapter.title" /></el-form-item
            ><el-form-item label="排序号"
              ><el-input-number
                v-model="selectedChapter.orderNo"
                :min="0"
                controls-position="right"
            /></el-form-item>
            <div class="chapter-save-row">
              <el-checkbox v-model="selectedChapter.enabled"
                >启用章节</el-checkbox
              ><el-button
                type="primary"
                plain
                :loading="saving"
                @click="saveChapterFromInspector"
                >保存章节属性</el-button
              >
            </div></el-form
          >
          <div class="inspector-subhead fields-head">
            <div>
              <strong>本章节内容块与字段</strong>
            </div>
            <el-button type="primary" plain :icon="Plus" @click="editBlock()"
              >新增内容块</el-button
            >
          </div>
          <div
            v-for="block in selectedChapter?.blocks"
            :key="block.id"
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
                  text
                  :icon="Plus"
                  aria-label="在内容块中新增字段"
                  title="新增字段"
                  @click="addMapping(block)"
                /><el-button
                  text
                  :icon="EditPen"
                  aria-label="编辑内容块"
                  title="编辑内容块"
                  @click="editBlock(block)"
                /><el-button
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
                v-for="mapping in block.mappings"
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
                  ><b>{{ mapping.wordLabel }}</b
                  ><small
                    >{{ mapping.fieldCode }} ·
                    {{ sourceLabels[mapping.sourceType] || "其他来源" }}</small
                  ></span
                ><el-tag
                  size="small"
                  :type="sourceTagType(mapping.sourceType) as any"
                  >{{ sourceLabels[mapping.sourceType] || "其他来源" }}</el-tag
                ><span class="field-line-actions"
                  ><el-button
                    text
                    type="primary"
                    :icon="Link"
                    :loading="bindingMappingId === mapping.id"
                    aria-label="绑定当前 Word 位置"
                    title="先在 Word 中选择文字，再点击绑定"
                    @click.stop="bindCurrentWordPosition(mapping)"
                  /><el-button
                    text
                    type="danger"
                    :icon="Delete"
                    aria-label="删除字段"
                    title="删除字段"
                    @click.stop="removeMapping(mapping)"
                  /></span
                >
              </div>
              <div v-if="!block.mappings.length && !mappingDraft" class="block-empty">
                当前内容块还没有字段
              </div>
              <template v-if="mappingDraft">
                <div class="inspector-subhead detail-head">
                  <strong>{{
                    selectedMapping ? "字段详细设置" : "新字段设置"
                  }}</strong>
                </div>
                <el-form label-position="top" class="inspector-form field-detail-form"
                  ><div v-if="selectedMapping" class="word-binding-actions">
                    <el-button
                      type="primary"
                      plain
                      :icon="Link"
                      :loading="bindingMappingId === selectedMapping.id"
                      @click="bindCurrentWordPosition(selectedMapping)"
                      >绑定当前 Word 位置</el-button
                    ><el-button
                      plain
                      :icon="Unlock"
                      :loading="unbindingWord"
                      @click="unbindCurrentWordPosition"
                      >解除当前绑定</el-button
                    >
                  </div><el-form-item label="显示名称"
                    ><el-input v-model="mappingDraft.wordLabel"
                  /></el-form-item>
                  <StandardFieldPicker
                    :model-value="mappingDraft.standardFieldCode"
                    :fields="standardFields"
                    @open="$emit('refreshStandardFields')"
                    @select="selectStandardField"
                  />
                  <div class="form-inline">
                    <el-form-item label="空值处理"
                      ><el-select v-model="mappingDraft.fillRule"
                        ><el-option
                          v-for="item in fillRuleOptions"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value" /></el-select></el-form-item
                    ><el-form-item label="冲突/合并行为"
                      ><el-select v-model="mappingDraft.mergeRule"
                        ><el-option
                          v-for="item in mergeRuleOptions"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value" /></el-select
                    ></el-form-item>
                  </div>
                  <div class="switches">
                    <el-checkbox v-model="mappingDraft.required"
                      >生成前必须有值</el-checkbox
                    ><el-checkbox v-model="mappingDraft.enabled">启用</el-checkbox>
                  </div>
                  <div
                    class="advanced-toggle"
                    @click="advancedOpen = !advancedOpen"
                  >
                    <span>高级位置与结构设置</span
                    ><small>{{ advancedOpen ? "收起" : "展开" }}</small>
                  </div>
                  <div v-if="advancedOpen" class="advanced-fields">
                    <el-form-item label="字段编码"
                      ><el-input v-model="mappingDraft.fieldCode" readonly /></el-form-item
                    ><el-form-item label="Word 内容控件标记"
                      ><el-input v-model="mappingDraft.controlTag" readonly /></el-form-item
                    ><el-form-item label="Word 位置编码"
                      ><el-input v-model="mappingDraft.locationId" readonly
                    /></el-form-item>
                  </div>
                  <div class="field-detail-actions">
                    <el-button
                      type="primary"
                      :loading="saving"
                      @click="saveMapping"
                      >{{
                        selectedMapping ? "保存字段修改" : "保存新增字段"
                      }}</el-button
                    >
                  </div></el-form
                >
              </template>
            </div>
          </div>
          <div v-if="!selectedChapter?.blocks.length" class="inspector-empty">
            <Files /><strong>本章节暂时没有内容块</strong>
          </div>
        </div>
      </aside>
</template>

<style scoped src="./admin-inspector.css"></style>
