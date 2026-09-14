<script setup lang="ts">
import { APPLICATION_ACCESS_GROUPS } from './application-menu'
import AuthGate from './AuthGate.vue'
import ReportApplication from './ReportApplication.vue'
</script>

<template>
  <AuthGate v-slot="{ user, logout }" title="报告自动生成系统" :required-permission-groups="APPLICATION_ACCESS_GROUPS">
    <ReportApplication :user="user" @logout="logout" />
  </AuthGate>
</template>
