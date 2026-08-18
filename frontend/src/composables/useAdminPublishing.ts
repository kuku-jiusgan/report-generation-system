import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminApi, type DataSourceRule, type LimsImport, type LimsRecognitionTest,
  type RuleVersion, type ValidationReport,
} from '../admin-api'
import { adminErrorText } from '../admin/designer-formatters'

interface PublishingOptions {
  sources: Ref<DataSourceRule[]>
  versions: Ref<RuleVersion[]>
  limsImports: Ref<LimsImport[]>
  reloadDesigner: () => Promise<void>
}

export function useAdminPublishing(options: PublishingOptions) {
  const sourceDialog = ref(false)
  const sourceDraft = ref<DataSourceRule>()
  const sourceConfigText = ref('{}')
  const validation = ref<ValidationReport>()
  const validationDialog = ref(false)
  const validating = ref(false)
  const publishing = ref(false)
  const recognitionDialog = ref(false)
  const recognitionResultDialog = ref(false)
  const recognitionImport = ref<LimsImport>()
  const recognitionIds = ref<string[]>([])
  const recognitionTesting = ref(false)
  const recognitionResult = ref<LimsRecognitionTest>()

  function editSource(item: DataSourceRule) {
    sourceDraft.value = JSON.parse(JSON.stringify(item))
    sourceConfigText.value = JSON.stringify(item.config, null, 2)
    sourceDialog.value = true
  }

  async function saveSource() {
    if (!sourceDraft.value) return
    try {
      sourceDraft.value.config = JSON.parse(sourceConfigText.value)
      await adminApi.updateSource(sourceDraft.value.code, sourceDraft.value)
      options.sources.value = await adminApi.sources()
      sourceDialog.value = false
      ElMessage.success('数据源配置已保存')
    } catch (error) {
      ElMessage.error(error instanceof SyntaxError ? '配置必须是有效 JSON' : adminErrorText(error))
    }
  }

  async function validateRules() {
    validating.value = true
    try {
      validation.value = await adminApi.validate()
      validationDialog.value = true
    } catch (error) {
      ElMessage.error(adminErrorText(error))
    } finally {
      validating.value = false
    }
  }

  async function publishRules() {
    try {
      const result = await ElMessageBox.prompt('请输入本次模板规则版本说明', '发布模板版本', {
        inputValue: '更新模板章节与字段规则',
        inputValidator: (value) => !!value || '请输入发布说明',
      })
      publishing.value = true
      const version = await adminApi.publish(result.value)
      options.versions.value = await adminApi.versions()
      await options.reloadDesigner()
      ElMessage.success(`模板规则 V${version.versionNo} 已发布`)
    } catch (error) {
      if (error !== 'cancel' && error !== 'close') ElMessage.error(adminErrorText(error))
    } finally {
      publishing.value = false
    }
  }

  function openRecognition() {
    recognitionImport.value = options.limsImports.value[0]
    recognitionIds.value = []
    recognitionDialog.value = true
  }

  async function runRecognition() {
    if (!recognitionImport.value || !recognitionIds.value.length) return
    recognitionTesting.value = true
    try {
      recognitionResult.value = await adminApi.limsRecognition(
        recognitionImport.value.id, recognitionIds.value,
      )
      recognitionDialog.value = false
      recognitionResultDialog.value = true
    } catch (error) {
      ElMessage.error(adminErrorText(error))
    } finally {
      recognitionTesting.value = false
    }
  }

  return {
    sourceDialog, sourceDraft, sourceConfigText,
    validation, validationDialog, validating, publishing,
    recognitionDialog, recognitionResultDialog, recognitionImport, recognitionIds,
    recognitionTesting, recognitionResult,
    editSource, saveSource, validateRules, publishRules, openRecognition, runRecognition,
  }
}
