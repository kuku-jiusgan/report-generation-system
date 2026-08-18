import type { DesignerBlock, DesignerChapter, MappingRule } from '../admin-api'

export function adminErrorText(error: unknown) {
  const value = error as {
    response?: { data?: { detail?: string | { message?: string; validation?: { errors?: Array<{ fieldCode?: string; locationId?: string; message?: string }> } } } }
    message?: string
  }
  const detail = value.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.validation?.errors?.length) {
    const first = detail.validation.errors[0]
    const target = first.fieldCode || first.locationId || '未知规则'
    return `${detail.message || '规则校验失败'}：${target}，${first.message || '请检查模板位置'}`
  }
  return detail?.message || value.message || '操作失败'
}

export function sourceTagType(type: string) {
  return ({
    SYSTEM: 'success', LIMS: 'success', PDF: 'warning', CALCULATED: 'primary', AI: 'danger', FIXED: 'info',
  } as Record<string, string>)[type] || 'info'
}

export function blockTone(block: DesignerBlock) {
  if (block.status === 'DISABLED') return 'disabled'
  if (block.status === 'PENDING') return 'pending'
  return block.kind.toLowerCase()
}

export function chapterTitle(item: DesignerChapter) {
  return ['cover', 'headerFooter'].includes(item.code) ? item.title : `${item.code}. ${item.title}`
}

export function firstAnchoredMapping(chapter: DesignerChapter): MappingRule | undefined {
  const mappings = chapter.blocks.flatMap((block) => block.mappings)
  return mappings.find((mapping) => mapping.controlTag)
    || chapter.children.map(firstAnchoredMapping).find(Boolean)
}

export function formatBytes(size: number) {
  return size < 1024 * 1024
    ? `${Math.round(size / 1024)} KB`
    : `${(size / 1024 / 1024).toFixed(1)} MB`
}
