<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  Clock, Coin, DataAnalysis, Delete, Document, Download, EditPen, Files, MoreFilled,
  Plus, Refresh, Search, SwitchButton, Upload, View,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadRequestOptions } from 'element-plus'
import {
  applyLimsToReport, createReport, createVersion, extractPdf, generateReport, getBindings, getHistory, getOnlyOfficeConfig, getVersions,
  getReport, listReportGenerations, listReports, reportGenerationFileUrl, updateReport, uploadPdf,
  rebuildReport,
  type ChangeEvent, type ExtractedField, type FieldBinding, type ReportGeneration, type ReportTask, type ReportVersion,
  type SourceDocument, type SourceRef, type SourceType, type TestItem,
} from './api'
import {
  getLimsCapabilities, recognizeLimsInstances, uploadLimsExcel,
  type LimsCapabilities, type LimsEvidence, type LimsImport, type LimsInstanceSummary, type LimsRecognition,
} from './lims-api'
import type { AuthUser } from './auth-api'

defineProps<{ sessionUser: AuthUser }>()
defineEmits<{ logout: [] }>()

declare global {
  interface Window {
    DocsAPI?: { DocEditor: new (elementId: string, config: Record<string, unknown>) => { destroyEditor?: () => void } }
  }
}

const report = ref<ReportTask>()
const reportTasks = ref<ReportTask[]>([])
const generationHistory = ref<ReportGeneration[]>([])
const generationSearch = ref('')
const generationLoading = ref(false)
const sidebarTab = ref<'reports' | 'exports'>('reports')
const bindings = ref<FieldBinding[]>([])
const history = ref<ChangeEvent[]>([])
const versions = ref<ReportVersion[]>([])
const uploadedSource = ref<SourceDocument>()
const selectedCode = ref('report_no')
const activeSource = ref<'all' | 'LIMS' | 'PDF'>('all')
const detailTab = ref('source')
const showSources = ref(true)
const previewVisible = ref(false)
const versionsVisible = ref(false)
const uploadPercent = ref(0)
const sourceSearch = ref('')
const editorMode = ref<'word' | 'fields'>('word')
const onlyOfficeLoading = ref(false)
const onlyOfficeError = ref('')
let onlyOfficeEditor: { destroyEditor?: () => void } | undefined
const savedAt = ref('')
const busy = reactive({ init: true, save: false, export: false, upload: false })
const limsCapabilities = ref<LimsCapabilities>({ sqlEnabled: false, sqlConfigured: false, excelImportEnabled: true })
const limsImport = ref<LimsImport>()
const limsDialogVisible = ref(false)
const limsLoading = ref(false)
const selectedLimsInstances = ref<LimsInstanceSummary[]>([])
const limsRecognition = ref<LimsRecognition>()
const conflictResolutions = reactive<Record<string, string>>({})
const selectedLimsDetail = ref<{ label: string; value: string; evidence: LimsEvidence }>()

interface LimsTreeNode {
  id: string
  label: string
  value?: string
  evidence?: LimsEvidence
  children?: LimsTreeNode[]
}

const limsCollectionLabels: Record<string, string> = {
  samples: '供试品', referenceStandards: '对照品', instruments: '仪器', columns: '色谱柱',
  reagents: '试剂', weighings: '称量记录', impurity: '杂质与限度', limit: '限度计算',
  validationSummary: '验证标准与结论', solutions: '溶液配制', methodParameters: '方法参数',
  systemSuitability: '系统适用性', specificity: '专属性', lod: '检测限', loq: '定量限',
  linearityPreparation: '线性溶液', linearity: '线性与范围', repeatability: '重复性',
  intermediatePrecision: '中间精密度', blankAmount: '空白量', accuracy: '准确度',
  solutionStability: '溶液稳定性', robustnessSpecificity: '耐用性专属性',
  robustnessSequence: '耐用性进样', robustnessResult: '耐用性结果', sampleResults: '样品结果',
  formulas: '计算公式', conclusions: '实验结论', unmatched: '未识别数据',
}

const sourceLabels: Record<SourceType, string> = {
  LIMS: 'LIMS', PDF: 'PDF', MANUAL: '人工', MANUAL_WORD: 'Word 人工编辑', CALCULATED: '计算',
}

const statusLabel = computed(() => ({
  DATA_REVIEW: '编辑中', READY_TO_GENERATE: '已保存', GENERATED: '已导出',
}[report.value?.status || ''] || report.value?.status || ''))

function readField(code: string): string {
  const data = report.value?.resolved_data
  if (!data) return ''
  const match = code.match(/^testItems\[id=(.+)]\.(.+)$/)
  if (match) {
    const item = data.test_items.find((row) => row.id === match[1])
    return item ? String(item[match[2] as keyof TestItem] ?? '') : ''
  }
  return String(data[code as keyof typeof data] ?? '')
}

function sourceFor(code: string): SourceRef {
  return report.value?.resolved_data.field_sources[code] || { type: 'MANUAL', record_id: 'MANUAL' }
}

function originalFor(code: string) {
  return report.value?.resolved_data.original_values[code] ?? readField(code)
}

const displayBindings = computed(() => bindings.value.map((item) => ({
  ...item,
  current_value: readField(item.field_code),
  original_value: originalFor(item.field_code),
  source: sourceFor(item.field_code),
  modified: readField(item.field_code) !== originalFor(item.field_code),
})))

const selectedBinding = computed<FieldBinding>(() => {
  if (selectedLimsDetail.value) {
    const evidence = selectedLimsDetail.value.evidence
    return {
      field_code: `LIMS.${evidence.instanceId || 'source'}`,
      label: selectedLimsDetail.value.label,
      current_value: selectedLimsDetail.value.value,
      original_value: selectedLimsDetail.value.value,
      source: {
        type: 'LIMS', record_id: evidence.unitId || evidence.richTextId || evidence.instanceId,
        instance_title: evidence.instanceTitle, section_path: evidence.sectionPath,
        excel_row: evidence.excelRow, table_index: evidence.tableIndex, headers: evidence.headers,
      },
      modified: false,
    }
  }
  return displayBindings.value.find((item) => item.field_code === selectedCode.value) || {
    field_code: selectedCode.value,
    label: selectedCode.value,
    current_value: readField(selectedCode.value),
    original_value: originalFor(selectedCode.value),
    source: sourceFor(selectedCode.value),
    modified: readField(selectedCode.value) !== originalFor(selectedCode.value),
  }
})

