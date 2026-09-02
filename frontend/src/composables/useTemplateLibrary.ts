import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type AdminTemplate, type AdminTemplateVersion } from '../admin-api'

export const templateVersionStatusText: Record<string, string> = {
  DRAFT: '草稿', PUBLISHED: '已发布', ARCHIVED: '历史版本',
}

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } }; message?: string }
  return value.response?.data?.detail || value.message || '操作失败'
}

export function useTemplateLibrary(
  openDesigner: (template: AdminTemplate, version: AdminTemplateVersion) => void,
) {
  const templates = ref<AdminTemplate[]>([])
  const versions = ref<AdminTemplateVersion[]>([])
  const selected = ref<AdminTemplate>()
  const editingTemplate = ref<AdminTemplate>()
  const loading = ref(false)
  const versionLoading = ref(false)
  const deletingTemplate = ref(false)
  const deletingVersionId = ref<string>()
  const savingTemplate = ref(false)
  const savingVersion = ref(false)
  const activatingVersionId = ref<string>()
  const templateDialog = ref(false)
  const versionDialog = ref(false)
  const templateDraft = reactive({ code: '', name: '', description: '' })
  const templateFile = ref<File>()
  const versionDraft = reactive<{ baseVersionId?: string; note: string }>({ note: '' })
  const selectedTitle = computed(() => selected.value
    ? `${selected.value.name} · ${selected.value.code}` : '选择一个模板')

  async function selectTemplate(item: AdminTemplate) {
    selected.value = item
    versionLoading.value = true
    try {
      versions.value = await adminApi.templateVersions(item.id)
    } catch (error) {
      console.error('[模板库] 加载模板版本失败', { templateId: item.id, error })
      ElMessage.error(errorText(error))
    } finally {
      versionLoading.value = false
    }
  }

  async function loadTemplates(preferredId?: string) {
    loading.value = true
    try {
      templates.value = await adminApi.templates()
      const target = templates.value.find(
        (item) => item.id === (preferredId || selected.value?.id),
      ) || templates.value[0]
      if (target) await selectTemplate(target)
    } catch (error) {
      console.error('[模板库] 加载模板列表失败', error)
      ElMessage.error(errorText(error))
    } finally {
      loading.value = false
    }
  }

  function openCreateTemplate() {
    editingTemplate.value = undefined
    Object.assign(templateDraft, { code: '', name: '', description: '' })
    templateFile.value = undefined
    templateDialog.value = true
  }

  function openEditTemplate() {
    if (!selected.value) return
    editingTemplate.value = selected.value
    Object.assign(templateDraft, {
      code: selected.value.code,
      name: selected.value.name,
      description: selected.value.description,
    })
    templateDialog.value = true
  }

  async function saveTemplate() {
    if (!templateDraft.code.trim() || !templateDraft.name.trim()) {
      ElMessage.warning('模板编码和名称不能为空')
      return
    }
    if (!editingTemplate.value && !templateFile.value) {
      ElMessage.warning('请选择 Word 模板基座文件')
      return
    }
    savingTemplate.value = true
    try {
      const result = editingTemplate.value
        ? await adminApi.updateTemplate(editingTemplate.value.id, templateDraft)
        : await adminApi.createTemplateWithFile({ ...templateDraft, note: '初始草稿版本', templateFile: templateFile.value as File })
      templateDialog.value = false
      await loadTemplates(result.id)
      ElMessage.success(editingTemplate.value ? '模板信息已保存' : '模板及 V1 已创建')
    } catch (error) {
      console.error('[模板库] 保存模板失败', error)
      ElMessage.error(errorText(error))
    } finally {
      savingTemplate.value = false
    }
  }

  async function removeTemplate() {
    if (!selected.value) return
    const target = selected.value
    try {
      await ElMessageBox.confirm(
        `删除模板“${target.name}（${target.code}）”？该模板的 ${target.versionCount} 个版本和独立 Word 文件也会一并删除，此操作不可恢复。`,
        '删除报告模板',
        { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
      )
      deletingTemplate.value = true
      await adminApi.deleteTemplate(target.id)
      selected.value = undefined
      versions.value = []
      await loadTemplates()
      ElMessage.success('模板已删除')
    } catch (error) {
      if (error === 'cancel' || error === 'close') return
      console.error('[模板库] 删除模板失败', { templateId: target.id, error })
      ElMessage.error(errorText(error))
    } finally {
      deletingTemplate.value = false
    }
  }

  function openCreateVersion(base?: AdminTemplateVersion) {
    versionDraft.baseVersionId = base?.id || versions.value[0]?.id
    versionDraft.note = base ? `基于 V${base.versionNo} 创建` : '新建草稿版本'
    versionDialog.value = true
  }

  async function saveVersion() {
    if (!selected.value) return
    savingVersion.value = true
    try {
      await adminApi.createTemplateVersion(selected.value.id, versionDraft)
      versionDialog.value = false
      await loadTemplates(selected.value.id)
      ElMessage.success('新版本已创建')
    } catch (error) {
      console.error('[模板库] 创建模板版本失败', { templateId: selected.value.id, error })
      ElMessage.error(errorText(error))
    } finally {
      savingVersion.value = false
    }
  }

  async function removeVersion(version: AdminTemplateVersion) {
    if (!selected.value) return
    try {
      await ElMessageBox.confirm(
        `删除版本 V${version.versionNo}？该版本对应的 Word 草稿文件也会一并删除，此操作不可恢复。`,
        '删除模板版本',
        { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
      )
      deletingVersionId.value = version.id
      await adminApi.deleteTemplateVersion(selected.value.id, version.id)
      await loadTemplates(selected.value.id)
      ElMessage.success(`版本 V${version.versionNo} 已删除`)
    } catch (error) {
      if (error === 'cancel' || error === 'close') return
      console.error('[模板库] 删除模板版本失败', { versionId: version.id, error })
      ElMessage.error(errorText(error))
    } finally {
      deletingVersionId.value = undefined
    }
  }

  async function enterDesigner(version: AdminTemplateVersion) {
    if (!selected.value) return
    activatingVersionId.value = version.id
    try {
      await adminApi.activateTemplateVersion(selected.value.id, version.id)
      openDesigner(selected.value, version)
    } catch (error) {
      console.error('[模板库] 激活模板版本失败', { versionId: version.id, error })
      ElMessage.error(errorText(error))
    } finally {
      activatingVersionId.value = undefined
    }
  }

  onMounted(loadTemplates)
  return {
    templates, versions, selected, editingTemplate, loading, versionLoading,
    deletingTemplate, deletingVersionId, savingTemplate, savingVersion, activatingVersionId,
    templateDialog, versionDialog, templateDraft, templateFile, versionDraft, selectedTitle,
    loadTemplates, selectTemplate, openCreateTemplate, openEditTemplate,
    saveTemplate, removeTemplate, openCreateVersion, saveVersion, removeVersion, enterDesigner,
  }
}
