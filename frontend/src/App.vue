<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  ArrowLeft, Clock, Coin, DataAnalysis, Delete, Document, Download, EditPen, Files, MoreFilled,
  Plus, Refresh, Search, SwitchButton, Upload, View,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadRequestOptions } from 'element-plus'
import {
  applyLimsToReport, createVersion, extractPdf, generateReport, getBindings, getHistory, getTemplateSourceCatalog, getVersions,
  getReport, listReportGenerations, listReports, reportGenerationFileUrl, updateReport, uploadPdf,
  rebuildReport,
  type ChangeEvent, type ExtractedField, type FieldBinding, type ReportGeneration, type ReportTask, type ReportVersion,
  type SourceDocument, type SourceRef, type SourceType, type TemplateSourceCatalog, type TestItem,
} from './api'
import {
  getLimsCapabilities, queryLimsProject, recognizeLimsInstances,
  type LimsCapabilities, type LimsEvidence, type LimsImport, type LimsInstanceSummary, type LimsRecognition,
} from './lims-api'
import type { AuthUser } from './auth-api'
import { useReportChapterTree, type ReportTreeNode } from './composables/useReportChapterTree'
import { useReportWordEditor } from './composables/useReportWordEditor'

const props = defineProps<{ sessionUser: AuthUser; initialReportId?: string }>()
defineEmits<{ logout: []; back: [] }>()

const report = ref<ReportTask>()
const reportTasks = ref<ReportTask[]>([])
const generationHistory = ref<ReportGeneration[]>([])
const bindings = ref<FieldBinding[]>([])
const history = ref<ChangeEvent[]>([])
const versions = ref<ReportVersion[]>([])
const uploadedSource = ref<SourceDocument>()
const selectedCode = ref('report_no')
const detailTab = ref('source')
const showSources = ref(true)
const previewVisible = ref(false)
const versionsVisible = ref(false)
const uploadPercent = ref(0)
const sourceSearch = ref('')
const editorMode = ref<'word' | 'fields'>('word')
const savedAt = ref('')
const busy = reactive({ init: true, save: false, export: false, upload: false })
const limsCapabilities = ref<LimsCapabilities>({ sqlEnabled: false, sqlConfigured: false })
const limsImport = ref<LimsImport>()
const limsDialogVisible = ref(false)
const limsLoading = ref(false)
const limsProjectId = ref('')
const selectedLimsInstances = ref<LimsInstanceSummary[]>([])
const limsRecognition = ref<LimsRecognition>()
const conflictResolutions = reactive<Record<string, string>>({})
const selectedLimsDetail = ref<{ label: string; value: string; evidence: LimsEvidence }>()
const templateSourceCatalog = ref<TemplateSourceCatalog>({ chapters: [] })

const {
  loading: onlyOfficeLoading,
  error: onlyOfficeError,
  linkStatus: wordLinkStatus,
  locate: locateWordField,
  open: openOnlyOffice,
  close: closeOnlyOffice,
} = useReportWordEditor({
  reportId: () => report.value?.id,
  onDocumentSaved: refreshSavedReport,
})

const limsCollectionLabels: Record<string, string> = {
  samples: '供试品', referenceStandards: '对照品', instruments: '仪器', columns: '色谱柱',
  reagents: '试剂', weighings: '称量记录', solutions: '溶液配制', methodParameters: '方法参数',
  systemSuitability: '系统适用性', specificity: '专属性', lod: '检测限', loq: '定量限',
  linearity: '线性与范围', repeatability: '重复性', intermediatePrecision: '中间精密度',
  accuracy: '准确度', solutionStability: '溶液稳定性', sampleResults: '样品结果',
}

const sourceLabels: Record<SourceType, string> = {
  LIMS: 'LIMS', PDF: 'PDF', EXCEL: 'Excel', MANUAL: '人工', MANUAL_WORD: 'Word 人工编辑', CALCULATED: '计算',
}

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

const { chapterTreeData } = useReportChapterTree({
  report,
  recognition: limsRecognition,
  catalog: templateSourceCatalog,
  bindings: displayBindings,
  search: sourceSearch,
})

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
        table_index: evidence.tableIndex, headers: evidence.headers,
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
    const textMatches = !query || `${item.label} ${item.current_value} ${item.field_code}`.toLowerCase().includes(query)
    return textMatches
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

