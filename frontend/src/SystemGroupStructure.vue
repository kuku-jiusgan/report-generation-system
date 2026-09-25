<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { adminApi, type SystemFieldGroup, type SystemFieldGroupLevel } from './admin-api'

/** 编组的数组结构编辑器：记录顶层 + 用户自定义的对象层/数组层，下方实时预览生成的结构。
 *  措辞一律用数据结构的通用名词（记录/对象/数组），不掺具体业务表的叫法。 */
const props = defineProps<{ group: SystemFieldGroup; errorText: (error: unknown) => string }>()
const emit = defineEmits<{ saved: [group: SystemFieldGroup] }>()

type LevelDraft = SystemFieldGroupLevel & { originalKey: string }
const canonicalLevels: SystemFieldGroupLevel[] = [
  { levelKey: 'summary', label: '汇总', kind: 'OBJECT', orderNo: 0 },
  { levelKey: 'injections', label: '进样明细', kind: 'ARRAY', orderNo: 1 },
]
const levelDraft = ref<LevelDraft>()
const dialogOpen = computed({
  get: () => !!levelDraft.value,
  set: (open: boolean) => { if (!open) levelDraft.value = undefined },
})
function fieldsOfLevel(levelKey: string) {
  return props.group.fields.filter((field) => (field.levelKey || '') === levelKey)
}
function fieldCodesOfLevel(levelKey: string) {
  return fieldsOfLevel(levelKey).map((field) => field.fieldCode)
}
/** 一个字段只能属于一层：这一层新选中的字段从原来的层移过来，取消勾选的退回记录顶层。 */
async function setLevelFields(levelKey: string, selected: string[]) {
  const before = fieldCodesOfLevel(levelKey)
  const moves: Array<[string, string]> = [
    ...selected.filter((code) => !before.includes(code)).map((code) => [code, levelKey] as [string, string]),
    // 记录顶层是兜底层，字段从别处移走才算离开，不能在顶层直接取消勾选
    ...(levelKey ? before.filter((code) => !selected.includes(code)).map((code) => [code, ''] as [string, string]) : []),
  ]
  if (!moves.length) return
  try {
    let saved: SystemFieldGroup | undefined
    for (const [fieldCode, target] of moves) {
      saved = await adminApi.moveGroupFieldLevel(props.group.groupCode, fieldCode, target)
    }
    if (saved) emit('saved', saved)
    ElMessage.success(`已调整 ${moves.length} 个字段的归属`)
  } catch (error) { ElMessage.error(props.errorText(error)) }
}
function editLevel(level?: SystemFieldGroupLevel) {
  levelDraft.value = level
    ? { ...level, originalKey: level.levelKey }
    : { levelKey: '', label: '', kind: 'ARRAY', parentLevelKey: '', orderNo: props.group.levels.length, originalKey: '' }
}
function selectCanonicalLevel(levelKey: string) {
  const selected = canonicalLevels.find((item) => item.levelKey === levelKey)
  if (selected && levelDraft.value) Object.assign(levelDraft.value, selected)
}
function levelOptionDisabled(levelKey: string) {
  return props.group.levels.some((item) => item.levelKey === levelKey && item.levelKey !== levelDraft.value?.originalKey)
}
function isCanonicalLevel(levelKey?: string) {
  return canonicalLevels.some((item) => item.levelKey === levelKey)
}
async function apply(action: Promise<SystemFieldGroup>, message: string) {
  try {
    emit('saved', await action)
    ElMessage.success(message)
  } catch (error) { ElMessage.error(props.errorText(error)) }
}
async function saveLevel() {
  const draft = levelDraft.value
  if (!draft?.levelKey.trim()) return ElMessage.warning('层的键名不能为空')
  try {
    emit('saved', await adminApi.saveGroupLevel(props.group.groupCode, draft))
    ElMessage.success('层已保存')
    levelDraft.value = undefined
  } catch (error) { ElMessage.error(props.errorText(error)) }
}
async function removeLevel(levelKey: string) {
  try {
    await ElMessageBox.confirm(`删除层“${levelKey}”？层里的字段会回到记录顶层，字段本身不会被删除。`,
      '删除层', { type: 'warning' })
  } catch { return }
  await apply(adminApi.deleteGroupLevel(props.group.groupCode, levelKey), '层已删除')
}
</script>

