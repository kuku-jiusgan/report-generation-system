<script setup lang="ts">
import { computed } from 'vue'
import type { StandardField, StandardFieldCatalogChapter, SystemFieldGroup } from './admin-api'

const emit = defineEmits<{ select: [field: StandardField, chapterId?: number]; group: [group: SystemFieldGroup]; chapter: [chapter: StandardFieldCatalogChapter] }>()
const props = withDefaults(defineProps<{
  chapters: StandardFieldCatalogChapter[]
  groups: SystemFieldGroup[]
  fields: StandardField[]
  unmappedFields?: StandardField[]
  keyword?: string
  selectedCode?: string
  selectedGroup?: string
}>(), { unmappedFields: () => [], keyword: '' })

interface CatalogTreeNode {
  id: number | string
  title: string
  code?: string
  field?: StandardField
  group?: SystemFieldGroup
  chapter?: StandardFieldCatalogChapter
  unmapped?: boolean
  children?: CatalogTreeNode[]
}

const normalizedKeyword = computed(() => props.keyword.trim().toLowerCase())
function matches(...values: unknown[]) {
  return !normalizedKeyword.value
    || values.some((value) => String(value || '').toLowerCase().includes(normalizedKeyword.value))
}
function fieldMatches(field: StandardField) {
  return matches(field.label, field.fieldCode, field.groupCode)
}
function fieldsFor(group: SystemFieldGroup) {
  return group.fields
    .map((item) => props.fields.find((field) => field.fieldCode === item.fieldCode))
    .filter((field): field is StandardField => Boolean(field))
    .sort((a, b) => a.orderNo - b.orderNo || a.id - b.id)
}
function sortedFields(fields: StandardField[]) {
  return [...fields].sort((a, b) => a.orderNo - b.orderNo || a.id - b.id)
}
function fieldNode(field: StandardField): CatalogTreeNode {
  return { id: `field:${field.fieldCode}`, title: field.label, field }
}
function groupNode(group: SystemFieldGroup, includeAll: boolean): CatalogTreeNode | undefined {
  const groupMatches = includeAll || matches(group.label, group.groupCode)
  const children = fieldsFor(group)
    .filter((field) => groupMatches || fieldMatches(field))
    .map(fieldNode)
  if (normalizedKeyword.value && !groupMatches && !children.length) return undefined
  return { id: `group:${group.groupCode}`, title: group.label, group, children }
}
function chapterNode(chapter: StandardFieldCatalogChapter, includeAll = false): CatalogTreeNode | undefined {
  const chapterMatches = includeAll || matches(chapter.code, chapter.title)
  const directFields = sortedFields(chapter.fields)
    .filter((field) => chapterMatches || fieldMatches(field))
    .map(fieldNode)
  const groups = props.groups
    .filter((group) => group.chapterIds.includes(chapter.id))
    .map((group) => groupNode(group, chapterMatches))
    .filter((group): group is CatalogTreeNode => Boolean(group))
  const children = chapter.children
    .map((child) => chapterNode(child, chapterMatches))
    .filter((child): child is CatalogTreeNode => Boolean(child))
  if (normalizedKeyword.value && !chapterMatches && !directFields.length && !groups.length && !children.length) {
    return undefined
  }
  return {
    id: chapter.id,
    code: chapter.code,
    title: chapter.title,
    chapter,
    children: [...directFields, ...groups, ...children],
  }
}
function unmappedNode(): CatalogTreeNode | undefined {
  const title = '未归属字段'
  const headingMatches = matches(title)
  const children = sortedFields(props.unmappedFields)
    .filter((field) => headingMatches || fieldMatches(field))
    .map(fieldNode)
  if (!children.length) return undefined
  return { id: 'unmapped-fields', title, unmapped: true, children }
}
const tree = computed(() => [
  ...props.chapters.map((chapter) => chapterNode(chapter)).filter((chapter): chapter is CatalogTreeNode => Boolean(chapter)),
  ...([unmappedNode()].filter((node): node is CatalogTreeNode => Boolean(node))),
])
function nodeClick(data: CatalogTreeNode) {
  if (data.field) emit('select', data.field)
  else if (data.group) emit('group', data.group)
  else if (data.chapter) emit('chapter', data.chapter)
}
</script>
<template>
  <el-tree :data="tree" node-key="id" default-expand-all class="catalog-tree" @node-click="nodeClick">
    <template #default="{ data }">
      <div v-if="data.group" class="tree-group" @click.stop="emit('group', data.group)">
        <span>{{ data.title }}</span>
      </div>
      <div v-else-if="data.field" class="tree-field" @click.stop="emit('select', data.field)">{{ data.title }}</div>
      <div v-else-if="data.unmapped" class="tree-unmapped">{{ data.title }}</div>
      <div v-else-if="data.chapter" class="tree-chapter" @click.stop="emit('chapter', data.chapter)">
        <span>{{ data.code }} {{ data.title }}</span>
      </div>
    </template>
  </el-tree>
</template>
<style scoped>
.catalog-tree{border:0;background:transparent;flex:1;min-height:0;overflow:auto}.tree-chapter,.tree-group{display:flex;align-items:center;justify-content:space-between;width:100%;padding-right:8px;font-size:12px}.tree-field,.tree-unmapped{font-size:12px}.tree-unmapped{color:#657187;font-weight:600}
</style>