const filteredBindings = computed(() => {
  const query = sourceSearch.value.trim().toLowerCase()
  return displayBindings.value.filter((item) => {
    const sourceMatches = activeSource.value === 'all' || item.source.type === activeSource.value
    const textMatches = !query || `${item.label} ${item.current_value} ${item.field_code}`.toLowerCase().includes(query)
    return sourceMatches && textMatches
  })
})

const sourceCounts = computed(() => ({
  LIMS: displayBindings.value.filter((item) => item.source.type === 'LIMS').length,
  PDF: displayBindings.value.filter((item) => item.source.type === 'PDF').length,
}))

const filteredGenerationHistory = computed(() => {
  const query = generationSearch.value.trim().toLowerCase()
  if (!query) return generationHistory.value
  return generationHistory.value.filter((item) => {
    const reportNo = item.resolved_data?.report_no || ''
    return `${item.title} ${reportNo}`.toLowerCase().includes(query)
  })
})

const filteredReportTasks = computed(() => {
  const query = generationSearch.value.trim().toLowerCase()
  if (!query) return reportTasks.value
  return reportTasks.value.filter((item) =>
    `${item.title} ${item.resolved_data.report_no || ''}`.toLowerCase().includes(query),
  )
})

function formatGenerationTime(value: string) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function generationStatusLabel(status: string) {
  return ({ SUCCESS: '已生成', FAILED: '生成失败', PROCESSING: '生成中' } as Record<string, string>)[status] || status
}

function displayLimsValue(item: Record<string, unknown>) {
  const preferred = ['sampleName', 'name', 'instrumentName', 'impurityName', 'field1', 'solutionName', 'sequence', 'text']
  const title = preferred.map((key) => item[key]).find((value) => value !== undefined && value !== '')
  const details = Object.entries(item)
    .filter(([key, value]) => key !== 'evidence' && value !== undefined && value !== '')
    .slice(0, 5)
    .map(([, value]) => String(value))
  return { title: String(title || details[0] || '记录'), details: details.join(' · ') }
}

const limsTreeData = computed<LimsTreeNode[]>(() => {
  const payload = (limsRecognition.value?.payload || report.value?.resolved_data.source_payloads.LIMS || {}) as Record<string, unknown>
  const query = sourceSearch.value.trim().toLowerCase()
  return Object.entries(limsCollectionLabels).flatMap(([key, label]) => {
    const records = payload[key]
    if (!Array.isArray(records) || !records.length) return []
    const children = records.map((record, index) => {
      const item = record as Record<string, unknown>
      const display = displayLimsValue(item)
      return { id: `${key}-${index}`, label: display.title, value: display.details,
        evidence: item.evidence as LimsEvidence | undefined }
    }).filter((node) => !query || `${label} ${node.label} ${node.value}`.toLowerCase().includes(query))
    if (!children.length && query) return []
    return [{ id: key, label: `${label} (${records.length})`, children }]
  })
})

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string | { message?: string } } }; message?: string }
  const detail = value.response?.data?.detail
  return (typeof detail === 'string' ? detail : detail?.message) || value.message || '操作失败'
}

function structuredTotal(counts: Record<string, number>) {
  return Object.values(counts).reduce((total, count) => total + count, 0)
}

function readLimsSql() {
  if (!limsCapabilities.value.sqlEnabled || !limsCapabilities.value.sqlConfigured) {
    ElMessage.warning('尚未配置 LIMS SQL 连接，请联系系统管理员')
    return
  }
  ElMessage.info('SQL 读取适配器尚未接入正式数据库')
}

async function handleLimsExcel(options: UploadRequestOptions) {
  limsLoading.value = true
  try {
    limsImport.value = await uploadLimsExcel(options.file)
    selectedLimsInstances.value = []
    limsRecognition.value = undefined
    Object.keys(conflictResolutions).forEach((key) => delete conflictResolutions[key])
    limsDialogVisible.value = true
    ElMessage.success(`已读取 ${limsImport.value.summary.instanceCount} 个实验实例`)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    limsLoading.value = false
  }
}

function handleLimsSelection(items: LimsInstanceSummary[]) {
  selectedLimsInstances.value = items
  limsRecognition.value = undefined
  Object.keys(conflictResolutions).forEach((key) => delete conflictResolutions[key])
}

async function recognizeSelectedLims() {
  if (!limsImport.value || !selectedLimsInstances.value.length) {
    ElMessage.warning('请至少选择一条实验记录')
    return
  }
  limsLoading.value = true
  try {
    limsRecognition.value = await recognizeLimsInstances(
      limsImport.value.id,
      selectedLimsInstances.value.map((item) => item.instanceId),
    )
    ElMessage.success(`已识别 ${limsRecognition.value.recognizedTotal} 条结构化数据`)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    limsLoading.value = false
  }
}

async function applySelectedLims() {
  if (!report.value || !limsImport.value || !limsRecognition.value) return
  if (report.value.word_edit_locked) {
    ElMessage.warning('Word 已人工编辑并保存，不能再用 LIMS 自动填充；请新建报告。')
    return
  }
  const unresolved = limsRecognition.value.conflicts.filter((item) => !conflictResolutions[item.id])
  if (unresolved.length) {
    ElMessage.warning(`还有 ${unresolved.length} 个冲突需要选择`)
    return
  }
  limsLoading.value = true
  try {
    onlyOfficeEditor?.destroyEditor?.()
    onlyOfficeEditor = undefined
    report.value = await applyLimsToReport(
      report.value.id,
      limsImport.value.id,
      selectedLimsInstances.value.map((item) => item.instanceId),
      { ...conflictResolutions },
    )
    limsDialogVisible.value = false
    await refreshBindings()
    await nextTick()
    await openOnlyOffice()
    ElMessage.success(`已合并 ${selectedLimsInstances.value.length} 条实验记录并填充 Word`)
  } catch (error) {
    ElMessage.error(errorText(error))
    await nextTick()
    await openOnlyOffice()
  } finally {
    limsLoading.value = false
  }
}