<template>
  <div class="group-structure">
    <div class="structure-head">
      <span>数组结构</span>
      <el-button text type="primary" :icon="Plus" @click="editLevel()">添加下一层</el-button>
    </div>
    <small class="structure-hint">
      编组的基数是「多条」时提取出来就是一个数组，这里描述的是数组里<b>一条记录</b>长什么样：
      字段留在记录顶层，就是每条记录一个取值；放进对象层，会包成记录下的一个子对象；
      放进数组层，会变成记录下的一个子数组，一条记录可以有多条。父层可以继续包含子层。
    </small>

    <div class="structure-level">
      <div class="structure-level-head"><b>记录顶层</b><code>每条记录一个取值</code></div>
      <el-select class="structure-picker" :model-value="fieldCodesOfLevel('')" multiple filterable
        collapse-tags collapse-tags-tooltip placeholder="选择放在记录顶层的字段"
        @update:model-value="setLevelFields('', $event)">
        <el-option v-for="field in group.fields" :key="field.fieldCode"
          :label="`${field.label} · ${field.jsonKey}`" :value="field.fieldCode" />
      </el-select>
      <div v-for="field in fieldsOfLevel('')" :key="field.fieldCode" class="structure-field">
        <b>{{ field.label }}</b><code>{{ field.fieldPath }}</code>
      </div>
      <p v-if="!fieldsOfLevel('').length" class="structure-empty">该层暂无字段</p>
    </div>

    <div v-for="level in group.levels" :key="level.levelKey" class="structure-level">
      <div class="structure-level-head">
        <b>{{ level.label || level.levelKey }}</b>
        <code>{{ level.parentLevelKey ? `${level.parentLevelKey} / ` : '' }}{{ level.levelKey }} · {{ level.kind === 'ARRAY' ? '数组层·每条记录多条' : '对象层·每条记录一份' }}</code>
        <div class="structure-level-actions">
          <el-button text size="small" :icon="EditPen" @click="editLevel(level)">编辑</el-button>
          <el-button text size="small" type="danger" :icon="Delete" @click="removeLevel(level.levelKey)">删除</el-button>
        </div>
      </div>
      <el-select class="structure-picker" :model-value="fieldCodesOfLevel(level.levelKey)" multiple filterable
        collapse-tags collapse-tags-tooltip :placeholder="`选择放在「${level.label || level.levelKey}」的字段`"
        @update:model-value="setLevelFields(level.levelKey, $event)">
        <el-option v-for="field in group.fields" :key="field.fieldCode"
          :label="`${field.label} · ${field.jsonKey}`" :value="field.fieldCode" />
      </el-select>
      <div v-for="field in fieldsOfLevel(level.levelKey)" :key="field.fieldCode" class="structure-field">
        <b>{{ field.label }}</b><code>{{ field.fieldPath }}</code>
      </div>
      <p v-if="!fieldsOfLevel(level.levelKey).length" class="structure-empty">该层暂无字段</p>
    </div>

    <div v-if="group.structurePreview" class="structure-preview">
      <b>按当前配置生成的数组结构（一条记录）</b>
      <pre>{{ JSON.stringify([group.structurePreview], null, 2) }}</pre>
    </div>

    <el-dialog v-model="dialogOpen" title="编组的层" width="460px">
      <el-form v-if="levelDraft" label-position="top">
        <el-form-item label="键名（生成的 JSON 里的属性名）">
          <el-input v-if="!isCanonicalLevel(levelDraft?.levelKey)"
            v-model="levelDraft.levelKey" :disabled="!!levelDraft.originalKey" placeholder="例如 technicians" />
          <el-select v-else :model-value="levelDraft.levelKey" :disabled="!!levelDraft.originalKey"
            @update:model-value="selectCanonicalLevel">
            <el-option v-for="level in canonicalLevels" :key="level.levelKey"
              :label="`${level.label}（${level.levelKey}）`" :value="level.levelKey"
              :disabled="levelOptionDisabled(level.levelKey)" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名"><el-input v-model="levelDraft.label" placeholder="例如 技术员编组" /></el-form-item>
        <el-form-item label="父层（可选）">
          <el-select v-model="levelDraft.parentLevelKey" clearable>
            <el-option v-for="parent in group.levels.filter(item => item.levelKey !== (levelDraft && levelDraft.levelKey))"
              :key="parent.levelKey" :label="parent.label || parent.levelKey" :value="parent.levelKey" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="levelDraft.kind">
            <el-option label="对象：记录下的一个子对象，每条记录一份" value="OBJECT" />
            <el-option label="数组：记录下的一个子数组，每条记录多条" value="ARRAY" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="levelDraft = undefined">取消</el-button>
        <el-button type="primary" @click="saveLevel">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.group-structure{margin-top:18px;padding:14px 16px;border:1px solid #e1e8e5;border-radius:8px;background:#f8fafb}
.structure-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;color:#30483f;font-size:12px;font-weight:650}
.structure-hint{display:block;margin-bottom:10px;color:#7b8a84;font-size:11px;line-height:1.6}
.structure-level{margin-bottom:10px;padding:8px 10px;border:1px solid #e6ece9;border-radius:6px;background:#fff}
.structure-level-head{display:flex;align-items:center;gap:10px;padding-bottom:6px;border-bottom:1px solid #eef2f0}
.structure-level-head b{color:#2d443b;font-size:12px}
.structure-level-head code{color:#7d918a;font:10px/1.3 Consolas,monospace}
.structure-level-actions{margin-left:auto;display:flex;gap:2px}
.structure-picker{width:100%;margin:8px 0 4px}
.structure-field{min-height:30px;display:grid;grid-template-columns:minmax(90px,1fr) minmax(140px,1.4fr);align-items:center;gap:10px;padding:4px 2px;border-top:1px solid #f2f6f4}
.structure-field b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#2d443b;font-size:12px;font-weight:550}
.structure-field code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#778a83;font:10px/1.3 Consolas,monospace}
.structure-empty{margin:8px 0 2px;color:#8a9993;font-size:11px;text-align:center}
.structure-preview{margin-top:10px;padding:10px 12px;border:1px solid #dbe5ee;border-radius:6px;background:#fff}
.structure-preview b{display:block;margin-bottom:6px;color:#2d443b;font-size:12px}
.structure-preview pre{margin:0;max-height:260px;overflow:auto;white-space:pre-wrap;color:#41564e;font:11px/1.6 Consolas,monospace}
</style>
