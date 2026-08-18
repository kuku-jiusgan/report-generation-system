<script setup lang="ts">
import { ref } from 'vue'
import App from './App.vue'
import AuthGate from './AuthGate.vue'
import ReportHub from './ReportHub.vue'

const activeReportId = ref<string>()
</script>

<template>
  <AuthGate v-slot="{ user, logout }" title="报告生成工作台" subtitle="登录后创建、编辑和生成实验报告" required-permission="REPORT_EDIT" portal="report">
    <ReportHub v-if="!activeReportId" :session-user="user" @open="activeReportId = $event" @logout="logout" />
    <App v-else :key="activeReportId" :session-user="user" :initial-report-id="activeReportId" @back="activeReportId = undefined" @logout="logout" />
  </AuthGate>
</template>