function selectLimsTreeNode(node: LimsTreeNode) {
  if (!node.evidence) return
  selectedLimsDetail.value = { label: node.label, value: node.value || '', evidence: node.evidence }
  detailTab.value = 'source'
}

async function refreshBindings() {
  if (!report.value) return
  bindings.value = await getBindings(report.value.id)
}

async function selectField(code: string) {
  selectedLimsDetail.value = undefined
  selectedCode.value = code
  detailTab.value = 'source'
  if (report.value) history.value = await getHistory(report.value.id, code)
}

function setField(code: string, value: string) {
  if (!report.value) return
  const data = report.value.resolved_data
  const match = code.match(/^testItems\[id=(.+)]\.(.+)$/)
  if (match) {
    const item = data.test_items.find((row) => row.id === match[1])
    if (item) (item as unknown as Record<string, string>)[match[2]] = value
  } else {
    (data as unknown as Record<string, unknown>)[code] = value
  }
}

function editBound(code: string, event: Event) {
  setField(code, (event.target as HTMLElement).innerText.trim())
  selectedCode.value = code
}

function sourceClass(code: string) {
  return showSources.value ? `source-${sourceFor(code).type.toLowerCase()}` : ''
}

function itemCode(item: TestItem, field: keyof TestItem) {
  return `testItems[id=${item.id}].${field}`
}

function categorySpan(index: number) {
  const items = report.value?.resolved_data.test_items || []
  const category = items[index]?.category
  let count = 1
  for (let i = index + 1; i < items.length && items[i].category === category; i += 1) count += 1
  return count
}

function firstInCategory(index: number) {
  const items = report.value?.resolved_data.test_items || []
  return index === 0 || items[index - 1].category !== items[index].category
}

function addTestItem() {
  if (!report.value) return
  const id = `TEST-${Date.now()}`
  const item: TestItem = { id, category: '新增分类', name: '新检测项目', method: '', requirement: '', result: '', unit: '', conclusion: '' }
  report.value.resolved_data.test_items.push(item)
  for (const field of ['category', 'name', 'method', 'requirement', 'result', 'unit', 'conclusion'] as const) {
    const code = itemCode(item, field)
    report.value.resolved_data.field_sources[code] = { type: 'MANUAL', record_id: id }
    report.value.resolved_data.original_values[code] = ''
    bindings.value.push({ field_code: code, label: field, current_value: item[field], original_value: '', source: sourceFor(code), modified: true })
  }
  selectField(itemCode(item, 'name'))
}

function removeTestItem(item: TestItem) {
  if (!report.value || report.value.resolved_data.test_items.length <= 1) return
  report.value.resolved_data.test_items = report.value.resolved_data.test_items.filter((row) => row.id !== item.id)
  bindings.value = bindings.value.filter((binding) => !binding.field_code.includes(`id=${item.id}`))
  selectedCode.value = 'report_no'
}

async function saveReport(makeVersion = true) {
  if (!report.value) return
  busy.save = true
  try {
    report.value = await updateReport(report.value)
    reportTasks.value = reportTasks.value.map((item) => item.id === report.value?.id ? report.value : item)
    if (makeVersion) await createVersion(report.value.id, '保存草稿')
    await refreshBindings()
    history.value = await getHistory(report.value.id, selectedCode.value)
    savedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    ElMessage.success('报告已保存')
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    busy.save = false
  }
}

async function exportWord() {
  if (!report.value) return
  busy.export = true
  try {
    if (editorMode.value === 'fields') await saveReport(false)
    else report.value = await getReport(report.value.id)
    report.value = await generateReport(report.value.id)
    await refreshGenerationHistory()
    const exported = generationHistory.value.find((item) => item.report_id === report.value?.id && item.status === 'SUCCESS')
    if (exported) window.open(reportGenerationFileUrl(exported.id), '_blank')
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    busy.export = false
  }
}

async function openVersions() {
  if (!report.value) return
  versions.value = await getVersions(report.value.id)
  versionsVisible.value = true
}

async function handleUpload(options: UploadRequestOptions) {
  if (report.value?.word_edit_locked) {
    ElMessage.warning('Word 已人工编辑并保存，不能再用 PDF 自动填充；请新建报告。')
    return
  }
  busy.upload = true
  uploadPercent.value = 0
  try {
    uploadedSource.value = await uploadPdf(options.file, (value) => (uploadPercent.value = value))
    uploadedSource.value = await extractPdf(uploadedSource.value.id)
    for (const field of uploadedSource.value.extracted_fields) applyExtractedValue(field)
    await saveReport(false)
    await rebuildWordFromSources()
    ElMessage.success(`PDF 已解析并填充 ${uploadedSource.value.extracted_fields.length} 个字段`)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    busy.upload = false
  }
}

function applyExtractedValue(field: ExtractedField) {
  if (!report.value) return
  setField(field.field_code, field.value)
  report.value.resolved_data.field_sources[field.field_code] = field.source
  report.value.resolved_data.original_values[field.field_code] = field.value
  if (!bindings.value.some((item) => item.field_code === field.field_code)) {
    bindings.value.push({ field_code: field.field_code, label: field.label, current_value: field.value, original_value: field.value, source: field.source, modified: false })
  }
  selectField(field.field_code)
}

async function applyExtracted(field: ExtractedField) {
  applyExtractedValue(field)
  await saveReport(false)
  await rebuildWordFromSources()
  ElMessage.success(`${field.label}已填充到 Word`)
}

async function rebuildWordFromSources() {
  if (!report.value) return
  if (report.value.word_edit_locked) throw new Error('Word 已人工编辑并保存，不能再次自动生成；请新建报告。')
  onlyOfficeEditor?.destroyEditor?.()
  onlyOfficeEditor = undefined
  report.value = await rebuildReport(report.value.id)
  await refreshBindings()
  await nextTick()
  await openOnlyOffice()
}

function restoreOriginal() {
  setField(selectedCode.value, selectedBinding.value.original_value)
  ElMessage.success('已恢复原始值')
}

