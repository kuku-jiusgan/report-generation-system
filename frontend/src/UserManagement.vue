<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { adminApi, type ManagedRole, type ManagedUser } from './admin-api'

const users = ref<ManagedUser[]>([]); const roles = ref<ManagedRole[]>([]); const query = ref(''); const loading = ref(false)
const dialog = ref(false); const editing = ref<ManagedUser>(); const form = reactive({ username:'', display_name:'', password:'', role_code:'REPORT_USER' })
const roleName = (code:string) => roles.value.find(item => item.code === code)?.name || code
const errorText = (e:unknown) => (e as {response?:{data?:{detail?:string}}}).response?.data?.detail || '操作失败'
async function load(){loading.value=true;try{[users.value, {roles:roles.value}] = await Promise.all([adminApi.users(query.value),adminApi.roles()])}catch(e){ElMessage.error(errorText(e))}finally{loading.value=false}}
function create(){editing.value=undefined;Object.assign(form,{username:'',display_name:'',password:'',role_code:'REPORT_USER'});dialog.value=true}
function edit(item:ManagedUser){editing.value=item;Object.assign(form,{username:item.username,display_name:item.displayName,password:'',role_code:item.roleCode});dialog.value=true}
async function save(){try{if(editing.value)await adminApi.updateUser(editing.value.id,{display_name:form.display_name,role_code:form.role_code});else await adminApi.createUser(form);dialog.value=false;ElMessage.success('用户已保存');await load()}catch(e){ElMessage.error(errorText(e))}}
async function toggle(item:ManagedUser){try{await adminApi.updateUser(item.id,{enabled:!item.enabled});await load()}catch(e){ElMessage.error(errorText(e))}}
async function reset(item:ManagedUser){try{const {value}=await ElMessageBox.prompt('输入新的临时密码（至少 8 位）','重置密码',{inputType:'password',inputPattern:/.{8,}/,inputErrorMessage:'密码至少 8 位'});await adminApi.resetUserPassword(item.id,value);ElMessage.success('密码已重置，用户下次登录必须修改')}catch(e){if(e!=='cancel')ElMessage.error(errorText(e))}}
onMounted(load)
</script>
<template>
  <section class="management-page">
    <header><div><h1>用户管理</h1><p>创建账号、分配角色并控制账号状态</p></div><el-button type="primary" :icon="Plus" @click="create">新建用户</el-button></header>
    <div class="management-toolbar"><el-input v-model="query" clearable placeholder="搜索用户名或姓名" :prefix-icon="Search" @keyup.enter="load"/><el-button :icon="Refresh" @click="load">刷新</el-button></div>
    <el-table :data="users" v-loading="loading" height="calc(100vh - 210px)"><el-table-column prop="username" label="用户名"/><el-table-column prop="displayName" label="姓名"/><el-table-column label="角色"><template #default="{row}">{{roleName(row.roleCode)}}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="row.enabled?'success':'info'">{{row.enabled?'启用':'停用'}}</el-tag></template></el-table-column><el-table-column prop="lastLoginAt" label="最后登录" width="190"/><el-table-column label="操作" width="260"><template #default="{row}"><el-button link @click="edit(row)">编辑</el-button><el-button link @click="reset(row)">重置密码</el-button><el-button link :type="row.enabled?'danger':'success'" @click="toggle(row)">{{row.enabled?'停用':'启用'}}</el-button></template></el-table-column></el-table>
    <el-dialog v-model="dialog" :title="editing?'编辑用户':'新建用户'" width="460"><el-form label-position="top"><el-form-item label="用户名"><el-input v-model="form.username" :disabled="!!editing"/></el-form-item><el-form-item label="姓名"><el-input v-model="form.display_name"/></el-form-item><el-form-item v-if="!editing" label="临时密码"><el-input v-model="form.password" type="password" show-password/></el-form-item><el-form-item label="角色"><el-select v-model="form.role_code"><el-option v-for="role in roles" :key="role.code" :label="role.name" :value="role.code"/></el-select></el-form-item></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template></el-dialog>
  </section>
</template>
