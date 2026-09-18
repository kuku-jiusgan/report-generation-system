<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock, Delete, Download, EditPen, Refresh, Search, UploadFilled, View } from '@element-plus/icons-vue'
import type { ReportTask } from '../api'
import { REPORT_STATUS_META, type ReportHubRow } from '../report-hub'

const props = defineProps<{
  rows: ReportHubRow[]
  total: number
  loading: boolean
  loadError: string
  query: string
  dates: [Date, Date] | []
  actionId: string
  canCreate: boolean
  canEdit: boolean
  canGenerate: boolean
  canDownload: boolean
}>()

const emit = defineEmits<{
  'update:query': [value: string]
  'update:dates': [value: [Date, Date] | []]
  reload: []
  clear: []
  create: []
  select: [reports: ReportTask[]]
  open: [report: ReportTask]
  regenerate: [report: ReportTask]
  replace: [report: ReportTask]
  downloadWord: [report: ReportTask]
  downloadPdf: [report: ReportTask]
  audit: [report: ReportTask]
  remove: [report: ReportTask]
  batchDownload: []
  batchRemove: []
}>()

const queueRoot = ref<HTMLElement>()
const compact = ref(false)
const narrow = ref(false)
const selectedCount = ref(0)
let observer: ResizeObserver | undefined

function statusMeta(row: ReportHubRow) {
  return REPORT_STATUS_META[row.lifecycle]
}

function updateDensity(width: number) {
  compact.value = width < 1160
  narrow.value = width < 1000
}

function updateDates(value: Date[] | null) {
  emit('update:dates', value?.length === 2 ? [value[0], value[1]] : [])
}

function updateSelection(rows: ReportHubRow[]) {
  selectedCount.value = rows.length
  emit('select', rows.map((row) => row.report))
}

function canOperate(row: ReportHubRow) {
  return props.canEdit && row.isOwned
}

onMounted(() => {
  if (!queueRoot.value) return
  updateDensity(queueRoot.value.clientWidth)
  observer = new ResizeObserver(([entry]) => updateDensity(entry.contentRect.width))
  observer.observe(queueRoot.value)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <section ref="queueRoot" class="hub-queue" aria-label="报告工作队列">
    <div class="hub-filters">
      <el-input
        :model-value="query"
        :prefix-icon="Search"
        clearable
        aria-label="搜索报告"
        placeholder="搜索报告名称、编号、项目号或实验记录"
        @update:model-value="emit('update:query', String($event))"
      />
      <el-date-picker
        :model-value="dates"
        type="datetimerange"
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        @update:model-value="updateDates"
      />
      <el-tooltip content="刷新报告列表" placement="bottom">
        <el-button class="hub-refresh" :icon="Refresh" :loading="loading" aria-label="刷新报告列表" @click="emit('reload')" />
      </el-tooltip>
    </div>

    <div v-if="selectedCount" class="hub-batch" aria-live="polite">
      <strong>已选择 {{ selectedCount }} 份报告</strong>
      <el-button v-if="canDownload" type="primary" plain :icon="Download" :loading="actionId === 'batch'" @click="emit('batchDownload')">批量导出</el-button>
      <el-button type="danger" plain :icon="Delete" @click="emit('batchRemove')">批量删除</el-button>
    </div>

    <div v-else-if="loadError && rows.length" class="hub-load-error" role="alert">
      <span>{{ loadError }}，当前显示上次成功加载的数据。</span>
      <el-button link type="primary" :icon="Refresh" :loading="loading" @click="emit('reload')">重新加载</el-button>
    </div>

    <div class="hub-table-wrap">
      <el-table
        v-loading="loading"
        :data="rows"
        row-key="id"
        height="100%"
        @selection-change="updateSelection"
        @row-dblclick="canOperate($event) && emit('open', $event.report)"
      >
        <el-table-column type="selection" width="44" :selectable="canOperate" />
        <el-table-column label="报告名称" min-width="240">
          <template #default="{ row }">
            <el-tooltip :content="row.title" :trigger="['hover', 'focus']" placement="top-start">
              <button v-if="canOperate(row)" class="hub-report-link" type="button" @click="emit('open', row.report)">{{ row.title }}</button>
              <strong v-else class="hub-report-title">{{ row.title }}</strong>
            </el-tooltip>
            <small>{{ row.reportNo }}<span v-if="row.sources"> · {{ row.sources }}</span></small>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="108">
          <template #default="{ row }">
            <el-tag class="hub-status-tag" size="small" effect="light" :type="statusMeta(row).type">
              {{ statusMeta(row).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="!narrow" label="项目号" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.projectNumber }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="168">
          <template #default="{ row }">{{ row.updatedAt }}</template>
        </el-table-column>
        <el-table-column v-if="!compact" label="实验记录" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">{{ row.experimentNames }}</template>
        </el-table-column>
        <el-table-column v-if="!narrow" label="创建人" width="96">
          <template #default="{ row }">{{ row.creator }}</template>
        </el-table-column>
        <el-table-column label="操作" width="184" fixed="right" align="center" header-align="center">
          <template #default="{ row }">
            <div v-if="canOperate(row)" class="hub-actions">
              <el-button link type="primary" :icon="EditPen" @click="emit('open', row.report)">编辑/复核</el-button>
              <el-dropdown trigger="click">
                <el-button link :loading="actionId === row.id">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="canGenerate" :icon="Refresh" @click="emit('regenerate', row.report)">重新生成</el-dropdown-item>
                    <el-dropdown-item :icon="UploadFilled" @click="emit('replace', row.report)">更换数据源</el-dropdown-item>
                    <el-dropdown-item v-if="canGenerate && canDownload" :icon="Download" @click="emit('downloadWord', row.report)">导出 Word</el-dropdown-item>
                    <el-dropdown-item v-if="canDownload" :icon="View" @click="emit('downloadPdf', row.report)">导出 PDF</el-dropdown-item>
                    <el-dropdown-item :icon="Clock" @click="emit('audit', row.report)">查看 Audit Trail</el-dropdown-item>
                    <el-dropdown-item divided :icon="Delete" @click="emit('remove', row.report)">删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <el-tag v-else class="hub-readonly-tag" size="small" type="info" effect="plain">
              {{ row.isOwned ? '只读' : '跨用户只读' }}
            </el-tag>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty v-if="loadError" :description="loadError" :image-size="64">
            <el-button type="primary" plain :icon="Refresh" @click="emit('reload')">重新加载</el-button>
          </el-empty>
          <el-empty v-else-if="query || dates.length" description="没有符合当前条件的报告" :image-size="64">
            <el-button @click="emit('clear')">清除筛选</el-button>
          </el-empty>
          <el-empty v-else description="还没有报告" :image-size="64">
            <el-button v-if="canCreate" type="primary" @click="emit('create')">新建报告</el-button>
          </el-empty>
        </template>
      </el-table>
    </div>

    <footer class="hub-table-footer">
      <span>当前显示 {{ rows.length }} 份</span>
      <span>共 {{ total }} 份报告</span>
    </footer>
  </section>
</template>
