<script setup lang="ts">
import { computed, ref } from 'vue'
import { Coin, Search } from '@element-plus/icons-vue'
import type { StandardField } from './admin-api'

const props = defineProps<{ modelValue?: string; fields: StandardField[] }>()
const emit = defineEmits<{ select: [field: StandardField] }>()
const visible = ref(false)
const search = ref('')
const selected = computed(() => props.fields.find((item) => item.fieldCode === props.modelValue))
const filtered = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return props.fields
  return props.fields.filter((item) => `${item.label} ${item.fieldCode} ${item.dbTable} ${item.dbColumn}`.toLowerCase().includes(keyword))
})

function choose(field: StandardField) {
  emit('select', field)
  visible.value = false
}
</script>

<template>
  <el-button
    class="standard-field-button"
    type="primary"
    plain
    :icon="Coin"
    @click="visible = true"
  >{{ selected ? '重新选择 LIMS 标准字段' : '选择 LIMS 标准字段' }}</el-button>

  <el-dialog v-model="visible" title="选择 LIMS 标准字段" width="820px" append-to-body>
    <el-input v-model="search" :prefix-icon="Search" placeholder="搜索业务名称、字段编码或数据库位置" clearable />
    <el-table :data="filtered" height="430" class="field-catalog-table" row-key="fieldCode" @row-dblclick="choose">
      <el-table-column prop="label" label="标准字段" min-width="170" />
      <el-table-column prop="fieldCode" label="字段编码" min-width="190"><template #default="scope"><code>{{ scope.row.fieldCode }}</code></template></el-table-column>
      <el-table-column label="数据库位置" min-width="250"><template #default="scope"><code>{{ scope.row.dbTable }}.{{ scope.row.dbColumn }}<template v-if="scope.row.jsonKey"> → {{ scope.row.jsonKey }}</template></code></template></el-table-column>
      <el-table-column label="关系" width="90"><template #default="scope"><el-tag size="small" effect="plain">{{ scope.row.cardinality === 'MANY' ? '一对多' : '单值' }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="90"><template #default="scope"><el-button type="primary" link @click="choose(scope.row)">选择</el-button></template></el-table-column>
    </el-table>
    <p class="catalog-help">Word 映射保存稳定的标准字段编码；数据库位置和旧 JSONPath 由系统维护。</p>
  </el-dialog>
</template>

<style scoped>
.standard-field-button{width:100%;margin:0 0 10px}.field-catalog-table{margin-top:14px}.field-catalog-table code{color:#31594e;font-size:11px}.catalog-help{margin:10px 0 0;color:#526860;font-size:10px}
</style>