function formatDocument(command: 'bold' | 'italic' | 'underline' | 'fontName' | 'fontSize', value?: string) {
  document.execCommand(command, false, value)
}

function loadOnlyOfficeApi(serverUrl: string) {
  if (window.DocsAPI) return Promise.resolve()
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-onlyoffice-api]')
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('ONLYOFFICE 编辑器脚本加载失败')), { once: true })
      return
    }
    const script = document.createElement('script')
    script.src = `${serverUrl}/web-apps/apps/api/documents/api.js`
    script.dataset.onlyofficeApi = 'true'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('ONLYOFFICE 编辑器脚本加载失败'))
    document.head.appendChild(script)
  })
}

async function openOnlyOffice() {
  if (!report.value || editorMode.value !== 'word') return
  onlyOfficeLoading.value = true
  onlyOfficeError.value = ''
  try {
    onlyOfficeEditor?.destroyEditor?.()
    const bootstrap = await getOnlyOfficeConfig(report.value.id)
    const reportId = report.value.id
    const config = bootstrap.config as Record<string, unknown> & { events?: Record<string, unknown> }
    config.events = {
      ...(config.events || {}),
      onDocumentStateChange: (event: { data?: boolean }) => {
        if (event.data !== false) return
        window.setTimeout(async () => {
          if (report.value?.id !== reportId) return
          try {
            report.value = await getReport(reportId)
            reportTasks.value = reportTasks.value.map((item) => item.id === reportId ? report.value! : item)
          } catch { /* callback may still be committing; backend remains authoritative */ }
        }, 1500)
      },
    }
    await loadOnlyOfficeApi(bootstrap.documentServerUrl)
    await nextTick()
    if (!window.DocsAPI) throw new Error('ONLYOFFICE 编辑器 API 不可用')
    onlyOfficeEditor = new window.DocsAPI.DocEditor('onlyoffice-editor', config)
  } catch (error) {
    onlyOfficeError.value = errorText(error)
  } finally {
    onlyOfficeLoading.value = false
  }
}

async function changeEditorMode(value: string | number | boolean) {
  editorMode.value = value as 'word' | 'fields'
  if (editorMode.value === 'word') {
    await nextTick()
    await openOnlyOffice()
  } else {
    onlyOfficeEditor?.destroyEditor?.()
    onlyOfficeEditor = undefined
  }
}

async function refreshGenerationHistory() {
  generationLoading.value = true
  try {
    generationHistory.value = (await listReportGenerations()).items
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    generationLoading.value = false
  }
}

async function refreshReportTasks() {
  reportTasks.value = await listReports()
}

async function openReportTask(item: ReportTask) {
  if (generationLoading.value && report.value?.id === item.id) return
  generationLoading.value = true
  try {
    onlyOfficeEditor?.destroyEditor?.()
    onlyOfficeEditor = undefined
    report.value = await getReport(item.id)
    selectedLimsInstances.value = []
    limsRecognition.value = undefined
    selectedLimsDetail.value = undefined
    uploadedSource.value = undefined
    const loadedInstances = report.value.resolved_data.source_payloads.LIMS?.instances
    if (Array.isArray(loadedInstances)) selectedLimsInstances.value = loadedInstances as unknown as LimsInstanceSummary[]
    await refreshBindings()
    await selectField('report_no')
    savedAt.value = new Date(report.value.updated_at).toLocaleTimeString('zh-CN', { hour12: false })
    await nextTick()
    await openOnlyOffice()
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    generationLoading.value = false
  }
}

function downloadGeneration(item: ReportGeneration) {
  if (item.status === 'SUCCESS') window.open(reportGenerationFileUrl(item.id), '_blank')
}

async function initialize() {
  busy.init = true
  try {
    const [capabilities, existing, generationPage] = await Promise.all([
      getLimsCapabilities(), listReports(), listReportGenerations(),
    ])
    limsCapabilities.value = capabilities
    generationHistory.value = generationPage.items
    reportTasks.value = existing
    report.value = existing[0]
    if (!report.value) return
    const loadedInstances = report.value.resolved_data.source_payloads.LIMS?.instances
    if (Array.isArray(loadedInstances)) selectedLimsInstances.value = loadedInstances as unknown as LimsInstanceSummary[]
    await refreshBindings()
    await selectField('report_no')
    savedAt.value = new Date(report.value.updated_at).toLocaleTimeString('zh-CN', { hour12: false })
    await nextTick()
    await openOnlyOffice()
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    busy.init = false
  }
}

async function newBlankReport() {
  try {
    onlyOfficeEditor?.destroyEditor?.()
    onlyOfficeEditor = undefined
    report.value = await createReport()
    await refreshReportTasks()
    selectedLimsInstances.value = []
    limsRecognition.value = undefined
    selectedLimsDetail.value = undefined
    uploadedSource.value = undefined
    await refreshBindings()
    await selectField('report_no')
    await nextTick()
    await openOnlyOffice()
    ElMessage.success('已创建空白模板报告')
  } catch (error) {
    ElMessage.error(errorText(error))
  }
}

async function renameReport(item: ReportTask) {
  try {
    const { value } = await ElMessageBox.prompt(
      '修改后的名称用于“我的报告”和导出历史，不会改写 Word 正文。',
      '修改报告名称',
      {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputValue: item.title === '未命名报告' ? '' : item.title,
        inputPlaceholder: '请输入报告名称',
        inputPattern: /\S+/,
        inputErrorMessage: '报告名称不能为空',
      },
    )
    const target = item.id === report.value?.id ? report.value : await getReport(item.id)
    target.title = value.trim()
    const updated = await updateReport(target)
    reportTasks.value = reportTasks.value.map((row) => row.id === updated.id ? updated : row)
    if (report.value?.id === updated.id) report.value = updated
    ElMessage.success('报告名称已修改')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorText(error))
  }
}

onMounted(() => {
  void initialize()
})

onUnmounted(() => {
  onlyOfficeEditor?.destroyEditor?.()
})
</script>

