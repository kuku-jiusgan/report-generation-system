<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type StandardFieldCatalogChapter, type SystemFieldGroup } from './admin-api'

const props = defineProps<{
  field: { fieldCode?: string; label?: string }
  chapters: StandardFieldCatalogChapter[]
  groups: SystemFieldGroup[]
  errorText: (error: unknown) => string
}>()
const emit = defineEmits<{ moved: [fieldCode: string] }>()

type TargetKind = 'chapter' | 'group'
const dialogOpen = ref(false)
const saving = ref(false)
const targetKind = ref<TargetKind>('chapter')
const targetChapterId = ref<number>()
const targetGroupCode = ref('')

const chapterOptions = computed(() => {
  const options: Array<{ id: number; label: string }> = []
  function append(items: StandardFieldCatalogChapter[], depth = 0) {
    for (const chapter of items) {
      options.push({ id: chapter.id, label: `${'　'.repeat(depth)}${chapter.code} ${chapter.title}` })
      append(chapter.children, depth + 1)
    }
  }
  append(props.chapters)
  return options
})

function open() {
  targetKind.value = 'chapter'
  targetChapterId.value = undefined
  targetGroupCode.value = ''
  dialogOpen.value = true
}

async function move() {
  const fieldCode = props.field.fieldCode
  if (!fieldCode) return
  if (targetKind.value === 'chapter' && !targetChapterId.value) {
    return ElMessage.warning('请选择目标章节')
  }
  if (targetKind.value === 'group' && !targetGroupCode.value) {
    return ElMessage.warning('请选择目标编组')
  }
  saving.value = true
  try {
    await adminApi.moveStandardFieldOwnership(
      fieldCode,
      targetKind.value === 'chapter'
        ? { chapterId: targetChapterId.value! }
        : { groupCode: targetGroupCode.value },
    )
    dialogOpen.value = false
    emit('moved', fieldCode)
    ElMessage.success('字段归属已移动')
  } catch (error) {
    ElMessage.error(props.errorText(error))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-button plain @click="open">移动归属</el-button>
  <el-dialog v-model="dialogOpen" title="移动字段归属" width="460px" append-to-body>
    <p class="ownership-summary">将“{{ field.label || field.fieldCode }}”移动到：</p>
    <el-radio-group v-model="targetKind" class="ownership-kind">
      <el-radio value="chapter">章节下</el-radio>
      <el-radio value="group">其他编组</el-radio>
    </el-radio-group>
    <el-select v-if="targetKind === 'chapter'" v-model="targetChapterId" class="ownership-select" filterable placeholder="选择目标章节">
      <el-option v-for="chapter in chapterOptions" :key="chapter.id" :label="chapter.label" :value="chapter.id" />
    </el-select>
    <el-select v-else v-model="targetGroupCode" class="ownership-select" filterable placeholder="选择目标编组">
      <el-option v-for="group in groups" :key="group.groupCode" :label="`${group.label} · ${group.groupCode}`" :value="group.groupCode" />
    </el-select>
    <p class="ownership-hint">移动会替换原有目录归属；模板引用、标准数据路径和提取规则不会改变。</p>
    <template #footer>
      <el-button @click="dialogOpen = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="move">确认移动</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ownership-summary{margin:0 0 14px;color:#30483f;font-size:13px}.ownership-kind{margin-bottom:14px}.ownership-select{width:100%}.ownership-hint{margin:10px 0 0;color:#71817b;font-size:11px;line-height:1.6}
</style>
