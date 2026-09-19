<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  Search, UploadFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import {
  applyLimsToReport, batchExportReports, createReport, deleteReport, extractExcel, extractPdf, generateReport, getHistory,
  listReportGenerations, listReports, rebuildReport, replaceReportSource, reportGenerationFileUrl, reportPdfUrl, uploadExcel, uploadPdf, uploadProtocol,
  type ChangeEvent, type ReportGeneration, type ReportTask, type SourceDocument,
} from './api'
import {
  queryLimsProject, recognizeLimsInstances,
  type LimsImport, type LimsInstanceSummary, type LimsRecognition,
} from './lims-api'
import type { AuthUser } from './auth-api'
import ReportGenerationProgress from './ReportGenerationProgress.vue'
import ReportTemplatePicker from './ReportTemplatePicker.vue'
import ProtocolUpload from './ProtocolUpload.vue'
import LimsConflictResolver from './LimsConflictResolver.vue'
import ReportHubHeader from './report-hub/ReportHubHeader.vue'
import ReportStatusTabs from './report-hub/ReportStatusTabs.vue'
import ReportQueue from './report-hub/ReportQueue.vue'
import {
  reportLifecycle, type ReportHubRow, type ReportHubTab, type ReportLifecycle,
} from './report-hub'

const props = defineProps<{ sessionUser: AuthUser }>()
const emit = defineEmits<{ open: [id: string] }>()
const can = (permission: string) => props.sessionUser.permissions.includes(permission)
const mineReports = ref<ReportTask[]>([])
const allReports = ref<ReportTask[]>([])
const activeTab = ref<ReportHubTab>('MINE')
const reports = computed(() => activeTab.value === 'ALL' ? allReports.value : mineReports.value)
const generations = ref<ReportGeneration[]>([])
const loading = ref(false)
const loadError = ref('')
const actionId = ref('')
const auditVisible = ref(false)
const auditReport = ref<ReportTask>()
const auditEvents = ref<ChangeEvent[]>([])
const createTemplateId = ref('')
const createVisible = ref(false)
const createBusy = ref(false)
const createRecognizing = ref(false)
const createProjectId = ref('')
const createImport = ref<LimsImport>()
const createInstances = ref<LimsInstanceSummary[]>([])
const createRecognition = ref<LimsRecognition>()
const createProtocol = ref<File>()
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
const filters = reactive<{ query: string; dates: [Date, Date] | [] }>({
  query: '', dates: [],
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

function lifecycle(item: ReportTask): ReportLifecycle {
  return reportLifecycle(item.status)
}

function isLifecycleTab(tab: ReportHubTab): tab is ReportLifecycle {
  return tab !== 'MINE' && tab !== 'ALL'
}

const filtered = computed(() => reports.value.filter((item) => {
  const data = item.resolved_data
  const samples = ((data.source_payloads?.LIMS?.samples || []) as Array<Record<string, unknown>>)
  const searchable = [item.title, item.report_number, data.report_no, data.sample, data.project_name,
    ...samples.flatMap((sample) => [sample.sampleName, sample.batchNo])].join(' ').toLowerCase()
  const queryMatches = !filters.query.trim() || searchable.includes(filters.query.trim().toLowerCase())
  const statusMatches = !isLifecycleTab(activeTab.value) || lifecycle(item) === activeTab.value
  const changed = new Date(item.updated_at).getTime()
  const dateMatches = !filters.dates.length || (changed >= filters.dates[0].getTime() && changed <= filters.dates[1].getTime())
  return queryMatches && statusMatches && dateMatches
}))

const stats = computed(() => ({
  mine: mineReports.value.length,
  draft: mineReports.value.filter((item) => lifecycle(item) === 'DRAFT').length,
  review: mineReports.value.filter((item) => lifecycle(item) === 'REVIEW').length,
  reviewed: mineReports.value.filter((item) => lifecycle(item) === 'REVIEWED').length,
  completed: mineReports.value.filter((item) => lifecycle(item) === 'COMPLETED').length,
  all: allReports.value.length,
}))

function projectNumber(item: ReportTask) {
  const lims = item.resolved_data.source_payloads?.LIMS
  const project = lims?.project as Record<string, unknown> | undefined
  return String(project?.id || '-').trim() || '-'
}

function experimentRecordNames(item: ReportTask) {
  const lims = item.resolved_data.source_payloads?.LIMS
  const instances = (lims?.instances || []) as Array<Record<string, unknown>>
  const names = instances.map((instance) => String(instance.title || '').trim()).filter(Boolean)
  return [...new Set(names)].join('；') || '-'
}

const reportRows = computed<ReportHubRow[]>(() => filtered.value.map((item) => ({
  report: item,
  id: item.id,
  title: item.title,
  reportNumber: item.report_number,
  projectNumber: projectNumber(item),
  updatedAt: new Date(item.updated_at).toLocaleString('zh-CN', { hour12: false }),
  experimentNames: experimentRecordNames(item),
  creator: item.creator_name || '未知用户',
  lifecycle: lifecycle(item),
  isOwned: item.created_by === props.sessionUser.id,
})))

function clearFilters() {
  filters.query = ''
  filters.dates = []
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [items, globalItems, history] = await Promise.all([
      listReports('mine'),
      can('REPORT_ALL_VIEW') ? listReports('all') : Promise.resolve([]),
      can('REPORT_EDIT') ? listReportGenerations() : Promise.resolve({ items: [] }),
    ])
    ;[...items, ...globalItems].forEach((item) => reportLifecycle(item.status))
    mineReports.value = items
    allReports.value = globalItems
    generations.value = history.items
  } catch (error) {
    loadError.value = `报告列表加载失败：${errorText(error)}`
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } }; message?: string }
  return value.response?.data?.detail || value.message || '操作失败'
}

