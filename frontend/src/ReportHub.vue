<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Clock, Delete, Document, Download, EditPen, Expand, Files, Fold, Plus, Refresh,
  Search, SwitchButton, UploadFilled, View,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import {
  applyLimsToReport, batchExportReports, createReport, deleteReport, extractExcel, extractPdf, generateReport, getHistory,
  listReportGenerations, listReports, rebuildReport, replaceReportSource, reportGenerationFileUrl, reportPdfUrl, uploadExcel, uploadPdf,
  type ChangeEvent, type ReportGeneration, type ReportTask, type SourceDocument,
} from './api'
import {
  queryLimsProject, recognizeLimsInstances,
  type LimsImport, type LimsInstanceSummary, type LimsRecognition,
} from './lims-api'
import type { AuthUser } from './auth-api'
import ReportGenerationProgress from './ReportGenerationProgress.vue'

const props = defineProps<{ sessionUser: AuthUser }>()
const emit = defineEmits<{ open: [id: string]; logout: [] }>()
const reports = ref<ReportTask[]>([])
const generations = ref<ReportGeneration[]>([])
const loading = ref(false)
const actionId = ref('')
const auditVisible = ref(false)
const auditReport = ref<ReportTask>()
const auditEvents = ref<ChangeEvent[]>([])
const createVisible = ref(false)
const createBusy = ref(false)
const createRecognizing = ref(false)
const createProjectId = ref('')
const createImport = ref<LimsImport>()
const createInstances = ref<LimsInstanceSummary[]>([])
const createRecognition = ref<LimsRecognition>()
const createPdf = ref<File>()
const createPdfFiles = ref<UploadFile[]>([])
const createExcel = ref<File>()
const createExcelFiles = ref<UploadFile[]>([])
const createExcelSource = ref<SourceDocument>()
const replaceVisible = ref(false)
const replaceReport = ref<ReportTask>()
const replaceType = ref<'PDF' | 'EXCEL'>('EXCEL')
const replaceFile = ref<File>()
const replaceFiles = ref<UploadFile[]>([])
const createConflictResolutions = reactive<Record<string, string>>({})
const selected = ref<ReportTask[]>([])
const sidebarHovered = ref(false)
const sidebarPinned = ref(false)
const sidebarExpanded = computed(() => sidebarHovered.value || sidebarPinned.value)
const filters = reactive<{ query: string; status: string; dates: [Date, Date] | [] }>({
  query: '', status: '', dates: [],
})
let createRecognitionTimer: ReturnType<typeof setTimeout> | undefined
let createRecognitionSequence = 0
const generationProgress = reactive({ visible: false, stage: 0, percentage: 4, status: 'running' as 'running' | 'success' | 'error', message: '正在准备数据源', title: '' })
let generationTimer: ReturnType<typeof setInterval> | undefined

function startGenerationProgress() {
  generationProgress.visible = true; generationProgress.stage = 0; generationProgress.percentage = 4
  generationProgress.status = 'running'; generationProgress.message = '正在整理所选实验记录'
  generationProgress.title = createInstances.value.map((item) => item.title).join('、') || createPdf.value?.name || '新报告'
  generationTimer = setInterval(() => {
    if (generationProgress.percentage < 88) generationProgress.percentage += generationProgress.percentage < 55 ? 2 : 1
    if (generationProgress.percentage >= 18 && generationProgress.stage < 1) generationProgress.stage = 1
    if (generationProgress.percentage >= 38 && generationProgress.stage < 2) { generationProgress.stage = 2; generationProgress.message = '正在生成概述、目的等智能内容' }
    if (generationProgress.percentage >= 72 && generationProgress.stage < 3) { generationProgress.stage = 3; generationProgress.message = '正在填充并编译 Word 报告' }
  }, 900)
}
function stopGenerationTimer() { if (generationTimer) clearInterval(generationTimer); generationTimer = undefined }

const latestByReport = computed(() => {
  const result = new Map<string, ReportGeneration>()
  for (const item of generations.value) if (!result.has(item.report_id)) result.set(item.report_id, item)
  return result
})

