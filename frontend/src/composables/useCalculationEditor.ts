import type { Ref } from 'vue'
import type { DesignerBlock, MappingRule, StandardField } from '../admin-api'

export function useCalculationEditor(
  draft: Ref<Partial<MappingRule> | undefined>,
  selectedBlock: Ref<DesignerBlock | undefined>,
) {
  function onSourceTypeChange(sourceType: string) {
    if (!draft.value || sourceType !== 'CALCULATED') return
    draft.value.sourcePath = ''
    draft.value.standardFieldCode = undefined
    draft.value.dataType = 'decimal'
    draft.value.calculationExpression ||= ''
    draft.value.calculationDependencies ||= []
    draft.value.calculationScope ||= ['REPEATING_TABLE', 'MATRIX', 'TABLE_REPEAT'].includes(selectedBlock.value?.kind || '')
      ? 'CURRENT_ROW' : 'REPORT'
    draft.value.calculationPrecision ??= 2
    draft.value.calculationNullBehavior ||= 'ERROR'
  }

  function insertCalculationText(value: string) {
    if (!draft.value) return
    const expression = draft.value.calculationExpression || ''
    draft.value.calculationExpression = `${expression}${expression ? ' ' : ''}${value}`
  }

  function insertCalculationReference(code: string) {
    if (!draft.value) return
    const dependencies = draft.value.calculationDependencies || []
    if (!dependencies.includes(code)) draft.value.calculationDependencies = [...dependencies, code]
    insertCalculationText(`{${code}}`)
  }

  function insertCalculationFunction(name: string) {
    const snippets: Record<string, string> = {
      SUM: 'SUM()', AVG: 'AVG()', RSD: 'RSD()', MIN: 'MIN()', MAX: 'MAX()',
      COUNT: 'COUNT()', ABS: 'ABS()', SQRT: 'SQRT()', IF: 'IF(条件, "符合", "不符合")',
    }
    insertCalculationText(snippets[name])
  }

  function selectStandardField(field: StandardField) {
    if (!draft.value) return
    draft.value.standardFieldCode = field.fieldCode
    draft.value.sourceType = 'SYSTEM'
    draft.value.sourcePath = field.legacyJsonPath
    draft.value.dataType = field.dataType
    draft.value.calculationExpression = ''
    draft.value.calculationDependencies = []
  }

  return {
    onSourceTypeChange, insertCalculationText, insertCalculationReference,
    insertCalculationFunction, selectStandardField,
  }
}
