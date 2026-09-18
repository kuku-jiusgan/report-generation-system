<script setup lang="ts">
import type { ReportHubStats, ReportHubTab } from '../report-hub'

const props = defineProps<{ stats: ReportHubStats; active: ReportHubTab; canViewAll: boolean }>()
const emit = defineEmits<{ select: [tab: ReportHubTab] }>()

const items: Array<{ key: ReportHubTab; label: string; count: keyof ReportHubStats }> = [
  { key: 'MINE', label: '我的报告', count: 'mine' },
  { key: 'DRAFT', label: '草稿', count: 'draft' },
  { key: 'REVIEW', label: '待复核', count: 'review' },
  { key: 'REVIEWED', label: '已复核', count: 'reviewed' },
  { key: 'COMPLETED', label: '已完成', count: 'completed' },
  { key: 'ALL', label: '全部报告', count: 'all' },
]
</script>

<template>
  <nav class="hub-status-strip" aria-label="报告状态快速筛选">
    <button
      v-for="item in items.filter((item) => item.key !== 'ALL' || canViewAll)"
      :key="item.key"
      type="button"
      :class="{ active: props.active === item.key }"
      :aria-pressed="props.active === item.key"
      @click="emit('select', item.key)"
    >
      <span>{{ item.label }}</span>
      <b>{{ stats[item.count] }}</b>
    </button>
  </nav>
</template>
