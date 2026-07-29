import { http, type Page } from '@/lib/api/client'
import type {
  AdminUserItem,
  Me,
  Preference,
  Role,
  TokenResponse,
  UserStatus,
} from '@/features/auth/types'

export interface RegisterPayload {
  email: string
  username: string
  password: string
}

export interface LoginPayload {
  email: string
  password: string
}

export const authApi = {
  register: (payload: RegisterPayload) =>
    http.post<{ userId: number; email: string; username: string; role: Role }>(
      '/auth/register',
      payload,
    ).then((r) => r.data),

  login: (payload: LoginPayload) =>
    http.post<TokenResponse>('/auth/login', payload).then((r) => r.data),

  logout: () => http.post<void>('/auth/logout').then(() => undefined),

  me: () => http.get<Me>('/auth/me').then((r) => r.data),

  updateProfile: (payload: { username?: string; avatarUrl?: string | null }) =>
    http.patch<Me>('/auth/me', payload).then((r) => r.data),

  changePassword: (payload: { oldPassword: string; newPassword: string }) =>
    http.put<void>('/auth/me/password', payload).then(() => undefined),

  updatePreference: (payload: Partial<Preference>) =>
    http.put<Preference>('/auth/me/preference', payload).then((r) => r.data),
}

export interface AdminUserQuery {
  page?: number
  size?: number
  keyword?: string
  role?: Role
  status?: UserStatus
  sort?: string
}

export const adminUserApi = {
  list: (params: AdminUserQuery) =>
    http.get<Page<AdminUserItem>>('/admin/users', { params }).then((r) => r.data),

  update: (userId: number, payload: { role?: Role; status?: UserStatus }) =>
    http.patch<AdminUserItem>(`/admin/users/${userId}`, payload).then((r) => r.data),
}
