<script setup lang="ts">
import App from './App.vue'
import AuthGate from './AuthGate.vue'
</script>

<template>
  <AuthGate v-slot="{ user, logout }" title="报告生成工作台" subtitle="登录后创建、编辑和生成实验报告" required-permission="REPORT_EDIT" portal="report">
    <App :session-user="user" @logout="logout" />
  </AuthGate>
</template>
