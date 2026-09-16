import axios from 'axios'
import type { SystemGroupSourceMapping } from './admin-api'
const http = axios.create({ baseURL: '/api/v1/admin', timeout: 120000 })
http.interceptors.response.use(undefined, error => {
  if (error.response?.status === 401) window.dispatchEvent(new Event('auth-expired'))
  return Promise.reject(error)
})
export interface ProtocolMetadata {
  sourceType: 'PROTOCOL'; sourceLabel: string
  modes: Array<{ value: string; label: string; inputs: string[] }>
  inputs: Record<string, { label: string; help: string }>
  documents: Array<{ id: string; fileName: string }>
}
export interface ProtocolFieldResult {
  status: 'SUCCESS' | 'ERROR'; value?: unknown; message?: string
  source: { locations?: Array<{ section: string; paragraph?: number; table?: number; row?: number; column?: number; quote: string; parentValue?: string }> }
}
export interface ProtocolPreview { fields: Record<string, ProtocolFieldResult>; warnings: string[]; errors: string[]; groups?: Record<string, unknown> }
export async function loadProtocolMetadata() { return (await http.get<ProtocolMetadata>('/protocol-rule-metadata')).data }
export async function previewProtocolRule(data: { documentId: string; fieldCode: string; config: Record<string, unknown>; transform: string; sourceMappings?: SystemGroupSourceMapping[] }) {
  return (await http.post<ProtocolPreview>('/protocol-rules/preview', data)).data
}