function lifecycle(item: ReportTask) {
  const generation = latestByReport.value.get(item.id)
  if (generation?.status === 'PROCESSING') return 'GENERATING'
  if (generation?.status === 'FAILED') return 'FAILED'
  if (item.status === 'GENERATED') return 'COMPLETED'
  if (item.status === 'READY_TO_GENERATE') return 'REVIEW'
  return 'DRAFT'
}

const statusMeta: Record<string, { label: string; type: '' | 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
  DRAFT: { label: '草稿编辑', type: 'info' },
  GENERATING: { label: '生成中', type: 'warning' },
  REVIEW: { label: '待复核', type: 'primary' },
  COMPLETED: { label: '已完成导出', type: 'success' },
  FAILED: { label: '生成失败', type: 'danger' },
}

const filtered = computed(() => reports.value.filter((item) => {
  const data = item.resolved_data
  const samples = ((data.source_payloads?.LIMS?.samples || []) as Array<Record<string, unknown>>)
  const searchable = [item.title, data.report_no, data.sample, data.project_name,
    ...samples.flatMap((sample) => [sample.sampleName, sample.batchNo])].join(' ').toLowerCase()
  const queryMatches = !filters.query.trim() || searchable.includes(filters.query.trim().toLowerCase())
  const statusMatches = !filters.status || lifecycle(item) === filters.status
  const changed = new Date(item.updated_at).getTime()
  const dateMatches = !filters.dates.length || (changed >= filters.dates[0].getTime() && changed <= filters.dates[1].getTime())
  return queryMatches && statusMatches && dateMatches
}))

const stats = computed(() => ({
  total: reports.value.length,
  review: reports.value.filter((item) => lifecycle(item) === 'REVIEW').length,
  completed: reports.value.filter((item) => lifecycle(item) === 'COMPLETED').length,
  failed: reports.value.filter((item) => lifecycle(item) === 'FAILED').length,
}))

function projectNumber(item: ReportTask) {
  const lims = item.resolved_data.source_payloads?.LIMS
  const project = lims?.project as Record<string, unknown> | undefined
  return String(project?.id || '-').trim() || '-'
}

function generatedAt(item: ReportTask) {
  return latestByReport.value.get(item.id)?.generated_at || item.updated_at
}

function experimentRecordNames(item: ReportTask) {
  const lims = item.resolved_data.source_payloads?.LIMS
  const instances = (lims?.instances || []) as Array<Record<string, unknown>>
  const names = instances.map((instance) => String(instance.title || '').trim()).filter(Boolean)
  return [...new Set(names)].join('；') || '-'
}

async function load() {
  loading.value = true
  try {
    const [items, history] = await Promise.all([listReports(), listReportGenerations()])
    reports.value = items
    generations.value = history.items
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    loading.value = false
  }
}

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } }; message?: string }
  return value.response?.data?.detail || value.message || '操作失败'
}

function createNew() {
  if (createRecognitionTimer) clearTimeout(createRecognitionTimer)
  createRecognitionSequence += 1
  createProjectId.value = ''
  createImport.value = undefined
  createInstances.value = []
  createRecognition.value = undefined
  createPdf.value = undefined
  createPdfFiles.value = []
  createExcel.value = undefined
  createExcelFiles.value = []
  createExcelSource.value = undefined
  Object.keys(createConflictResolutions).forEach((key) => delete createConflictResolutions[key])
  createVisible.value = true
}

async function queryCreateProject() {
  if (!createProjectId.value.trim()) return ElMessage.warning('请输入项目编号')
  createBusy.value = true
  try {
    createImport.value = await queryLimsProject(createProjectId.value.trim())
    if (createRecognitionTimer) clearTimeout(createRecognitionTimer)
    createRecognitionSequence += 1
    createInstances.value = []
    createRecognition.value = undefined
    ElMessage.success(`查询到 ${createImport.value.summary.instanceCount} 条实验记录`)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    createBusy.value = false
  }
}

function selectCreateInstances(items: LimsInstanceSummary[]) {
  createInstances.value = items
  createRecognition.value = undefined
  Object.keys(createConflictResolutions).forEach((key) => delete createConflictResolutions[key])
  if (createRecognitionTimer) clearTimeout(createRecognitionTimer)
  const sequence = ++createRecognitionSequence
  if (!items.length) {
    createRecognizing.value = false
    return
  }
  createRecognizing.value = true
  createRecognitionTimer = setTimeout(() => void recognizeCreateInstances(sequence), 350)
}

