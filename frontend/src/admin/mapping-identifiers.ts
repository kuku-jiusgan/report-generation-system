import type {
  DesignerBlock, DesignerChapter, MappingRule, StandardField,
} from '../admin-api'

interface MappingContext {
  chapters: DesignerChapter[]
  selectedChapter?: DesignerChapter
  selectedBlock?: DesignerBlock
}

function identifierSegment(value: string, fallback: string, maxLength = 48) {
  const normalized = value
    .normalize('NFKC')
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '_')
    .replace(/^_+|_+$/g, '')
  return (normalized || fallback).slice(0, maxLength)
}

function isTemporaryIdentifier(value?: string) {
  const current = (value || '').trim()
  return !current
    || /^\d+$/.test(current)
    || current.startsWith('draft.')
    || /^(?:word\.)?contentcontrol\.\d+$/i.test(current)
    || /^report\..+\.mapping\.\d+$/.test(current)
}

export function resolveMappingContext(mapping: Partial<MappingRule>, context: MappingContext) {
  const chapter = context.chapters.find((item) => item.id === mapping.chapterId)
    || context.chapters.find((item) => item.code === mapping.sectionCode)
    || context.selectedChapter
  const block = chapter?.blocks.find((item) => item.id === mapping.blockId)
    || chapter?.blocks.find((item) => item.mappings.some((field) => field.id === mapping.id))
    || context.selectedBlock
  return { chapter, block }
}

export function mappingIdentifiers(mapping: Partial<MappingRule>, context: MappingContext) {
  const { chapter, block } = resolveMappingContext(mapping, context)
  const rawSection = mapping.sectionCode || chapter?.code || 'field'
  const section = ['cover', 'headerFooter'].includes(rawSection)
    ? identifierSegment(rawSection, 'field')
    : `s${identifierSegment(rawSection, 'field')}`
  const field = identifierSegment(mapping.wordLabel || '', `field_${mapping.id || 'new'}`)
  const blockName = identifierSegment(block?.title || '', '')
  const parts = ['report', section]
  if (blockName && blockName !== field) parts.push(blockName)
  parts.push(field)

  let generatedFieldCode = parts.join('.')
  const allMappings = context.chapters
    .flatMap((item) => item.blocks)
    .flatMap((item) => item.mappings)
    .filter((item) => item.id !== mapping.id)
  if (allMappings.some((item) => item.fieldCode === generatedFieldCode)) {
    generatedFieldCode += `.m${mapping.id || Date.now()}`
  }
  const fieldCode = isTemporaryIdentifier(mapping.fieldCode)
    ? generatedFieldCode : String(mapping.fieldCode)
  let generatedTag = `cc.${fieldCode}`
  if (allMappings.some((item) => item.controlTag === generatedTag)) {
    generatedTag += `.m${mapping.id || Date.now()}`
  }
  const controlTag = isTemporaryIdentifier(mapping.controlTag)
    ? generatedTag : String(mapping.controlTag)
  const currentLocation = String(mapping.locationId || '')
  const locationId = isTemporaryIdentifier(currentLocation)
    ? `word.content_control.${controlTag}` : currentLocation
  return { fieldCode, controlTag, locationId }
}

export function mappingDisplayName(
  mapping: Partial<MappingRule>, context: MappingContext, standardFields: StandardField[],
) {
  const current = String(mapping.wordLabel || '').trim()
  if (current && current !== '新字段') return current
  const standard = standardFields.find((item) => item.fieldCode === mapping.standardFieldCode)
  if (standard?.label) return standard.label
  const { block } = resolveMappingContext(mapping, context)
  return block?.title ? `${block.title}字段` : '未命名字段'
}
