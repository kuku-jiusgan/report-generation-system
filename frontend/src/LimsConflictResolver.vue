<script setup lang="ts">
import type { LimsConflict } from './lims-api'

defineProps<{
  conflicts: LimsConflict[]
  resolutions: Record<string, string>
}>()

const emit = defineEmits<{
  resolve: [conflictId: string, candidateId: string]
}>()

function conflictValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '空'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}
</script>

<template>
  <div class="create-conflicts">
    <article v-for="conflict in conflicts" :key="conflict.id">
      <header class="conflict-heading">
        <strong>{{ conflict.label }} · {{ conflict.identity }}</strong>
        <span>{{ conflict.differingFields.length }} 个字段不同</span>
      </header>
      <p class="conflict-guidance">以下业务值不一致，请选择要用于报告的实验记录。</p>
      <el-radio-group
        :aria-label="`${conflict.label} ${conflict.identity} 冲突选项`"
        :model-value="resolutions[conflict.id]"
        @update:model-value="emit('resolve', conflict.id, String($event))"
      >
        <el-radio v-for="option in conflict.options" :key="option.candidateId" :value="option.candidateId" border>
          <span class="conflict-source">
            <strong>{{ option.evidence.instanceTitle || '未命名实验记录' }}</strong>
            <small>{{ option.evidence.instanceId || '记录编号未知' }}</small>
          </span>
          <dl class="conflict-values">
            <div v-for="field in conflict.differingFields" :key="field.key">
              <dt>{{ field.label }}</dt>
              <dd>{{ conflictValue(option.value[field.key]) }}</dd>
            </div>
          </dl>
        </el-radio>
      </el-radio-group>
    </article>
  </div>
</template>
