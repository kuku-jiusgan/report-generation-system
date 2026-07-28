import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1/auth', timeout: 30000, withCredentials: true })

export interface AuthUser {
  id: string
  username: string
  displayName: string
  roleCode: 'SUPER_ADMIN' | 'SYSTEM_ADMIN' | 'REPORT_USER'
  enabled: boolean
  mustChangePassword: boolean
  permissions: string[]
  createdAt?: string
  updatedAt?: string
  lastLoginAt?: string
}

export type AuthPortal = 'report' | 'admin'

export async function login(username: string, password: string, portal: AuthPortal) {
  return (await http.post<AuthUser>('/login', { username, password, portal })).data
}

export async function logout(portal: AuthPortal) {
  await http.post('/logout', undefined, { params: { portal } })
}

export async function currentUser(portal: AuthPortal) {
  return (await http.get<AuthUser>('/me', { params: { portal } })).data
}

export async function changePassword(currentPassword: string, newPassword: string, portal: AuthPortal) {
  return (await http.post<AuthUser>('/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  }, { params: { portal } })).data
}
