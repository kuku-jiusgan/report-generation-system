import type { ReportTask } from './api'

export type ReportLifecycle = 'DRAFT' | 'REVIEW' | 'REVIEWED' | 'COMPLETED'
export type ReportHubTab = 'MINE' | ReportLifecycle | 'ALL'

export interface ReportStatusMeta {
  label: string
  type: '' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
}

export const REPORT_STATUS_META: Record<ReportLifecycle, ReportStatusMeta> = {
  DRAFT: { label: '草稿', type: 'info' },
  REVIEW: { label: '待复核', type: 'primary' },
  REVIEWED: { label: '已复核', type: 'warning' },
  COMPLETED: { label: '已完成', type: 'success' },
}

export interface ReportHubStats {
  mine: number
  draft: number
  review: number
  reviewed: number
  completed: number
  all: number
}

export interface ReportHubRow {
  report: ReportTask
  id: string
  title: string
  reportNumber: string
  projectNumber: string
  updatedAt: string
  experimentNames: string
  creator: string
  lifecycle: ReportLifecycle
  isOwned: boolean
}

export function reportLifecycle(status: string): ReportLifecycle {
  if (status === 'EDITING') return 'DRAFT'
  if (status === 'DATA_REVIEW') return 'REVIEW'
  if (status === 'READY_TO_GENERATE') return 'REVIEWED'
  if (status === 'GENERATED') return 'COMPLETED'
  throw new Error(`未知报告状态：${status}`)
}
