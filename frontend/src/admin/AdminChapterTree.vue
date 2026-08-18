<script setup lang="ts">
import { EditPen, Plus, Refresh, Search, Warning } from '@element-plus/icons-vue'
import type { DesignerBlock, DesignerChapter } from '../admin-api'
import { blockTone, chapterTitle } from './designer-formatters'

defineProps<{
  chapters: DesignerChapter[]
  selectedChapterId?: number
  selectedBlockId?: number
  expanded: number[]
  mappings: number
  pending: number
}>()
defineEmits<{
  refresh: []
  editChapter: [chapter?: DesignerChapter, parent?: DesignerChapter]
  removeChapter: [chapter: DesignerChapter]
  selectChapter: [chapter: DesignerChapter]
  selectBlock: [chapter: DesignerChapter, block: DesignerBlock]
}>()
const search = defineModel<string>('search', { required: true })
</script>

<template>
  <aside class="chapter-panel">
    <div class="panel-title">
      <strong>章节目录树</strong>
      <div class="tree-actions"><el-button text :icon="Plus" aria-label="新增根章节" @click="$emit('editChapter')" /><el-button text :icon="Refresh" aria-label="刷新章节" @click="$emit('refresh')" /></div>
    </div>
    <el-input v-model="search" class="chapter-search" :prefix-icon="Search" placeholder="搜索章节、字段或表格" clearable />
    <div class="coverage-line"><span><i class="ready" />已配置 {{ mappings - pending }}</span><span><i class="pending" />待完善 {{ pending }}</span></div>
    <div class="chapter-scroll">
      <section v-for="chapter in chapters" :key="chapter.id" class="chapter-group">
        <div class="chapter-row" :class="{ selected: selectedChapterId === chapter.id }">
          <button @click="$emit('selectChapter', chapter)"><span>{{ chapterTitle(chapter) }}</span><small>{{ chapter.pageHint || '' }}</small></button>
          <div class="tree-row-actions">
            <el-button text :icon="Plus" aria-label="新增子章节" @click="$emit('editChapter', undefined, chapter)" />
            <el-button text :icon="EditPen" aria-label="编辑章节" @click="$emit('editChapter', chapter)" />
            <el-button text :icon="Warning" aria-label="删除章节" @click="$emit('removeChapter', chapter)" />
          </div>
        </div>
        <div v-if="expanded.includes(chapter.id)" class="section-list">
          <div v-for="child in chapter.children" :key="child.id" class="section-group">
            <div class="section-row" :class="{ selected: selectedChapterId === child.id }">
              <button @click="$emit('selectChapter', child)"><span>{{ chapterTitle(child) }}</span><small>{{ child.pageHint || '' }}</small></button>
              <div class="tree-row-actions"><el-button text :icon="EditPen" aria-label="编辑章节" @click="$emit('editChapter', child)" /><el-button text :icon="Warning" aria-label="删除章节" @click="$emit('removeChapter', child)" /></div>
            </div>
            <button v-for="block in child.blocks" :key="block.id" class="block-row" :class="[{ selected: selectedBlockId === block.id }, blockTone(block)]" @click="$emit('selectBlock', child, block)"><i /><span><b>{{ block.title }}</b></span><Warning v-if="block.status === 'PENDING'" /></button>
          </div>
        </div>
        <button v-for="block in chapter.blocks" :key="block.id" class="block-row" :class="[{ selected: selectedBlockId === block.id }, blockTone(block)]" @click="$emit('selectBlock', chapter, block)"><i /><span><b>{{ block.title }}</b></span><Warning v-if="block.status === 'PENDING'" /></button>
      </section>
      <div v-if="!chapters.length" class="tree-empty">没有匹配的章节或字段</div>
    </div>
  </aside>
</template>

<style scoped>
.chapter-panel { min-width: 0; height: 100%; min-height: 0; display: flex; flex-direction: column; overflow: hidden; background: #fff; border-right: 1px solid #e4eaf2; }
.panel-title { min-height: 58px; padding: 0 12px 0 15px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e4e8e6; }
.panel-title strong { color: #183f36; font-size: 13px; }
.tree-actions, .tree-row-actions { display: flex; align-items: center; }.tree-actions :deep(.el-button), .tree-row-actions :deep(.el-button) { margin: 0; padding: 4px; color: #73817b; }
.tree-row-actions { opacity: 0; }.chapter-row:hover .tree-row-actions, .section-row:hover .tree-row-actions, .chapter-row.selected .tree-row-actions, .section-row.selected .tree-row-actions { opacity: 1; }
.chapter-search { padding: 12px 13px 8px; }.coverage-line { padding: 0 15px 10px; display: flex; gap: 13px; color: #6f7c77; font-size: 9px; border-bottom: 1px solid #f4f7fb; }
.coverage-line span { display: flex; align-items: center; gap: 5px; }.coverage-line i { width: 7px; height: 7px; border-radius: 50%; }.coverage-line .ready { background: #3e8b70; }.coverage-line .pending { background: #c38a3c; }
.chapter-scroll { min-height: 0; flex: 1; overflow: auto; padding: 7px 0 22px; }.chapter-group { border-bottom: 1px solid #f4f7fb; }
.chapter-row, .section-row { min-height: 35px; padding: 0 7px 0 12px; display: flex; align-items: center; justify-content: space-between; }
.chapter-row > button, .section-row > button { min-width: 0; flex: 1; height: 35px; display: flex; align-items: center; justify-content: space-between; color: #29463e; border: 0; background: transparent; text-align: left; cursor: pointer; }
.chapter-row > button span, .section-row > button span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.chapter-row small, .section-row small { min-width: 22px; color: #8b9691; font-size: 9px; text-align: right; }
.chapter-row:hover, .chapter-row.selected, .section-row:hover, .section-row.selected { background: #eaf3f0; }.chapter-row.selected { box-shadow: inset 3px 0 #216b5a; }.chapter-row > button { font-size: 11px; font-weight: 700; }
.section-row { padding-left: 27px; }.section-row > button { color: #64736e; font-size: 10px; }
.block-row { width: 100%; min-height: 40px; padding: 6px 12px 6px 34px; display: grid; grid-template-columns: 8px minmax(0, 1fr) 14px; align-items: center; gap: 8px; color: #40534c; border: 0; background: transparent; text-align: left; cursor: pointer; }
.block-row > i { width: 7px; height: 7px; border-radius: 2px; background: #6cae9c; }.block-row b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }
.block-row:hover { background: #f4f7f6; }.block-row.selected { background: #e7f1ee; box-shadow: inset 3px 0 #216b5a; }.block-row.pending > i { background: #c68a3b; }.block-row.disabled { opacity: .55; }
.tree-empty { padding: 24px; color: #84918c; font-size: 10px; text-align: center; }
.chapter-panel .block-row { display: none; }
</style>