function createNew() {
  createTemplateId.value = ''
  createProtocol.value = undefined
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
  let force = false
  if (replaceReport.value.word_edit_locked) {
    try {
      await ElMessageBox.confirm(
        '当前 Word 已有人工编辑内容。继续将按新数据源重新生成 Word，现有人工修改会被覆盖。',
        '确认覆盖人工编辑',
        { confirmButtonText: '继续替换', cancelButtonText: '取消', type: 'warning' },
      )
      force = true
    } catch {
      return
    }
  }
  actionId.value = replaceReport.value.id
  try {
    const uploaded = replaceType.value === 'EXCEL'
      ? await uploadExcel(replaceFile.value) : await uploadPdf(replaceFile.value)
    if (replaceType.value === 'EXCEL') await extractExcel(uploaded.id)
    else await extractPdf(uploaded.id)
    await replaceReportSource(replaceReport.value.id, uploaded.id, replaceType.value, force)
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
  if (!createTemplateId.value) return ElMessage.warning('请选择报告模板')
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
    const protocolSource = createProtocol.value ? await uploadProtocol(createProtocol.value) : undefined
    created = await createReport(sourceId, excelSourceId, createTemplateId.value, protocolSource?.id)
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

watch(activeTab, () => { selected.value = [] })
onMounted(load)
</script>

<template>
  <main class="hub-main">
    <ReportHubHeader :can-create="can('REPORT_CREATE')" :creating="actionId === 'new'" @create="createNew" />
    <ReportGenerationProgress v-bind="generationProgress" />
    <ReportStatusTabs
      :stats="stats"
      :active="activeTab"
      :can-view-all="can('REPORT_ALL_VIEW')"
      @select="activeTab = $event"
    />
    <ReportQueue
      :rows="reportRows"
      :total="reports.length"
      :loading="loading"
      :load-error="loadError"
      :query="filters.query"
      :dates="filters.dates"
      :action-id="actionId"
      :can-create="can('REPORT_CREATE')"
      :can-edit="can('REPORT_EDIT')"
      :can-generate="can('REPORT_GENERATE')"
      :can-download="can('REPORT_DOWNLOAD')"
      @update:query="filters.query = $event"
      @update:dates="filters.dates = $event"
      @reload="load"
      @clear="clearFilters"
      @create="createNew"
      @select="selected = $event"
      @open="emit('open', $event.id)"
      @regenerate="regenerate"
      @replace="openReplaceSource"
      @download-word="downloadWord"
      @download-pdf="downloadPdf"
      @audit="showAudit"
      @remove="remove"
      @batch-download="batchDownload"
      @batch-remove="batchRemove"
    />

    <el-dialog v-model="createVisible" title="发起新报告生成" width="1040px" top="5vh" class="create-report-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="create-dialog-heading">
          <h2>发起新报告生成</h2>
        </div>
      </template>
      <div class="create-template-area">
        <ReportTemplatePicker v-if="createVisible" v-model="createTemplateId" />
      </div>
      <section class="create-report-section">
        <header><div><strong>选择 LIMS 实验记录（可选）</strong></div></header>
        <div class="create-project-query">
          <el-input v-model="createProjectId" aria-label="LIMS 项目编号" clearable placeholder="请输入项目编号" @keyup.enter="queryCreateProject" />
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
        </div>
        <div v-if="createRecognition" class="create-recognition-summary">
          <span><b>{{ createRecognition.recognizedTotal }}</b> 条数据已识别</span>
          <span><b>{{ createRecognition.duplicateCount }}</b> 条完全重复已合并</span>
          <span><b>{{ createRecognition.conflicts.length }}</b> 个同名冲突</span>
        </div>
        <LimsConflictResolver
          v-if="createRecognition?.conflicts.length"
          :conflicts="createRecognition.conflicts"
          :resolutions="createConflictResolutions"
          @resolve="(conflictId, candidateId) => { createConflictResolutions[conflictId] = candidateId }"
        />
      </section>
      <div class="create-attachments">
        <ProtocolUpload v-if="createVisible" v-model="createProtocol" />
        <section class="create-report-section">
          <header><div><strong>上传 Excel 验证计算表（可选）</strong></div></header>
          <el-upload v-model:file-list="createExcelFiles" drag accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12" :auto-upload="false" :limit="1" :on-change="selectCreateExcel" :on-remove="() => { createExcel = undefined; createExcelSource = undefined }">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text"><em>选择 Excel 文件</em></div>
          </el-upload>
          <div v-if="createExcelSource" class="create-recognition-summary">
            <span><b>{{ createExcelSource.summary.impurityCount || 0 }}</b> 个杂质</span>
            <span>{{ (createExcelSource.summary.impurityNames || []).join('、') }}</span>
            <span v-if="createExcelSource.warnings.length"><b>{{ createExcelSource.warnings.length }}</b> 条缓存警告</span>
        </div>
      </section>
      <section class="create-report-section">
        <header><div><strong>上传 PDF 谱图（可选）</strong></div></header>
        <el-upload v-model:file-list="createPdfFiles" drag accept=".pdf,application/pdf" :auto-upload="false" :limit="1" :on-change="selectCreatePdf" :on-remove="() => { createPdf = undefined }">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text"><em>选择 PDF 文件</em></div>
        </el-upload>
      </section>
      </div>
      <template #footer>
        <div class="create-dialog-footer">
          <div class="create-footer-actions">
            <el-button @click="createVisible = false">取消</el-button>
            <el-button class="hub-create-confirm" type="primary" :loading="createBusy" :disabled="!createTemplateId || createRecognizing || (!createRecognition && !createPdf && !createExcel)" @click="submitCreateReport">创建并进入工作台</el-button>
          </div>
        </div>
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
  </main>
</template>

<style src="./styles/create-report-dialog.css"></style>
<style src="./styles/report-hub.css"></style>
