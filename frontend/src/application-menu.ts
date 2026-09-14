import type { Component } from 'vue'
import {
  Clock, Coin, Cpu, Document, Files, Key, User,
} from '@element-plus/icons-vue'

export type ApplicationModuleId =
  | 'reports'
  | 'templates'
  | 'standard-fields'
  | 'ai-service'
  | 'users'
  | 'permissions'
  | 'history'

export interface ApplicationModule {
  id: ApplicationModuleId
  group: 'reports' | 'system'
  label: string
  description: string
  permissions: string[]
  icon: Component
}

export const APPLICATION_MODULES: ApplicationModule[] = [
  {
    id: 'reports', group: 'reports', label: '报告管理大厅', description: '检索、生成与导出',
    permissions: ['REPORT_EDIT'], icon: Files,
  },
  {
    id: 'templates', group: 'system', label: '报告模板与规则', description: '模板、版本与字段映射',
    permissions: ['ADMIN_ACCESS', 'RULES_MANAGE'], icon: Document,
  },
  {
    id: 'standard-fields', group: 'system', label: '系统标准字段', description: '字段目录与来源规则',
    permissions: ['ADMIN_ACCESS', 'LIMS_FIELDS_MANAGE'], icon: Coin,
  },
  {
    id: 'ai-service', group: 'system', label: 'AI 服务配置', description: '接口、模型与连接测试',
    permissions: ['ADMIN_ACCESS', 'RULES_MANAGE'], icon: Cpu,
  },
  {
    id: 'users', group: 'system', label: '用户管理', description: '账号、角色与状态',
    permissions: ['ADMIN_ACCESS', 'USERS_MANAGE'], icon: User,
  },
  {
    id: 'permissions', group: 'system', label: '权限管理', description: '角色权限矩阵',
    permissions: ['ADMIN_ACCESS', 'PERMISSIONS_MANAGE'], icon: Key,
  },
  {
    id: 'history', group: 'system', label: '报告生成历史', description: '生成记录与历史文件',
    permissions: ['ADMIN_ACCESS', 'REPORT_HISTORY_VIEW'], icon: Clock,
  },
]

export const APPLICATION_ACCESS_GROUPS = APPLICATION_MODULES.map((item) => item.permissions)

export function availableApplicationModules(permissions: string[]) {
  const granted = new Set(permissions)
  return APPLICATION_MODULES.filter((item) => item.permissions.every((code) => granted.has(code)))
}
