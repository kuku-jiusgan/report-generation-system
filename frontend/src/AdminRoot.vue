<script setup lang="ts">
import AdminHub from './AdminHub.vue'
import AuthGate from './AuthGate.vue'
</script>

<template>
  <AuthGate v-slot="{ user, logout }" title="报告自动生成系统后台管理" subtitle="系统配置、用户权限与报告生成历史" required-permission="ADMIN_ACCESS" portal="admin">
    <AdminHub :permissions="user.permissions" :user="user" @logout="logout" />
  </AuthGate>
</template>