async function recognizeCreateInstances(sequence = ++createRecognitionSequence) {
  if (!createImport.value || !createInstances.value.length) {
    createRecognizing.value = false
    return
  }
  const importId = createImport.value.id
  const instanceIds = createInstances.value.map((item) => item.instanceId)
  createRecognizing.value = true
  try {
    const result = await recognizeLimsInstances(importId, instanceIds)
    if (sequence !== createRecognitionSequence) return
    createRecognition.value = result
    ElMessage.success(`已自动识别 ${result.recognizedTotal} 条数据，合并 ${result.duplicateCount} 条重复数据`)
  } catch (error) {
    if (sequence === createRecognitionSequence) ElMessage.error(errorText(error))
  } finally {
    if (sequence === createRecognitionSequence) createRecognizing.value = false
  }
}

const conflictFieldLabels: Record<string, string> = {
  name: '名称', grade: '级别', batchNo: '批号', manufacturer: '厂家', expiryDate: '有效期',
  sampleName: '样品名称', sampleNo: '样品编号', model: '型号', serialNo: '序列号',
}

function differingConflictFields(options: LimsRecognition['conflicts'][number]['options']) {
  const values = options.map((option) => option.value as Record<string, unknown>)
  const keys = [...new Set(values.flatMap((value) => Object.keys(value)))]
  return keys.filter((key) => new Set(values.map((value) => JSON.stringify(value[key] ?? null))).size > 1)
}

function conflictValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '空'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function selectCreatePdf(file: UploadFile) {
  createPdf.value = file.raw
  createPdfFiles.value = file.raw ? [file] : []
}

function selectCreateExcel(file: UploadFile) {
  createExcel.value = file.raw
  createExcelFiles.value = file.raw ? [file] : []
  createExcelSource.value = undefined
}

function openReplaceSource(item: ReportTask) {
  replaceReport.value = item
  replaceType.value = 'EXCEL'
  replaceFile.value = undefined
  replaceFiles.value = []
  replaceVisible.value = true
}

function selectReplaceFile(file: UploadFile) {
  replaceFile.value = file.raw
  replaceFiles.value = file.raw ? [file] : []
}

async function submitReplaceSource() {
  if (!replaceReport.value || !replaceFile.value) return ElMessage.warning('请选择新的数据源文件')
  actionId.value = replaceReport.value.id
  try {
    const uploaded = replaceType.value === 'EXCEL'
      ? await uploadExcel(replaceFile.value) : await uploadPdf(replaceFile.value)
    if (replaceType.value === 'EXCEL') await extractExcel(uploaded.id)
    else await extractPdf(uploaded.id)
    await replaceReportSource(replaceReport.value.id, uploaded.id, replaceType.value)
    ElMessage.success(`${replaceType.value === 'EXCEL' ? 'Excel' : 'PDF'} 数据源已替换，报告已重新生成`)
    replaceVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    actionId.value = ''
  }
}

async function submitCreateReport() {
  const hasLims = Boolean(createImport.value && createInstances.value.length && createRecognition.value)
  const hasPdf = Boolean(createPdf.value)
  const hasExcel = Boolean(createExcel.value)
  if (!hasLims && !hasPdf && !hasExcel) return ElMessage.warning('请选择 LIMS、PDF 或 Excel，至少提供一种数据源')
  if (createInstances.value.length && !createRecognition.value) return ElMessage.warning('已选择 LIMS 实验记录，请先完成识别或取消选择')
  const unresolved = (createRecognition.value?.conflicts || []).filter((item) => !createConflictResolutions[item.id])
  if (unresolved.length) return ElMessage.warning(`还有 ${unresolved.length} 个同名数据冲突需要选择`)
  createBusy.value = true
  actionId.value = 'new'
  createVisible.value = false
  startGenerationProgress()
  let created: ReportTask | undefined
  try {
    let sourceId: string | undefined
    if (createPdf.value) {
      const source = await uploadPdf(createPdf.value)
      await extractPdf(source.id)
      sourceId = source.id
    }
    let excelSourceId: string | undefined
    if (createExcel.value) {
      const source = await uploadExcel(createExcel.value)
      createExcelSource.value = await extractExcel(source.id)
      excelSourceId = source.id
    }
    created = await createReport(sourceId, excelSourceId)
    if (hasLims && createImport.value) {
      created = await applyLimsToReport(
        created.id, createImport.value.id, createInstances.value.map((item) => item.instanceId),
        { ...createConflictResolutions },
      )
    }
    stopGenerationTimer(); generationProgress.stage = 4; generationProgress.percentage = 100
    generationProgress.status = 'success'; generationProgress.message = '报告已准备完成，正在进入工作台'
    const sources = [hasLims && 'LIMS', hasPdf && 'PDF', hasExcel && 'Excel'].filter(Boolean).join('、')
    ElMessage.success(`报告已按 ${sources} 数据源创建`)
    await new Promise((resolve) => setTimeout(resolve, 650))
    generationProgress.visible = false
    emit('open', created.id)
  } catch (error) {
    stopGenerationTimer(); generationProgress.status = 'error'; generationProgress.message = errorText(error)
    if (created) await deleteReport(created.id).catch(() => undefined)
    ElMessage.error(errorText(error))
    await new Promise((resolve) => setTimeout(resolve, 1200))
    generationProgress.visible = false
  } finally {
    createBusy.value = false
    actionId.value = ''
  }
}

