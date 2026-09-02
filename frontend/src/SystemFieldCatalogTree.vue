<script setup lang="ts">
import { computed } from 'vue'
import type { StandardField, StandardFieldCatalogChapter, SystemFieldGroup } from './admin-api'

const emit = defineEmits<{ select: [field: StandardField, chapterId?: number]; group: [group: SystemFieldGroup]; chapter: [chapter: StandardFieldCatalogChapter] }>()
const props = defineProps<{
  chapters: any[]
  groups: SystemFieldGroup[]
  fields: StandardField[]
  selectedCode?: string
  selectedGroup?: string
}>()
function fieldsFor(group: SystemFieldGroup, all: StandardField[]) {
  return group.fields.map((item) => all.find((field) => field.fieldCode === item.fieldCode)).filter(Boolean) as StandardField[]
}
function enrichChapter(chapter: any): any {
  return { ...chapter, children: [
    ...(chapter.fields || []).map((field: StandardField) => ({ id: `field:${field.fieldCode}`, title: field.label, field })),
    ...props.groups.filter((group) => group.chapterIds.includes(chapter.id)).map((group) => ({ id: `group:${group.groupCode}`, title: group.label, group, children: fieldsFor(group, props.fields).map((field) => ({ id: `field:${field.fieldCode}`, title: field.label, field })) })),
    ...(chapter.children || []).map((child: any) => enrichChapter(child)),
  ] }
}
const tree = computed(() => props.chapters.map((chapter) => enrichChapter(chapter)))
function nodeClick(data: any) {
  if (data.field) emit('select', data.field)
  else if (data.group) emit('group', data.group)
  else emit('chapter', data)
}
</script>
<template>
  <el-tree :data="tree" node-key="id" default-expand-all class="catalog-tree" @node-click="nodeClick">
    <template #default="{ data }">
      <div v-if="data.group" class="tree-group" @click.stop="emit('group', data.group)">
        <span>{{ data.title }}</span>
      </div>
      <div v-else-if="data.field" class="tree-field" @click.stop="emit('select', data.field)">{{ data.title }}</div>
      <div v-else class="tree-chapter" @click.stop="emit('chapter', data)">
        <span>{{ data.code }} {{ data.title }}</span>
      </div>
    </template>
  </el-tree>
</template>
<style scoped>
.catalog-tree{border:0;background:transparent;flex:1;min-height:0;overflow:auto}.tree-chapter,.tree-group{display:flex;align-items:center;justify-content:space-between;width:100%;padding-right:8px;font-size:12px}.tree-field{font-size:12px}
</style>