async function readLimsSql() {
  if (!limsCapabilities.value.sqlEnabled || !limsCapabilities.value.sqlConfigured) {
    ElMessage.warning('尚未配置 LIMS SQL 连接，请联系系统管理员')
    return
  }
  const projectId = limsProjectId.value.trim()
  if (!projectId) {
    ElMessage.warning('请输入项目编号')
    return
  }
  limsLoading.value = true
  try {
    limsImport.value = await queryLimsProject(projectId)
    selectedLimsInstances.value = []
    limsRecognition.value = undefined
    Object.keys(conflictResolutions).forEach((key) => delete conflictResolutions[key])
    limsDialogVisible.value = true
    ElMessage.success(`已查询到 ${limsImport.value.summary.instanceCount} 个实验实例`)
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
  let force = false
  if (report.value.word_edit_locked) {
    try {
      await ElMessageBox.confirm(
        '当前 Word 已有人工编辑内容。继续将按所选 LIMS 数据重新生成 Word，现有人工修改会被覆盖。',
        '确认覆盖人工编辑',
        { confirmButtonText: '继续填充', cancelButtonText: '取消', type: 'warning' },
      )
      force = true
    } catch {
      return
    }
  }
  const unresolved = limsRecognition.value.conflicts.filter((item) => !conflictResolutions[item.id])
  if (unresolved.length) {
    ElMessage.warning(`还有 ${unresolved.length} 个冲突需要选择`)
    return
  }
  limsLoading.value = true
  try {
    closeOnlyOffice()
    report.value = await applyLimsToReport(
      report.value.id,
      limsImport.value.id,
      selectedLimsInstances.value.map((item) => item.instanceId),
      { ...conflictResolutions },
      force,
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

function selectLimsTreeNode(node: ReportTreeNode) {
  if (node.controlTag) void locateWordField(node.controlTag, node.recordIndex || 0)
  if (node.bindingCode) {
    void selectField(node.bindingCode)
  } else if (node.extractedField) {
    applyExtracted(node.extractedField)
  } else if (node.evidence) {
    selectedLimsDetail.value = { label: node.label, value: node.value || '', evidence: node.evidence }
    detailTab.value = 'source'
  }
}

async function refreshBindings() {
  if (!report.value) return
  bindings.value = await getBindings(report.value.id)
}

async function refreshSavedReport(reportId: string) {
  if (report.value?.id !== reportId) return
  try {
    report.value = await getReport(reportId)
    reportTasks.value = reportTasks.value.map((item) => item.id === reportId ? report.value! : item)
  } catch { /* ONLYOFFICE callback may still be committing. */ }
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
    // Word 已人工编辑保存时 PUT 会 409；此时直接导出当前工作文件（含人工修改）
    if (editorMode.value === 'fields' && !report.value.word_edit_locked) await saveReport(false)
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
  if (report.value?.word_edit_locked) {
    ElMessage.warning('Word 已人工编辑并保存，不能再用 PDF 自动填充；请新建报告。')
    return
  }
  applyExtractedValue(field)
  await saveReport(false)
  await rebuildWordFromSources()
  ElMessage.success(`${field.label}已填充到 Word`)
}

async function rebuildWordFromSources() {
  if (!report.value) return
  if (report.value.word_edit_locked) throw new Error('Word 已人工编辑并保存，不能再次自动生成；请新建报告。')
  closeOnlyOffice()
  report.value = await rebuildReport(report.value.id)
  await refreshBindings()
  await nextTick()
  await openOnlyOffice()
}

function restoreOriginal() {
  setField(selectedCode.value, selectedBinding.value.original_value)
  ElMessage.success('已恢复原始值')
}

async function refreshGenerationHistory() {
  try {
    generationHistory.value = (await listReportGenerations()).items
  } catch (error) {
    ElMessage.error(errorText(error))
  }
}

async function refreshReportTasks() {
  reportTasks.value = await listReports()
}

async function initialize() {
  busy.init = true
  try {
    const [capabilities, existing, generationPage, sourceCatalog] = await Promise.all([
      getLimsCapabilities(), listReports(), listReportGenerations(), getTemplateSourceCatalog(),
    ])
    limsCapabilities.value = capabilities
    generationHistory.value = generationPage.items
    reportTasks.value = existing
    templateSourceCatalog.value = sourceCatalog
    report.value = existing.find((item) => item.id === props.initialReportId) || existing[0]
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

onMounted(() => {
  void initialize()
})
</script>

<template>
  <div v-loading.fullscreen.lock="busy.init" class="studio-shell">
    <main v-if="report" class="workspace">
      <aside class="source-panel panel">
        <div class="source-page-actions">
          <el-button :icon="ArrowLeft" aria-label="返回报告大厅" title="返回报告大厅" @click="$emit('back')">返回报告大厅</el-button>
        </div>
        <div class="panel-header">
          <div><h2>数据源</h2><p>LIMS 与 PDF</p></div>
          <div class="word-link-indicator">
            <span :class="wordLinkStatus.toLowerCase()"><i />{{ wordLinkStatus === 'PLUGIN' ? '定位已连接' : wordLinkStatus === 'CONNECTOR' ? 'Word 已连接' : '定位未连接' }}</span>
            <el-button circle :icon="Refresh" aria-label="刷新数据源" title="刷新数据源" @click="refreshBindings" />
          </div>
        </div>
        <el-input v-model="sourceSearch" placeholder="搜索字段或数据" :prefix-icon="Search" clearable />
        <div class="source-scroll">
          <div class="source-tools">
            <div class="lims-actions">
              <el-input v-model="limsProjectId" placeholder="项目编号，如 XM2024108" clearable
                :disabled="!limsCapabilities.sqlEnabled || !limsCapabilities.sqlConfigured"
                @keyup.enter="readLimsSql" />
              <el-tooltip :content="limsCapabilities.sqlConfigured ? '从 LIMS 数据库读取' : '请联系系统管理员配置 SQL 连接'">
                <el-button :icon="Coin" :loading="limsLoading" :disabled="!limsCapabilities.sqlEnabled || !limsCapabilities.sqlConfigured" @click="readLimsSql">查询 LIMS</el-button>
              </el-tooltip>
            </div>
            <el-upload accept=".pdf" :show-file-list="false" :http-request="handleUpload" class="source-upload">
              <el-button plain :icon="Upload" :loading="busy.upload" :disabled="report.word_edit_locked">添加 PDF 图谱</el-button>
            </el-upload>
            <el-progress v-if="busy.upload" :percentage="uploadPercent" :show-text="false" :stroke-width="3" />
          </div>
          <el-tree :data="chapterTreeData" node-key="id" :expand-on-click-node="true"
            highlight-current class="lims-data-tree chapter-source-tree" @node-click="selectLimsTreeNode">
            <template #default="{ data }">
              <span class="lims-tree-node" :class="{ directory: data.children?.length, field: !data.children?.length }">
                <span>{{ data.label }}</span><small v-if="!data.children?.length">{{ data.value || '' }}</small>
                <i v-if="data.sourceType" class="tree-source-mark" :class="data.sourceType.toLowerCase()">{{ data.sourceType }}</i>
              </span>
            </template>
          </el-tree>
        </div>
      </aside>

      <section class="editor-panel">
        <div v-loading="onlyOfficeLoading" class="onlyoffice-shell">
          <el-result v-if="onlyOfficeError" icon="error" title="ONLYOFFICE 加载失败" :sub-title="onlyOfficeError">
            <template #extra><el-button type="primary" @click="openOnlyOffice">重新加载</el-button></template>
          </el-result>
          <div v-else id="onlyoffice-editor" class="onlyoffice-host" />
        </div>

      </section>

    </main>

    <main v-else class="workspace-empty">
      <el-empty :image-size="96" description="当前账号还没有报告">
        <p class="history-empty-hint">请返回报告管理大厅发起新报告。</p>
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
        <el-button v-else type="primary" :loading="limsLoading" @click="applySelectedLims">确认并填充 Word</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="versionsVisible" title="报告版本记录" size="420px">
      <div class="version-list">
        <article v-for="version in versions" :key="version.id" class="version-item"><span>V{{ version.version_no }}</span><div><strong>{{ version.note }}</strong><small>{{ new Date(version.created_at).toLocaleString('zh-CN') }}</small><p>{{ version.data.report_no }} · {{ version.data.project_name }}</p></div></article>
      </div>
    </el-drawer>
  </div>
</template>
