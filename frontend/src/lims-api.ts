import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1/lims', timeout: 120000 })
http.interceptors.response.use(undefined, (error) => {
  if (error.response?.status === 401) window.dispatchEvent(new Event('auth-expired'))
  return Promise.reject(error)
})

export interface LimsCapabilities {
  sqlEnabled: boolean
  sqlConfigured: boolean
  excelImportEnabled: boolean
}

export interface LimsInstanceSummary {
  instanceId: string
  projectId?: string
  title: string
  version: number
  createdBy?: string
  createdTime?: string
  rowCount: number
  structuredDataCounts: Record<string, number>
  richTextCount: number
}

export interface LimsImport {
  id: string
  fileName: string
  size: number
  summary: {
    rowCount: number
    instanceCount: number
    projects: string[]
    instances: LimsInstanceSummary[]
  }
  createdAt: string
}

export interface LimsInstance extends LimsInstanceSummary {
  project: { id?: string; name?: string }
  document: { code?: string; version?: string }
  samples: Array<{ sampleName?: string; clientName?: string; sourceRecordId?: string }>
  approval: Array<{ field1?: string; field3?: string }>
}

export interface LimsEvidence {
  type?: string
  instanceId?: string
  instanceTitle?: string
  unitId?: string
  sectionPath?: string[]
  excelRow?: number
  richTextId?: string
  tableIndex?: number
  headers?: string[]
}

export interface LimsConflictOption {
  candidateId: string
  value: Record<string, unknown>
  evidence: LimsEvidence
}

export interface LimsConflict {
  id: string
  collection: string
  label: string
  identity: string
  options: LimsConflictOption[]
  resolved: boolean
}

export interface LimsRecognition {
  payload: Record<string, unknown>
  recognizedCounts: Record<string, number>
  recognizedTotal: number
  validationSections: string[]
  duplicateCount: number
  conflicts: LimsConflict[]
  unresolvedConflictCount: number
  unmatched: Array<Record<string, unknown>>
  coverage: { recognizedTables: number; unmatchedTables: number }
}

export async function getLimsCapabilities() {
  return (await http.get<LimsCapabilities>('/capabilities')).data
}

export async function uploadLimsExcel(file: File) {
  const body = new FormData()
  body.append('file', file)
  return (await http.post<LimsImport>('/imports', body)).data
}

export async function getLimsInstance(importId: string, instanceId: string) {
  return (await http.get<LimsInstance>(`/imports/${importId}/instances/${instanceId}`)).data
}

export async function recognizeLimsInstances(importId: string, instanceIds: string[]) {
  return (await http.post<LimsRecognition>(`/imports/${importId}/recognize`, {
    instance_ids: instanceIds,
  })).data
}