async function regenerate(item: ReportTask) {
  actionId.value = item.id
  try {
    await rebuildReport(item.id)
    ElMessage.success('报告已按当前模板重新生成')
    await load()
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    actionId.value = ''
  }
}

async function downloadWord(item: ReportTask) {
  actionId.value = item.id
  try {
    await generateReport(item.id)
    const history = await listReportGenerations()
    generations.value = history.items
    const exported = history.items.find((value) => value.report_id === item.id && value.status === 'SUCCESS')
    if (exported) window.open(reportGenerationFileUrl(exported.id), '_blank')
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    actionId.value = ''
  }
}

function downloadPdf(item: ReportTask) {
  window.open(reportPdfUrl(item.id), '_blank')
}

async function showAudit(item: ReportTask) {
  auditReport.value = item
  auditVisible.value = true
  try {
    auditEvents.value = await getHistory(item.id)
  } catch (error) {
    ElMessage.error(errorText(error))
  }
}

async function remove(item: ReportTask) {
  try {
    await ElMessageBox.confirm(`删除报告“${item.title}”及其生成文件？此操作不可恢复。`, '删除报告', {
      type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消',
    })
    await deleteReport(item.id)
    ElMessage.success('报告已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorText(error))
  }
}

async function batchDownload() {
  actionId.value = 'batch'
  try {
    const blob = await batchExportReports(selected.value.map((item) => item.id))
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `报告批量导出-${new Date().toISOString().slice(0, 10)}.zip`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    actionId.value = ''
  }
}

async function batchRemove() {
  try {
    await ElMessageBox.confirm(`删除选中的 ${selected.value.length} 份报告及其生成文件？`, '批量删除', {
      type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消',
    })
    await Promise.all(selected.value.map((item) => deleteReport(item.id)))
    selected.value = []
    ElMessage.success('所选报告已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorText(error))
  }
}

onMounted(load)
</script>

<template>
  <div class="report-hub-shell" :class="{ 'sidebar-expanded': sidebarExpanded }">
    <aside class="hub-sidebar" @mouseenter="sidebarHovered = true" @mouseleave="sidebarHovered = false">
      <div class="hub-sidebar-compact">
        <div class="hub-compact-brand"><Document /></div>
        <nav><button class="active" title="报告管理大厅"><Files /></button><button disabled title="报告编辑工作台"><EditPen /></button></nav>
        <button class="hub-collapse-button" type="button" title="固定展开菜单" aria-label="固定展开菜单" @click.stop="sidebarPinned = true"><Expand /></button>
        <span class="hub-compact-avatar">{{ props.sessionUser.displayName.slice(0, 1) }}</span>
      </div>
      <div class="hub-sidebar-wide">
        <div class="hub-brand"><span><Document /></span><div><strong>智检报告系统</strong><small>REPORT OPERATIONS</small></div></div>
        <nav>
          <button class="active"><Files /><span><strong>报告管理大厅</strong><small>检索、监控与导出</small></span></button>
          <button disabled><EditPen /><span><strong>报告编辑工作台</strong><small>选择报告后进入</small></span></button>
        </nav>
        <button class="hub-collapse-button wide" type="button" :title="sidebarPinned ? '取消固定并收起' : '收起菜单'" aria-label="收起菜单" @click.stop="sidebarPinned = false; sidebarHovered = false"><Fold /><span>收起菜单</span></button>
        <div class="hub-user"><span>{{ props.sessionUser.displayName.slice(0, 1) }}</span><div><strong>{{ props.sessionUser.displayName }}</strong><small>{{ props.sessionUser.username }}</small></div><el-button text :icon="SwitchButton" title="退出" @click="$emit('logout')" /></div>
      </div>
    </aside>
    <main class="hub-main">
      <header class="hub-header"><div><p>REPORT MANAGEMENT</p><h1>报告管理大厅</h1><span>统一管理报告任务、数据源与合规记录</span></div><el-button class="hub-create-button" type="primary" size="large" :icon="Plus" :loading="actionId === 'new'" @click="createNew">发起新报告生成</el-button></header>
      <ReportGenerationProgress v-bind="generationProgress" />
      <section class="hub-stats">
        <article><span>全部报告</span><b>{{ stats.total }}</b></article>
        <article><span>待复核</span><b>{{ stats.review }}</b></article>
        <article><span>已完成导出</span><b>{{ stats.completed }}</b></article>
        <article :class="{ alert: stats.failed }"><span>生成失败</span><b>{{ stats.failed }}</b></article>
      </section>
      <section class="hub-content">
        <div class="hub-filters">
          <el-input v-model="filters.query" :prefix-icon="Search" clearable placeholder="报告名称、样品编号或实验名称" />
          <el-select v-model="filters.status" clearable placeholder="全部状态">
            <el-option v-for="(meta, code) in statusMeta" :key="code" :label="meta.label" :value="code" />
          </el-select>
          <el-date-picker v-model="filters.dates" type="datetimerange" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" />
          <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
        </div>
        <div v-if="selected.length" class="hub-batch"><strong>已选择 {{ selected.length }} 份报告</strong><el-button type="primary" plain :icon="Download" :loading="actionId === 'batch'" @click="batchDownload">批量导出 Word</el-button><el-button type="danger" plain :icon="Delete" @click="batchRemove">批量删除</el-button></div>
        <el-table v-loading="loading" :data="filtered" row-key="id" height="calc(100vh - 330px)" @selection-change="selected = $event" @row-dblclick="emit('open', $event.id)">
          <el-table-column type="selection" width="44" />
          <el-table-column prop="title" label="报告名称" min-width="220"><template #default="{ row }"><button class="hub-report-link" @click="emit('open', row.id)">{{ row.title }}</button><small>{{ row.resolved_data.report_no || '暂无报告编号' }}</small></template></el-table-column>
          <el-table-column label="项目号" min-width="150"><template #default="{ row }">{{ projectNumber(row) }}</template></el-table-column>
          <el-table-column label="生成 / 更新时间" width="180"><template #default="{ row }">{{ new Date(generatedAt(row)).toLocaleString('zh-CN') }}</template></el-table-column>
          <el-table-column label="实验记录名称" min-width="240" show-overflow-tooltip><template #default="{ row }">{{ experimentRecordNames(row) }}</template></el-table-column>
          <el-table-column label="创建人" width="110"><template #default>{{ props.sessionUser.displayName }}</template></el-table-column>
          <el-table-column label="操作" width="210" fixed="right" align="center" header-align="center" label-class-name="hub-operation-header"><template #default="{ row }"><div class="hub-actions">
            <el-button link type="primary" :icon="EditPen" @click="emit('open', row.id)">编辑/复核</el-button>
            <el-dropdown trigger="click"><el-button link :loading="actionId === row.id">更多操作</el-button><template #dropdown><el-dropdown-menu>
              <el-dropdown-item :icon="Refresh" @click="regenerate(row)">重新生成</el-dropdown-item>
              <el-dropdown-item :icon="UploadFilled" @click="openReplaceSource(row)">更换数据源</el-dropdown-item>
              <el-dropdown-item :icon="Download" @click="downloadWord(row)">导出 Word</el-dropdown-item>
              <el-dropdown-item :icon="View" @click="downloadPdf(row)">导出 PDF</el-dropdown-item>
              <el-dropdown-item :icon="Clock" @click="showAudit(row)">查看 Audit Trail</el-dropdown-item>
              <el-dropdown-item divided :icon="Delete" @click="remove(row)">删除</el-dropdown-item>
            </el-dropdown-menu></template></el-dropdown>
          </div></template></el-table-column>
        </el-table>
        <div class="hub-table-footer">显示 {{ filtered.length }} / {{ reports.length }} 份报告</div>
      </section>
    </main>
    <el-dialog v-model="createVisible" title="发起新报告生成" width="980px" class="create-report-dialog" :close-on-click-modal="false">
      <el-steps :active="createRecognition ? 2 : createImport ? 1 : 0" finish-status="success" align-center>
        <el-step title="查询项目" />
        <el-step title="选择并识别记录" />
        <el-step title="上传数据文件" />
      </el-steps>
      <section class="create-report-section">
        <header><span>1</span><div><strong>选择 LIMS 实验记录（可选）</strong><small>输入项目编号，查询并勾选本次报告需要引用的实验记录</small></div></header>
        <div class="create-project-query">
          <el-input v-model="createProjectId" clearable placeholder="请输入项目编号，如 XM2024108" @keyup.enter="queryCreateProject" />
          <el-button type="primary" :icon="Search" :loading="createBusy" @click="queryCreateProject">查询 LIMS</el-button>
        </div>
        <el-table v-if="createImport" v-loading="createRecognizing" :data="createImport.summary.instances" max-height="280" stripe @selection-change="selectCreateInstances">
          <el-table-column type="selection" width="48" />
          <el-table-column prop="instanceId" label="实例编号" width="135" />
          <el-table-column prop="title" label="实验名称" min-width="300" show-overflow-tooltip />
          <el-table-column prop="version" label="版本" width="70" />
          <el-table-column prop="createdBy" label="编制人" width="100" />
          <el-table-column label="结构化数据" width="105"><template #default="{ row }">{{ Object.values(row.structuredDataCounts || {}).reduce((sum: number, value: unknown) => sum + Number(value || 0), 0) }}</template></el-table-column>
        </el-table>
        <div v-if="createImport" class="create-recognize-action">
          <span>已选择 {{ createInstances.length }} 条记录</span>
          <span v-if="createRecognizing">正在自动识别...</span>
          <span v-else-if="createInstances.length && !createRecognition" class="recognition-error">自动识别未完成，请重新勾选</span>
          <span v-else-if="!createInstances.length">勾选后自动识别</span>
        </div>
        <div v-if="createRecognition" class="create-recognition-summary">
          <span><b>{{ createRecognition.recognizedTotal }}</b> 条数据已识别</span>
          <span><b>{{ createRecognition.duplicateCount }}</b> 条完全重复已合并</span>
          <span><b>{{ createRecognition.conflicts.length }}</b> 个同名冲突</span>
        </div>
        <div v-if="createRecognition?.conflicts.length" class="create-conflicts">
          <article v-for="conflict in createRecognition.conflicts" :key="conflict.id">
            <strong>{{ conflict.label }} · {{ conflict.identity }}</strong>
            <p class="conflict-difference">
              差异字段：{{ differingConflictFields(conflict.options).map((key) => conflictFieldLabels[key] || key).join('、') }}
            </p>
            <el-radio-group v-model="createConflictResolutions[conflict.id]">
              <el-radio v-for="option in conflict.options" :key="option.candidateId" :value="option.candidateId" border>
                <span>{{ option.evidence.instanceTitle || option.evidence.instanceId }}</span>
                <b v-for="key in differingConflictFields(conflict.options)" :key="key">
                  {{ conflictFieldLabels[key] || key }}：{{ conflictValue((option.value as Record<string, unknown>)[key]) }}
                </b>
              </el-radio>
            </el-radio-group>
          </article>
        </div>
      </section>
      <section class="create-report-section">
        <header><span>3</span><div><strong>上传 Excel 验证计算表（可选）</strong><small>支持 XLSX/XLSM；读取已保存的公式缓存，不执行宏</small></div></header>
        <el-upload v-model:file-list="createExcelFiles" drag accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12" :auto-upload="false" :limit="1" :on-change="selectCreateExcel" :on-remove="() => { createExcel = undefined; createExcelSource = undefined }">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖放验证计算表到这里，或<em>点击选择文件</em></div>
          <template #tip><div class="el-upload__tip">仅解析验证结果计算页；原始工作簿会保留用于追溯</div></template>
        </el-upload>
        <div v-if="createExcelSource" class="create-recognition-summary">
          <span><b>{{ createExcelSource.summary.impurityCount || 0 }}</b> 个杂质</span>
          <span>{{ (createExcelSource.summary.impurityNames || []).join('、') }}</span>
          <span v-if="createExcelSource.warnings.length"><b>{{ createExcelSource.warnings.length }}</b> 条缓存警告</span>
        </div>
      </section>
      <section class="create-report-section">
        <header><span>2</span><div><strong>上传 PDF 谱图（可选）</strong><small>支持单个 PDF 文件；LIMS 与 PDF 至少提供一种数据源</small></div></header>
        <el-upload v-model:file-list="createPdfFiles" drag accept=".pdf,application/pdf" :auto-upload="false" :limit="1" :on-change="selectCreatePdf" :on-remove="() => { createPdf = undefined }">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖放 PDF 谱图到这里，或<em>点击选择文件</em></div>
          <template #tip><div class="el-upload__tip">仅支持 PDF；报告创建后可在数据源中查看和追溯</div></template>
        </el-upload>
      </section>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button class="hub-create-confirm" type="primary" :loading="createBusy" :disabled="createRecognizing || (!createRecognition && !createPdf && !createExcel)" @click="submitCreateReport">创建并进入工作台</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="replaceVisible" title="更换数据源" width="620px" :close-on-click-modal="false">
      <el-segmented v-model="replaceType" :options="[{ label: 'Excel 验证计算表', value: 'EXCEL' }, { label: 'PDF 谱图', value: 'PDF' }]" @change="replaceFile = undefined; replaceFiles = []" />
      <el-upload v-model:file-list="replaceFiles" drag :accept="replaceType === 'EXCEL' ? '.xlsx,.xlsm' : '.pdf,application/pdf'" :auto-upload="false" :limit="1" :on-change="selectReplaceFile" :on-remove="() => { replaceFile = undefined }">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖放新文件到这里，或<em>点击选择文件</em></div>
        <template #tip><div class="el-upload__tip">只替换所选类型的数据，报告中的其他来源和字段保持不变</div></template>
      </el-upload>
      <template #footer><el-button @click="replaceVisible = false">取消</el-button><el-button type="primary" :loading="Boolean(replaceReport && actionId === replaceReport.id)" :disabled="!replaceFile" @click="submitReplaceSource">替换并重新生成</el-button></template>
    </el-dialog>
    <el-drawer v-model="auditVisible" title="Audit Trail" size="520px">
      <div v-if="auditReport" class="audit-heading"><strong>{{ auditReport.title }}</strong><span>{{ auditReport.resolved_data.report_no || '暂无报告编号' }}</span></div>
      <section v-if="auditReport" class="audit-generations"><h3>生成与导出记录</h3><article v-for="item in generations.filter((value) => value.report_id === auditReport?.id)" :key="item.id"><el-tag size="small" :type="item.status === 'SUCCESS' ? 'success' : item.status === 'FAILED' ? 'danger' : 'warning'">{{ item.status }}</el-tag><span>{{ new Date(item.generated_at).toLocaleString('zh-CN') }}</span><small v-if="item.error_message">{{ item.error_message }}</small></article><p v-if="!generations.some((value) => value.report_id === auditReport?.id)">暂无生成记录</p></section>
      <h3 class="audit-change-title">字段修改记录</h3>
      <el-timeline v-if="auditEvents.length"><el-timeline-item v-for="item in auditEvents" :key="item.id" :timestamp="new Date(item.created_at).toLocaleString('zh-CN')"><strong>{{ item.operator }} · {{ item.reason }}</strong><p>{{ item.field_code }}：{{ item.old_value || '空' }} → {{ item.new_value || '空' }}</p></el-timeline-item></el-timeline>
      <el-empty v-else description="暂无字段修改记录" />
    </el-drawer>
  </div>
</template>
