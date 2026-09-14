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

export async function login(username: string, password: string) {
  return (await http.post<AuthUser>('/login', { username, password })).data
}

export async function logout() {
  await http.post('/logout')
}

export async function currentUser() {
  return (await http.get<AuthUser>('/me')).data
}

export async function changePassword(currentPassword: string, newPassword: string) {
  return (await http.post<AuthUser>('/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })).data
}
