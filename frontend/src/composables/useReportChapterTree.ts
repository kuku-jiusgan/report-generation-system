import { computed, type ComputedRef, type Ref } from 'vue'
import type {
  ExtractedField, FieldBinding, ReportTask, TemplateSourceCatalog,
  TemplateSourceChapter, TemplateSourceField,
} from '../api'
import type { LimsEvidence, LimsRecognition } from '../lims-api'

export interface ReportTreeNode {
  id: string
  label: string
  value?: string
  evidence?: LimsEvidence
  bindingCode?: string
  extractedField?: ExtractedField
  sourceType?: 'LIMS' | 'PDF'
  controlTag?: string
  recordIndex?: number
  children?: ReportTreeNode[]
}

type DisplayBinding = FieldBinding & { current_value: string }

interface ChapterTreeOptions {
  report: Ref<ReportTask | undefined>
  recognition: Ref<LimsRecognition | undefined>
  catalog: Ref<TemplateSourceCatalog>
  bindings: ComputedRef<DisplayBinding[]>
  search: Ref<string>
}

export function useReportChapterTree(options: ChapterTreeOptions) {
  function payload() {
    return (options.recognition.value?.payload
      || options.report.value?.resolved_data.source_payloads.LIMS
      || {}) as Record<string, unknown>
  }

  function payloadValues(path: string) {
    const repeat = path.match(/^\$\.([^.[]+)\[\*]\.(.+)$/)
    if (repeat) {
      const records = payload()[repeat[1]]
      if (!Array.isArray(records)) return []
      return records.map((record) => repeat[2].split('.').reduce<unknown>(
        (value, key) => value && typeof value === 'object'
          ? (value as Record<string, unknown>)[key] : undefined,
        record,
      )).filter((value) => value !== undefined && value !== null && value !== '')
    }
    if (!path.startsWith('$.')) return []
    const value = path.slice(2).split('.').reduce<unknown>(
      (current, key) => current && typeof current === 'object'
        ? (current as Record<string, unknown>)[key] : undefined,
      payload(),
    )
    return value === undefined || value === null || value === '' ? [] : [value]
  }

  function nestedValue(record: Record<string, unknown>, sourcePath: string) {
    const repeat = sourcePath.match(/^\$\.[^.[]+\[\*]\.(.+)$/)
    if (!repeat) return undefined
    return repeat[1].split('.').reduce<unknown>(
      (value, key) => value && typeof value === 'object'
        ? (value as Record<string, unknown>)[key] : undefined,
      record,
    )
  }

  function fieldNode(field: TemplateSourceField, record?: Record<string, unknown>, recordIndex?: number): ReportTreeNode {
    const binding = options.bindings.value.find(
      (item) => item.field_code === field.bindingCode,
    )
    const recordValue = record ? nestedValue(record, field.sourcePath) : undefined
    const values = record
      ? (recordValue === undefined || recordValue === null ? [] : [recordValue])
      : payloadValues(field.sourcePath)
    const value = values.length
      ? [...new Set(values.map((item) => typeof item === 'object' ? JSON.stringify(item) : String(item)))].join('；')
      : record ? '' : binding?.current_value || ''
    const sourceType = record ? undefined
      : binding?.source.type === 'LIMS' || binding?.source.type === 'PDF' ? binding.source.type
        : values.length && field.sourceType === 'LIMS' ? 'LIMS' : undefined
    return {
      id: `template-field-${field.id}${recordIndex === undefined ? '' : `-${recordIndex}`}`,
      label: field.wordLabel,
      value,
      bindingCode: binding?.field_code,
      sourceType,
      controlTag: field.controlTag,
      recordIndex,
    }
  }

  function recordTitle(record: Record<string, unknown>, index: number) {
    const keys = ['sampleName', 'sampleNumber', 'name', 'instrumentName', 'assetNo', 'serialNo', 'impurityName', 'solutionName', 'field1', 'sequence']
    const values = keys.map((key) => record[key]).filter((value) => value !== undefined && value !== null && value !== '')
    return values.slice(0, 2).map(String).join(' · ') || `数据 ${index + 1}`
  }

  function chapterFields(chapter: TemplateSourceChapter) {
    const repeatGroups = new Map<string, TemplateSourceField[]>()
    const direct: TemplateSourceField[] = []
    for (const field of chapter.fields) {
      const match = field.sourcePath.match(/^\$\.([^.[]+)\[\*]\./)
      if (!match) direct.push(field)
      else repeatGroups.set(match[1], [...(repeatGroups.get(match[1]) || []), field])
    }
    const nodes = direct.map((field) => fieldNode(field))
    for (const [collection, fields] of repeatGroups) {
      const source = payload()[collection]
      const records = Array.isArray(source) ? source as Record<string, unknown>[] : []
      if (!records.length) {
        nodes.push(...fields.map((field) => fieldNode(field)))
        continue
      }
      records.forEach((record, index) => {
        nodes.push({
          id: `template-record-${chapter.id}-${collection}-${index}`,
          label: recordTitle(record, index),
          sourceType: 'LIMS',
          controlTag: fields.find((field) => field.controlTag)?.controlTag,
          recordIndex: index,
          children: fields.map((field) => fieldNode(field, record, index)),
        })
      })
    }
    return nodes
  }

  const chapterTreeData = computed<ReportTreeNode[]>(() => {
    const query = options.search.value.trim().toLowerCase()
    const firstLocation = (nodes: ReportTreeNode[]): { tag: string; index: number } | undefined => {
      for (const node of nodes) {
        if (node.controlTag) return { tag: node.controlTag, index: node.recordIndex || 0 }
        const nested = firstLocation(node.children || [])
        if (nested) return nested
      }
      return undefined
    }
    const build = (chapter: TemplateSourceChapter): ReportTreeNode | undefined => {
      const chapters = chapter.children.map(build).filter(Boolean) as ReportTreeNode[]
      const fields = chapterFields(chapter).filter((node) => !query
        || `${chapter.code} ${chapter.title} ${node.label} ${node.value || ''} ${(node.children || []).map((item) => `${item.label} ${item.value}`).join(' ')}`.toLowerCase().includes(query))
      const children = [...chapters, ...fields]
      if (query && !children.length) return undefined
      const location = firstLocation(children)
      return {
        id: `report-chapter-${chapter.id}`,
        label: `${chapter.code} ${chapter.title}`,
        children,
        controlTag: location?.tag,
        recordIndex: location?.index,
      }
    }
    return options.catalog.value.chapters.map(build).filter(Boolean) as ReportTreeNode[]
  })

  return { chapterTreeData }
}
