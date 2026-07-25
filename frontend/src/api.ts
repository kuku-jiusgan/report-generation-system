import axios from 'axios'

export type SourceType = 'LIMS' | 'PDF' | 'MANUAL' | 'CALCULATED'

export interface SourceRef {
  type: SourceType
  record_id?: string
  document_id?: string
  page?: number
  quote?: string
  rect?: number[]
  instance_title?: string
  section_path?: string[]
  excel_row?: number
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

export interface SourceDocument {
  id: string
  file_name: string
  size: number
  preview_url: string
  extracted_fields: ExtractedField[]
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
  created_at: string
  updated_at: string
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

export async function uploadPdf(file: File, onProgress?: (percent: number) => void) {
  const body = new FormData()
  body.append('file', file)
  return (
    await http.post<SourceDocument>('/source-documents', body, {
      onUploadProgress: (event) => event.total && onProgress?.(Math.round((event.loaded * 100) / event.total)),
    })
  ).data
}

export async function extractPdf(id: string) {
  return (await http.post<SourceDocument>(`/source-documents/${id}/extract`)).data
}

export async function createReport(sourceDocumentId?: string) {
  return (await http.post<ReportTask>('/reports', { source_document_id: sourceDocumentId })).data
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

export async function applyLimsToReport(
  id: string,
  importId: string,
  instanceIds: string[],
  conflictResolutions: Record<string, string>,
) {
  return (await http.post<ReportTask>(`/reports/${id}/apply-lims`, {
    import_id: importId,
    instance_ids: instanceIds,
    conflict_resolutions: conflictResolutions,
  })).data
}

export async function listReports() {
  return (await http.get<ReportTask[]>('/reports')).data
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

export async function submitReview(id: string) {
  return (await http.post<ReportTask>(`/reports/${id}/submit-review`)).data
}

export async function getOnlyOfficeConfig(id: string) {
  return (await http.get<OnlyOfficeBootstrap>(`/onlyoffice/reports/${id}/config`)).data
}