<template>
  <div v-loading.fullscreen.lock="busy.init" class="studio-shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark"><Document /></span>
        <div><strong>智检报告工作台</strong><small>WORD REPORT STUDIO</small></div>
      </div>
      <div v-if="report" class="report-meta">
        <span class="status-dot" />
        <strong>{{ report.resolved_data.report_no }}</strong>
        <el-tag size="small" type="warning" effect="plain">{{ statusLabel }}</el-tag>
        <span>模板 {{ report.resolved_data.template_version }}</span>
      </div>
      <div class="top-actions">
        <el-button :icon="Plus" @click="newBlankReport">新建报告</el-button>
        <template v-if="report">
          <el-switch v-model="showSources" inline-prompt active-text="来源" inactive-text="隐藏" />
          <el-button :icon="View" aria-label="预览 PDF" title="预览 PDF" @click="previewVisible = true">预览 PDF</el-button>
          <el-button :icon="Clock" aria-label="版本记录" title="版本记录" @click="openVersions">版本记录</el-button>
          <el-button :icon="Download" aria-label="导出 Word" title="导出 Word" :loading="busy.export" @click="exportWord">导出 Word</el-button>
          <el-button class="top-critical-action" :loading="busy.save" @click="saveReport()">保存</el-button>
        </template>
        <div class="top-session">
          <span>{{ sessionUser.displayName }}</span>
          <el-button :icon="SwitchButton" @click="$emit('logout')">退出</el-button>
        </div>
      </div>
    </header>

    <main v-if="report" class="workspace">
      <aside class="history-panel panel">
        <div class="panel-header">
          <div><h2>报告中心</h2><p>任务与正式导出分开管理</p></div>
          <el-button circle :icon="Refresh" aria-label="刷新列表" title="刷新列表"
            :loading="generationLoading" @click="sidebarTab === 'reports' ? refreshReportTasks() : refreshGenerationHistory()" />
        </div>
        <div class="source-tabs report-tabs">
          <button :class="{ active: sidebarTab === 'reports' }" @click="sidebarTab = 'reports'">我的报告</button>
          <button :class="{ active: sidebarTab === 'exports' }" @click="sidebarTab = 'exports'">导出历史</button>
        </div>
        <el-input v-model="generationSearch" placeholder="搜索报告名称或编号" :prefix-icon="Search" clearable />
        <div v-if="sidebarTab === 'reports'" v-loading="generationLoading" class="generation-list">
          <div v-for="item in filteredReportTasks" :key="item.id" class="generation-item"
            :class="{ active: report.id === item.id }" role="button" tabindex="0"
            @click="openReportTask(item)" @keydown.enter="openReportTask(item)">
            <span class="generation-item-head">
              <strong>{{ item.title || '未命名报告' }}</strong>
              <el-tag v-if="item.word_edit_locked" size="small" effect="plain" type="warning">人工锁定</el-tag>
              <el-button text circle :icon="EditPen" aria-label="修改报告名称" title="修改报告名称" @click.stop="renameReport(item)" />
            </span>
            <span class="generation-report-no">{{ item.resolved_data.report_no || '暂无报告编号' }}</span>
            <span class="generation-meta"><time>{{ formatGenerationTime(item.updated_at) }}</time><small>{{ item.status }}</small></span>
          </div>
          <el-empty v-if="!filteredReportTasks.length" :image-size="52" description="还没有报告任务">
            <el-button type="primary" :icon="Plus" @click="newBlankReport">新建报告</el-button>
          </el-empty>
        </div>
        <div v-else v-loading="generationLoading" class="generation-list">
          <button v-for="item in filteredGenerationHistory" :key="item.id" class="generation-item" @click="downloadGeneration(item)">
            <span class="generation-item-head">
              <strong>{{ item.title || '未命名报告' }}</strong>
              <el-tag size="small" effect="plain" :type="item.status === 'SUCCESS' ? 'success' : item.status === 'FAILED' ? 'danger' : 'warning'">
                {{ generationStatusLabel(item.status) }}
              </el-tag>
            </span>
            <span class="generation-report-no">{{ item.resolved_data?.report_no || '暂无报告编号' }}</span>
            <span class="generation-meta">
              <time>{{ formatGenerationTime(item.generated_at) }}</time>
              <small>V{{ item.version_no || '-' }}</small>
            </span>
          </button>
          <el-empty v-if="!filteredGenerationHistory.length" :image-size="52" :description="generationSearch ? '未找到匹配的导出' : '还没有导出记录'">
            <p v-if="!generationSearch" class="history-empty-hint">完成报告并导出 Word 后，会在这里形成可追溯记录。</p>
          </el-empty>
        </div>
      </aside>

      <aside class="source-panel panel">
        <div class="panel-header">
          <div><h2>数据源</h2><p>LIMS 与 PDF</p></div>
          <el-button circle :icon="Refresh" aria-label="刷新数据源" title="刷新数据源" @click="refreshBindings" />
        </div>
        <el-input v-model="sourceSearch" placeholder="搜索字段或数据" :prefix-icon="Search" clearable />
        <div class="source-tabs">
          <button :class="{ active: activeSource === 'all' }" @click="activeSource = 'all'">全部</button>
          <button :class="{ active: activeSource === 'LIMS' }" @click="activeSource = 'LIMS'">LIMS</button>
          <button :class="{ active: activeSource === 'PDF' }" @click="activeSource = 'PDF'">PDF</button>
        </div>

        <div class="source-scroll">
          <section v-if="activeSource === 'all' || activeSource === 'LIMS'" class="source-group">
            <div class="source-heading">
              <span class="source-icon lims"><DataAnalysis /></span>
              <div><strong>生产 LIMS</strong><small>{{ selectedLimsInstances.length ? `${selectedLimsInstances.length} 条实验记录 · ${limsTreeData.length} 类数据` : '等待导入实验数据' }}</small></div>
              <el-tag v-if="selectedLimsInstances.length" size="small" type="success">已载入</el-tag>
            </div>
            <div class="lims-actions">
              <el-tooltip :content="limsCapabilities.sqlConfigured ? '从 LIMS 数据库读取' : '请联系系统管理员配置 SQL 连接'">
                <el-button :icon="Coin" :disabled="!limsCapabilities.sqlEnabled || !limsCapabilities.sqlConfigured" @click="readLimsSql">读取 SQL</el-button>
              </el-tooltip>
              <el-upload v-if="limsCapabilities.excelImportEnabled" accept=".xlsx" :show-file-list="false" :http-request="handleLimsExcel">
                <el-button :icon="Upload" :loading="limsLoading">导入 Excel</el-button>
              </el-upload>
            </div>
            <el-tree v-if="limsTreeData.length" :data="limsTreeData" node-key="id" default-expand-all
              :expand-on-click-node="false" class="lims-data-tree" @node-click="selectLimsTreeNode">
              <template #default="{ data }">
                <span class="lims-tree-node"><span>{{ data.label }}</span><small v-if="data.value">{{ data.value }}</small></span>
              </template>
            </el-tree>
            <el-empty v-else description="导入并识别 LIMS 数据后在此显示" :image-size="44" />
          </section>

          <section v-if="activeSource === 'all' || activeSource === 'PDF'" class="source-group">
            <div class="source-heading">
              <span class="source-icon pdf"><Files /></span>
              <div><strong>{{ uploadedSource?.file_name || '供应商检测报告.pdf' }}</strong><small>{{ uploadedSource ? '已上传并解析' : `示例来源 · ${sourceCounts.PDF} 个字段` }}</small></div>
            </div>
            <button v-for="item in filteredBindings.filter((row) => row.source.type === 'PDF')" :key="item.field_code"
              class="source-field" :class="{ selected: selectedCode === item.field_code, conflict: item.modified }" @click="selectField(item.field_code)">
              <span>{{ item.label }}</span><b>{{ item.current_value }}</b><i>P{{ item.source.page || '-' }}</i>
            </button>
            <button v-for="field in uploadedSource?.extracted_fields || []" :key="`upload-${field.field_code}`" class="source-field extracted" @click="applyExtracted(field)">
              <span>{{ field.label }}</span><b>{{ field.value }}</b><i>{{ Math.round(field.confidence * 100) }}%</i>
            </button>
            <el-upload accept=".pdf" :show-file-list="false" :http-request="handleUpload" class="source-upload">
              <el-button text :icon="Upload" :loading="busy.upload" :disabled="report.word_edit_locked">添加 PDF 数据源</el-button>
            </el-upload>
            <el-progress v-if="busy.upload" :percentage="uploadPercent" :show-text="false" :stroke-width="3" />
          </section>

        </div>
      </aside>

      <section class="editor-panel">
        <div class="editor-toolbar">
          <el-segmented :model-value="editorMode" :options="[{ label: '在线 Word', value: 'word' }, { label: '字段视图', value: 'fields' }]" size="small" @change="changeEditorMode" />
          <div v-if="editorMode === 'fields'" class="tool-group">
            <el-tooltip content="加粗"><button class="format-button" @mousedown.prevent="formatDocument('bold')"><b>B</b></button></el-tooltip>
            <el-tooltip content="斜体"><button class="format-button" @mousedown.prevent="formatDocument('italic')"><i>I</i></button></el-tooltip>
            <el-tooltip content="下划线"><button class="format-button" @mousedown.prevent="formatDocument('underline')"><u>U</u></button></el-tooltip>
            <span class="tool-divider" />
            <button class="select-tool" @mousedown.prevent="formatDocument('fontName', 'SimSun')">宋体</button><button class="select-tool" @mousedown.prevent="formatDocument('fontSize', '2')">10.5</button>
          </div>
          <div v-if="editorMode === 'fields'" class="source-legend">
            <span><i class="legend-dot lims" />LIMS</span><span><i class="legend-dot pdf" />PDF</span><span><i class="legend-dot manual" />人工</span>
          </div>
          <div class="save-state">已保存 {{ savedAt }}</div>
          <el-button text circle :icon="MoreFilled" aria-label="更多编辑选项" title="更多编辑选项" />
        </div>

        <div v-if="editorMode === 'word'" v-loading="onlyOfficeLoading" class="onlyoffice-shell">
          <el-result v-if="onlyOfficeError" icon="error" title="ONLYOFFICE 加载失败" :sub-title="onlyOfficeError">
            <template #extra><el-button type="primary" @click="openOnlyOffice">重新加载</el-button></template>
          </el-result>
          <div v-else id="onlyoffice-editor" class="onlyoffice-host" />
        </div>

        <div v-else class="document-scroll">
          <article class="paper">
            <div class="doc-code">文件编号：QMS-R-028</div>
            <h1 contenteditable spellcheck="false" class="doc-project" :class="sourceClass('project_name')"
              @focus="selectField('project_name')" @input="editBound('project_name', $event)">{{ report.resolved_data.project_name }}</h1>
            <div class="doc-title">检验检测报告</div>
            <div class="doc-subtitle">TESTING REPORT</div>

            <table class="meta-table">
              <tbody>
                <tr>
                  <th>报告编号</th>
                  <td><span contenteditable spellcheck="false" class="bound" :class="[sourceClass('report_no'), { active: selectedCode === 'report_no' }]"
                    @focus="selectField('report_no')" @input="editBound('report_no', $event)">{{ report.resolved_data.report_no }}</span></td>
                  <th>报告日期</th>
                  <td><span contenteditable class="bound" :class="sourceClass('report_date')" @focus="selectField('report_date')" @input="editBound('report_date', $event)">{{ report.resolved_data.report_date }}</span></td>
                </tr>
                <tr><th>客户名称</th><td colspan="3"><span contenteditable class="bound wide" :class="[sourceClass('customer'), { active: selectedCode === 'customer' }]" @focus="selectField('customer')" @input="editBound('customer', $event)">{{ report.resolved_data.customer }}</span></td></tr>
                <tr><th>样品名称</th><td colspan="3"><span contenteditable class="bound wide" :class="[sourceClass('sample'), { active: selectedCode === 'sample' }]" @focus="selectField('sample')" @input="editBound('sample', $event)">{{ report.resolved_data.sample }}</span></td></tr>
              </tbody>
            </table>

            <div class="section-heading"><h3>一、检测结果</h3><el-button size="small" :icon="Plus" @click="addTestItem">添加检测项</el-button></div>
            <table class="result-table">
              <thead><tr><th>分类</th><th>检测项目</th><th>检测方法</th><th>技术要求</th><th>结果</th><th>结论</th><th class="row-action" /></tr></thead>
              <tbody>
                <tr v-for="(item, index) in report.resolved_data.test_items" :key="item.id">
                  <td v-if="firstInCategory(index)" :rowspan="categorySpan(index)"><span contenteditable class="bound compact" :class="sourceClass(itemCode(item, 'category'))" @focus="selectField(itemCode(item, 'category'))" @input="editBound(itemCode(item, 'category'), $event)">{{ item.category }}</span></td>
                  <td><span contenteditable class="bound compact" :class="[sourceClass(itemCode(item, 'name')), { active: selectedCode === itemCode(item, 'name') }]" @focus="selectField(itemCode(item, 'name'))" @input="editBound(itemCode(item, 'name'), $event)">{{ item.name }}</span></td>
                  <td><span contenteditable class="bound compact" :class="sourceClass(itemCode(item, 'method'))" @focus="selectField(itemCode(item, 'method'))" @input="editBound(itemCode(item, 'method'), $event)">{{ item.method }}</span></td>
                  <td><span contenteditable class="bound compact" :class="sourceClass(itemCode(item, 'requirement'))" @focus="selectField(itemCode(item, 'requirement'))" @input="editBound(itemCode(item, 'requirement'), $event)">{{ item.requirement }}</span></td>
                  <td><span contenteditable class="bound compact result-value" :class="[sourceClass(itemCode(item, 'result')), { active: selectedCode === itemCode(item, 'result') }]" @focus="selectField(itemCode(item, 'result'))" @input="editBound(itemCode(item, 'result'), $event)">{{ item.result }}</span> {{ item.unit }}</td>
                  <td><span contenteditable class="bound compact" :class="sourceClass(itemCode(item, 'conclusion'))" @focus="selectField(itemCode(item, 'conclusion'))" @input="editBound(itemCode(item, 'conclusion'), $event)">{{ item.conclusion }}</span></td>
                  <td class="row-action"><el-button text circle :icon="Delete" aria-label="删除检测项" title="删除检测项" :disabled="report.resolved_data.test_items.length <= 1" @click="removeTestItem(item)" /></td>
                </tr>
              </tbody>
            </table>

            <h3>二、检验结论</h3>
            <p contenteditable class="conclusion bound" :class="[sourceClass('conclusion'), { active: selectedCode === 'conclusion' }]" @focus="selectField('conclusion')" @input="editBound('conclusion', $event)">{{ report.resolved_data.conclusion }}</p>
            <div class="signatures">
              <span>编制：<b contenteditable @focus="selectField('author')" @input="editBound('author', $event)">{{ report.resolved_data.author }}</b></span>
              <span>复核：<b contenteditable @focus="selectField('reviewer')" @input="editBound('reviewer', $event)">{{ report.resolved_data.reviewer || '__________' }}</b></span>
              <span>批准：<b contenteditable @focus="selectField('approver')" @input="editBound('approver', $event)">{{ report.resolved_data.approver || '__________' }}</b></span>
            </div>
            <footer class="doc-footer"><span>受控文件</span><span>第 1 页 / 共 1 页</span></footer>
          </article>
        </div>
      </section>

      <aside class="detail-panel panel">
        <div class="detail-header">
          <div><span class="detail-eyebrow">当前字段</span><h2>{{ selectedBinding.label }}</h2><code>{{ selectedBinding.field_code }}</code></div>
          <span class="source-badge" :class="selectedBinding.source.type.toLowerCase()">{{ sourceLabels[selectedBinding.source.type] }}</span>
        </div>
        <div class="current-value">
          <label>当前值</label><strong>{{ selectedBinding.current_value || '未填写' }}</strong>
          <div v-if="selectedBinding.modified" class="modified-warning"><EditPen /> 已人工修改，与原始数据不同</div>
        </div>

        <el-tabs v-model="detailTab" stretch class="detail-tabs">
          <el-tab-pane label="来源详情" name="source">
            <dl class="facts">
              <dt>来源类型</dt><dd>{{ sourceLabels[selectedBinding.source.type] }}</dd>
              <dt>记录标识</dt><dd>{{ selectedBinding.source.record_id || selectedBinding.source.document_id || '-' }}</dd>
              <template v-if="selectedBinding.source.type === 'LIMS' && selectedBinding.source.instance_title">
                <dt>实验记录</dt><dd>{{ selectedBinding.source.instance_title }}</dd>
                <dt>章节路径</dt><dd>{{ selectedBinding.source.section_path?.join(' › ') || '-' }}</dd>
                <dt>证据位置</dt><dd>{{ selectedBinding.source.excel_row ? `Excel 第 ${selectedBinding.source.excel_row} 行` : '' }}{{ selectedBinding.source.table_index ? ` · 原文表 ${selectedBinding.source.table_index}` : '' }}</dd>
                <dt>原始表头</dt><dd>{{ selectedBinding.source.headers?.join(' | ') || '-' }}</dd>
              </template>
              <dt>原始值</dt><dd>{{ selectedBinding.original_value || '-' }}</dd>
              <dt>当前值</dt><dd>{{ selectedBinding.current_value || '-' }}</dd>
            </dl>
            <div v-if="selectedBinding.source.type === 'PDF'" class="evidence-card">
              <div class="evidence-head"><strong>PDF 原文证据</strong><span>第 {{ selectedBinding.source.page || '-' }} 页</span></div>
              <div class="pdf-snapshot">
                <div class="fake-line long" /><div class="fake-line" />
                <div class="evidence-highlight">{{ selectedBinding.source.quote || selectedBinding.current_value }}</div>
                <div class="fake-line long" /><div class="fake-line short" />
              </div>
              <el-button plain :icon="View" @click="previewVisible = true">打开 PDF 并定位</el-button>
            </div>
            <div v-else-if="selectedBinding.source.type === 'LIMS'" class="record-card">
              <DataAnalysis /><div><small>LIMS 原始记录</small><strong>{{ selectedBinding.source.record_id }}</strong></div><el-button link type="primary" @click="ElMessage.info('正式接入 LIMS 后将在此打开原始记录')">查看</el-button>
            </div>
            <div v-else class="manual-card"><EditPen /><div><strong>人工录入字段</strong><small>该值由报告编制人员直接维护</small></div></div>
          </el-tab-pane>
          <el-tab-pane label="修改历史" name="history">
            <div v-if="history.length" class="history-timeline">
              <div v-for="event in history" :key="event.id" class="history-event"><i /><div><b>{{ event.operator }} · {{ new Date(event.created_at).toLocaleString('zh-CN') }}</b><p>{{ event.old_value || '空' }} → {{ event.new_value || '空' }}</p><small>{{ event.reason }}</small></div></div>
            </div>
            <el-empty v-else description="该字段还没有修改记录" :image-size="60" />
          </el-tab-pane>
          <el-tab-pane label="校验" name="check">
            <el-alert title="字段格式校验通过" type="success" :closable="false" show-icon />
            <div class="validation-list"><span>必填性检查</span><b>通过</b><span>来源完整性</span><b>通过</b><span>值域规则</span><b>通过</b></div>
          </el-tab-pane>
        </el-tabs>
        <div v-if="selectedBinding.modified" class="detail-actions"><el-button @click="restoreOriginal">恢复原始值</el-button><el-button type="primary" @click="saveReport()">保留人工值</el-button></div>
      </aside>
    </main>

    <main v-else class="workspace-empty">
      <el-empty :image-size="96" description="当前账号还没有报告">
        <p class="history-empty-hint">点击“新建报告”后才会创建报告任务，打开页面不会自动新增。</p>
        <el-button type="primary" :icon="Plus" @click="newBlankReport">新建报告</el-button>
      </el-empty>
    </main>

    <el-dialog v-model="previewVisible" title="PDF 预览与证据定位" width="78%" class="preview-dialog">
      <iframe v-if="uploadedSource" :src="uploadedSource.preview_url" class="pdf-frame" />
      <div v-else class="preview-placeholder"><Files /><h3>供应商检测报告.pdf</h3><p>当前展示的是原型证据数据。上传真实 PDF 后，这里会显示原文件并定位到选中字段。</p><div class="large-evidence">{{ selectedBinding.source.quote || '请选择一个 PDF 来源字段' }}</div></div>
    </el-dialog>

    <el-dialog v-model="limsDialogVisible" title="选择并识别 LIMS 实验记录" width="1080px" class="lims-instance-dialog">
      <div v-if="limsImport" class="lims-import-summary">
        <strong>{{ limsImport.fileName }}</strong>
        <span>{{ limsImport.summary.rowCount }} 行查询结果</span>
        <span>{{ limsImport.summary.instanceCount }} 个实验实例</span>
      </div>
      <el-table v-if="limsImport && !limsRecognition" :data="limsImport.summary.instances" max-height="430" stripe @selection-change="handleLimsSelection">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="instanceId" label="实例编号" width="130" />
        <el-table-column prop="title" label="实验名称" min-width="260" show-overflow-tooltip />
        <el-table-column prop="version" label="版本" width="70" />
        <el-table-column prop="createdBy" label="编制人" width="90" />
        <el-table-column label="结构化记录" width="105"><template #default="scope">{{ structuredTotal(scope.row.structuredDataCounts) }}</template></el-table-column>
        <el-table-column prop="richTextCount" label="原文块" width="80" />
      </el-table>
      <div v-if="limsRecognition" class="lims-recognition-result">
        <div class="recognition-metrics">
          <span><b>{{ limsRecognition.recognizedTotal }}</b> 条结构化数据</span>
          <span><b>{{ limsRecognition.coverage.recognizedTables }}</b> 张已识别表</span>
          <span><b>{{ limsRecognition.duplicateCount }}</b> 条重复已合并</span>
          <span :class="{ warning: limsRecognition.unmatched.length }"><b>{{ limsRecognition.unmatched.length }}</b> 张未识别表</span>
        </div>
        <div class="recognition-sections">
          <el-tag v-for="(count, key) in limsRecognition.recognizedCounts" :key="key" effect="plain">{{ limsCollectionLabels[key] || key }} {{ count }}</el-tag>
        </div>
        <el-alert v-if="limsRecognition.unmatched.length" :title="`${limsRecognition.unmatched.length} 张表无法可靠归类，已保留为原始证据，不会静默填充`" type="warning" :closable="false" show-icon />
        <section v-if="limsRecognition.conflicts.length" class="conflict-list">
          <h3>同名数据冲突（{{ limsRecognition.conflicts.length }}）</h3>
          <article v-for="conflict in limsRecognition.conflicts" :key="conflict.id">
            <strong>{{ conflict.label }} · {{ conflict.identity }}</strong>
            <el-radio-group v-model="conflictResolutions[conflict.id]">
              <el-radio v-for="option in conflict.options" :key="option.candidateId" :value="option.candidateId" border>
                <span>{{ option.evidence.instanceTitle || option.evidence.instanceId }}</span>
                <small>{{ JSON.stringify(option.value) }}</small>
              </el-radio>
            </el-radio-group>
          </article>
        </section>
      </div>
      <el-alert v-else class="lims-instance-note" title="可多选同一项目下的实验记录。系统会先识别、去重并展示冲突，确认后才写入 Word。" type="info" :closable="false" show-icon />
      <template #footer>
        <el-button @click="limsDialogVisible = false">取消</el-button>
        <el-button v-if="limsRecognition" @click="limsRecognition = undefined">返回重选</el-button>
        <el-button v-if="!limsRecognition" type="primary" :loading="limsLoading" :disabled="!selectedLimsInstances.length" @click="recognizeSelectedLims">识别所选记录</el-button>
        <el-button v-else type="primary" :loading="limsLoading" :disabled="report?.word_edit_locked" @click="applySelectedLims">确认并填充 Word</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="versionsVisible" title="报告版本记录" size="420px">
      <div class="version-list">
        <article v-for="version in versions" :key="version.id" class="version-item"><span>V{{ version.version_no }}</span><div><strong>{{ version.note }}</strong><small>{{ new Date(version.created_at).toLocaleString('zh-CN') }}</small><p>{{ version.data.report_no }} · {{ version.data.project_name }}</p></div></article>
      </div>
    </el-drawer>
  </div>
</template>
