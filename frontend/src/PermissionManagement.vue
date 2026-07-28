<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi, type RoleMatrix } from './admin-api'
const matrix=ref<RoleMatrix>();const active=ref('SYSTEM_ADMIN');const selected=ref<string[]>([]);const loading=ref(false)
function select(code:string){active.value=code;selected.value=[...(matrix.value?.roles.find(r=>r.code===code)?.permissions||[])]}
async function load(){matrix.value=await adminApi.roles();select(matrix.value.roles.find(r=>r.code==='SYSTEM_ADMIN')?.code||matrix.value.roles[0].code)}
async function save(){loading.value=true;try{await adminApi.updateRolePermissions(active.value,selected.value);ElMessage.success('权限已更新，相关用户需要重新登录');await load()}catch(e){ElMessage.error((e as {response?:{data?:{detail?:string}}}).response?.data?.detail||'保存失败')}finally{loading.value=false}}
onMounted(load)
</script>
<template><section class="management-page"><header><div><h1>权限管理</h1><p>配置系统管理员与报告用户的功能权限</p></div><el-button type="primary" :loading="loading" :disabled="active==='SUPER_ADMIN'" @click="save">保存权限</el-button></header><div v-if="matrix" class="permission-layout"><aside><button v-for="role in matrix.roles" :key="role.code" :class="{active:active===role.code}" @click="select(role.code)"><strong>{{role.name}}</strong><small>{{role.description}}</small></button></aside><article><el-alert v-if="active==='SUPER_ADMIN'" title="超级管理员核心权限不可修改" type="info" :closable="false"/><el-checkbox-group v-model="selected" :disabled="active==='SUPER_ADMIN'"><el-checkbox v-for="permission in matrix.permissions" :key="permission.code" :value="permission.code"><span>{{permission.name}}</span><small>{{permission.code}}</small></el-checkbox></el-checkbox-group></article></div></section></template>
