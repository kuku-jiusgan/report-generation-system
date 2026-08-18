<script setup lang="ts">
import { computed } from 'vue'
import type { StandardField, SystemFieldGroup } from './admin-api'

const props = defineProps<{
  rows: any[]; groups: SystemFieldGroup[]; fields: StandardField[]; unmapped: StandardField[];
  selectedCode?: string; loading: boolean
}>()
const emit = defineEmits<{ toggle: [id: number]; select: [field: StandardField, chapterId?: number] }>()
type ResolvedGroup = SystemFieldGroup & { resolvedFields: StandardField[] }
function groupsFor(row: any): ResolvedGroup[] {
  return props.groups.filter((group) => group.chapterIds.includes(row.node.id)).map((group) => ({
    ...group, resolvedFields: group.fields
      .map((field) => props.fields.find((item) => item.fieldCode === field.fieldCode))
      .filter((field): field is StandardField => Boolean(field)),
  })) as ResolvedGroup[]
}
function groupedCodes(row: any) {
  return new Set(groupsFor(row).flatMap((group) => group.resolvedFields.map((field: any) => field.fieldCode)))
}
const empty = computed(() => !props.loading && !props.rows.length && !props.unmapped.length)
</script>

<template>
  <div v-loading="loading" class="field-list">
    <div v-for="row in rows" :key="row.node.id" class="chapter-entry">
      <button class="chapter-row" :class="{ muted: !row.node.enabled }" :style="{ '--chapter-depth': row.depth }" :aria-expanded="row.open" @click="emit('toggle', row.node.id)">
        <span class="chapter-caret" :class="{ open: row.open }">›</span><span class="chapter-code">{{ row.node.code }}</span><b>{{ row.node.title }}</b><span class="chapter-count">{{ row.node.fieldCount }}</span>
      </button>
      <template v-if="row.open">
        <section v-for="group in groupsFor(row)" :key="group.groupCode" class="group-node" :style="{ '--chapter-depth': row.depth }">
          <header><b>{{ group.label }}</b><small>{{ group.cardinality === 'MANY' ? '数组' : '单值' }} · {{ group.resolvedFields.length }} 个字段</small></header>
          <button v-for="item in group.resolvedFields" :key="item.fieldCode" class="field-item" :class="{ selected: selectedCode === item.fieldCode }" @click="emit('select', item, row.node.id)">
            <span><b>{{ item.label }}</b><small>{{ item.fieldCode }}</small></span><span class="field-state" :class="{ disabled: !item.enabled }" />
          </button>
          <p v-if="!group.resolvedFields.length" class="group-empty">该编组暂未配置字段</p>
        </section>
        <div class="chapter-fields" :style="{ '--chapter-depth': row.depth }">
          <button v-for="item in row.node.fields.filter((field: StandardField) => !groupedCodes(row).has(field.fieldCode))" :key="item.fieldCode" class="field-item" :class="{ selected: selectedCode === item.fieldCode }" @click="emit('select', item, row.node.id)">
            <span><b>{{ item.label }}</b><small>{{ item.fieldCode }}</small></span><span class="field-state" :class="{ disabled: !item.enabled }" />
          </button>
        </div>
      </template>
    </div>
    <section v-if="unmapped.length" class="unmapped-fields"><h2>未映射字段<span>{{ unmapped.length }}</span></h2><button v-for="item in unmapped" :key="item.fieldCode" class="field-item" :class="{ selected: selectedCode === item.fieldCode }" @click="emit('select', item)"><span><b>{{ item.label }}</b><small>{{ item.fieldCode }}</small></span></button></section>
    <el-empty v-if="empty" :image-size="52" description="没有匹配的字段或章节" />
  </div>
</template>

<style scoped>
.field-list{padding:8px 4px}.chapter-entry{margin-bottom:7px}.chapter-row{display:flex;align-items:center;gap:7px;width:100%;padding:9px 10px;border:1px solid #dfe7ef;border-radius:7px;background:#f8fafc;color:#263746;text-align:left;cursor:pointer}.chapter-row:hover{border-color:#8eb5d2;background:#f1f7fb}.chapter-row b{flex:1;font-size:13px}.chapter-code{color:#6b8091;font:11px ui-monospace,monospace}.chapter-count{color:#6b8091;font-size:11px}.chapter-caret{font-size:18px;transition:transform .15s}.chapter-caret.open{transform:rotate(90deg)}.field-item{display:flex;align-items:center;justify-content:space-between;width:100%;padding:7px 9px;border:0;border-radius:5px;background:transparent;text-align:left;cursor:pointer}.field-item:hover{background:#edf5fa}.field-item.selected{background:#dcecf7;color:#14547a}.field-item span:first-child{display:flex;flex-direction:column;min-width:0}.field-item b{font-size:12px;font-weight:600}.field-item small{overflow:hidden;color:#7890a0;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.field-state{width:7px;height:7px;border-radius:50%;background:#47a67d}.field-state.disabled{background:#aab5bf}.chapter-fields{margin-left:calc(18px + var(--chapter-depth)*12px);padding:4px 0 4px 10px}.group-node{margin:6px 0 8px calc(18px + var(--chapter-depth)*12px);border:1px solid #d8e5ef;border-radius:7px;background:#fbfdff;padding:4px 5px 6px 8px}.group-node header{display:flex;justify-content:space-between;padding:5px 4px;color:#34495e}.group-node header small{color:#718096;font-size:10px}.group-empty{margin:3px 4px 5px;color:#9aaab6;font-size:11px}.unmapped-fields{margin:14px 0 0;padding-top:10px;border-top:1px dashed #cbd8e2}.unmapped-fields h2{display:flex;justify-content:space-between;padding:0 8px;color:#5c7180;font-size:12px}.unmapped-fields h2 span{color:#9a6b2f}
</style>
