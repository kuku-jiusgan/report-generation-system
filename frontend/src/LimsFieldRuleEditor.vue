<script setup lang="ts">
import { computed } from 'vue'
import type { LimsRuleInputGroup, LimsRuleMetadata } from './admin-api'

const config = defineModel<Record<string, unknown>>({ required: true })
const props = defineProps<{ metadata: LimsRuleMetadata; transform: string }>()
const extractionType = computed(() => String(config.value.extractionType || ''))
const definition = computed(() => props.metadata.extractionTypes.find(item => item.value === extractionType.value))

function conditionMatches(group: LimsRuleInputGroup) {
  if (!group.when) return true
  const value = group.when.key === 'transform' ? props.transform : config.value[group.when.key]
  return value === group.when.value
}
function changeExtractionType(value: string) {
  const target = props.metadata.extractionTypes.find(item => item.value === value)
  if (!target) return
  const transformKeys = props.metadata.transformGroups.flatMap(group => group.fields.map(field => field.key))
  const retained = Object.fromEntries(
    transformKeys.filter(key => key in config.value).map(key => [key, config.value[key]]),
  )
  config.value = { ...target.defaultConfig, ...retained }
}
function valueFor(key: string) {
  return config.value[key]
}
function numberFor(key: string) {
  const value = valueFor(key)
  return typeof value === 'number' ? value : undefined
}
function tagsFor(key: string) {
  const value = valueFor(key)
  return Array.isArray(value) ? value.map(String) : []
}
function setValue(key: string, value: unknown) {
  config.value[key] = value
}
function optionValue(option: string | { value: string; label: string }) {
  return typeof option === 'string' ? option : option.value
}
function optionLabel(option: string | { value: string; label: string }) {
  return typeof option === 'string' ? option : option.label
}
</script>

<template>
  <el-form-item label="LIMS 提取方式">
    <el-select :model-value="extractionType" @update:model-value="changeExtractionType">
      <el-option v-for="item in metadata.extractionTypes" :key="item.value" :label="item.label" :value="item.value" />
    </el-select>
  </el-form-item>

  <template v-for="(group, groupIndex) in definition?.groups || []" :key="groupIndex">
    <div v-if="conditionMatches(group)" class="metadata-grid" :class="`columns-${group.columns}`">
      <el-form-item v-for="input in group.fields" :key="input.key" :label="input.label">
        <el-input-number v-if="input.kind === 'integer'" :model-value="numberFor(input.key)" :min="input.min" controls-position="right" @update:model-value="setValue(input.key, $event)" />
        <el-select v-else-if="input.kind === 'select'" :model-value="valueFor(input.key)" filterable :allow-create="input.allowCustom" :default-first-option="input.allowCustom" @update:model-value="setValue(input.key, $event)">
          <el-option v-for="option in input.options || []" :key="optionValue(option)" :label="optionLabel(option)" :value="optionValue(option)" />
        </el-select>
        <el-select v-else-if="input.kind === 'tags'" :model-value="tagsFor(input.key)" multiple filterable allow-create default-first-option @update:model-value="setValue(input.key, $event)" />
        <el-input v-else :model-value="String(valueFor(input.key) ?? '')" :type="input.kind === 'textarea' ? 'textarea' : 'text'" :rows="input.rows" :placeholder="input.placeholder" @update:model-value="setValue(input.key, $event)" />
      </el-form-item>
    </div>
  </template>

  <template v-for="(group, groupIndex) in metadata.transformGroups" :key="`transform-${groupIndex}`">
    <div v-if="conditionMatches(group)" class="metadata-grid transform-grid" :class="`columns-${group.columns}`">
      <el-form-item v-for="input in group.fields" :key="input.key" :label="input.label">
        <el-input :model-value="String(valueFor(input.key) ?? '')" :type="input.kind === 'textarea' ? 'textarea' : 'text'" :rows="input.rows" :placeholder="input.placeholder" @update:model-value="setValue(input.key, $event)" />
      </el-form-item>
    </div>
  </template>
</template>

<style scoped>
.metadata-grid{display:grid;gap:16px}.columns-1{grid-template-columns:1fr}.columns-2{grid-template-columns:repeat(2,minmax(0,1fr))}.columns-3{grid-template-columns:repeat(3,minmax(0,1fr))}.columns-4{grid-template-columns:repeat(4,minmax(0,1fr))}.transform-grid{padding:10px 12px 0;background:#f7f9fc;margin-bottom:14px}.el-select,.el-input-number{width:100%}@media(max-width:720px){.columns-2,.columns-3,.columns-4{grid-template-columns:1fr}}
</style>
