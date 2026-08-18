import axios from 'axios'

export type SourceType = 'LIMS' | 'PDF' | 'EXCEL' | 'MANUAL' | 'MANUAL_WORD' | 'CALCULATED'

export interface SourceRef {
  type: SourceType
  record_id?: string
  document_id?: string
  page?: number
  quote?: string
  rect?: number[]
  instance_title?: string
  section_path?: string[]
  table_index?: number
  headers?: string[]
}

export interface ExtractedField {
  field_code: string
  label: string
  value: string
  confidence: number
  source: SourceRef
}

export interface TemplateSourceField {
  id: number
  wordLabel: string
  fieldCode: string
  bindingCode: string
  sourceType: string
  sourcePath: string
  repeatType: string
  tableNo: string
  controlTag: string
  orderNo: number
}

export interface TemplateSourceChapter {
  id: number
  parentId?: number
  code: string
  title: string
  orderNo: number
  fields: TemplateSourceField[]
  children: TemplateSourceChapter[]
}

export interface TemplateSourceCatalog { chapters: TemplateSourceChapter[] }

export interface SourceDocument {
  id: string
  file_name: string
  size: number
  preview_url: string
  extracted_fields: ExtractedField[]
  source_type: 'PDF' | 'EXCEL' | string
  warnings: string[]
  sha256: string
  summary: { impurityCount?: number; impurityNames?: string[] }
  created_at: string
}

export interface TestItem {
  id: string
  category: string
  name: string
  method: string
  requirement: string
  result: string
  unit: string
  conclusion: string
}

export interface ReportData {
  report_no: string
  customer: string
  sample: string
  project_name: string
  report_date: string
  conclusion: string
  author: string
  reviewer: string
  approver: string
  template_version: string
  template_id: string
  template_name: string
  template_code: string
  template_catalog_version_id: string
  template_revision: string
  test_items: TestItem[]
  field_sources: Record<string, SourceRef>
  original_values: Record<string, string>
  source_payloads: Record<string, Record<string, unknown>>
}

export interface ReportTask {
  id: string
  title: string
  status: string
  source_document_id?: string
  resolved_data: ReportData
  output_name?: string
  download_url?: string
  word_edit_locked: boolean
  word_edited_at?: string
  created_at: string
  updated_at: string
}

export interface ReportGeneration {
  id: string
  report_id: string
  version_id?: number
  version_no?: number
  status: 'PROCESSING' | 'SUCCESS' | 'FAILED' | string
  output_name?: string
  error_message?: string
  generated_at: string
  title: string
  resolved_data: ReportData
}

export interface ReportGenerationPage {
  total: number
  page: number
  pageSize: number
  items: ReportGeneration[]
}

export interface FieldBinding {
  field_code: string
  label: string
  current_value: string
  original_value: string
  source: SourceRef
  modified: boolean
}

export interface ChangeEvent {
  id: number
  report_id: string
  field_code: string
  old_value: string
  new_value: string
  operator: string
  reason: string
  created_at: string
}

export interface ReportVersion {
  id: number
  report_id: string
  version_no: number
  note: string
  created_at: string
  data: ReportData
}

export interface OnlyOfficeBootstrap {
  documentServerUrl: string
  config: Record<string, unknown>
}

const http = axios.create({ baseURL: '/api/v1', timeout: 60000 })
http.interceptors.response.use(undefined, (error) => {
  if (error.response?.status === 401) window.dispatchEvent(new Event('auth-expired'))
  return Promise.reject(error)
})

export async function uploadPdf(file: File, onProgress?: (percent: number) => void) {
  const body = new FormData()
  body.append('file', file)
  return (
    await http.post<SourceDocument>('/source-documents', body, {
      onUploadProgress: (event) => event.total && onProgress?.(Math.round((event.loaded * 100) / event.total)),
    })
  ).data
}

export async function uploadExcel(file: File, onProgress?: (percent: number) => void) {
  return uploadPdf(file, onProgress)
}

export async function extractPdf(id: string) {
  return (await http.post<SourceDocument>(`/source-documents/${id}/extract`)).data
}

export async function extractExcel(id: string) {
  return extractPdf(id)
}

export async function createReport(sourceDocumentId?: string, excelDocumentId?: string) {
  return (await http.post<ReportTask>('/reports', {
    source_document_id: sourceDocumentId, excel_document_id: excelDocumentId,
  })).data
}

export async function updateReport(report: ReportTask) {
  return (
    await http.put<ReportTask>(`/reports/${report.id}`, {
      title: report.title,
      data: report.resolved_data,
    })
  ).data
}

export async function generateReport(id: string) {
  return (await http.post<ReportTask>(`/reports/${id}/generate`)).data
}

export async function rebuildReport(id: string) {
  return (await http.post<ReportTask>(`/reports/${id}/rebuild-word`)).data
}

export async function replaceReportSource(id: string, sourceDocumentId: string, sourceType: 'PDF' | 'EXCEL') {
  return (await http.post<ReportTask>(`/reports/${id}/replace-source`, {
    source_document_id: sourceDocumentId, source_type: sourceType,
  }, { timeout: 300000 })).data
}

export async function applyLimsToReport(
  id: string,
  importId: string,
  instanceIds: string[],
  conflictResolutions: Record<string, string>,
  force = false,
) {
  return (await http.post<ReportTask>(`/reports/${id}/apply-lims`, {
    import_id: importId,
    instance_ids: instanceIds,
    conflict_resolutions: conflictResolutions,
    force,
  }, { timeout: 300000 })).data
}

export async function listReports() {
  return (await http.get<ReportTask[]>('/reports')).data
}

export async function getTemplateSourceCatalog() {
  return (await http.get<TemplateSourceCatalog>('/template-source-catalog')).data
}

export async function getReport(id: string) {
  return (await http.get<ReportTask>(`/reports/${id}`)).data
}

export async function deleteReport(id: string) {
  return (await http.delete<{ deleted: boolean }>(`/reports/${id}`)).data
}

export async function batchExportReports(ids: string[]) {
  return (await http.post<Blob>('/reports/batch-word', { report_ids: ids }, { responseType: 'blob' })).data
}

export function reportPdfUrl(id: string) {
  return `/api/v1/reports/${id}/pdf`
}

export async function listReportGenerations() {
  return (await http.get<ReportGenerationPage>('/report-generations', { params: { page: 1, page_size: 100 } })).data
}

export function reportGenerationFileUrl(id: string) {
  return `/api/v1/report-generations/${id}/file`
}

export async function getBindings(id: string) {
  return (await http.get<FieldBinding[]>(`/reports/${id}/bindings`)).data
}

export async function getHistory(id: string, fieldCode?: string) {
  return (await http.get<ChangeEvent[]>(`/reports/${id}/history`, { params: { field_code: fieldCode } })).data
}

export async function getVersions(id: string) {
  return (await http.get<ReportVersion[]>(`/reports/${id}/versions`)).data
}

export async function createVersion(id: string, note = '手工保存') {
  return (await http.post<ReportVersion>(`/reports/${id}/versions`, undefined, { params: { note } })).data
}

export async function getOnlyOfficeConfig(id: string) {
  return (await http.get<OnlyOfficeBootstrap>(`/onlyoffice/reports/${id}/config`)).data
}
