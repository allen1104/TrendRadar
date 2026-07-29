/**
 * auth 模块类型。
 *
 * 注意：这些是手写的过渡类型。后端起来后跑 `pnpm gen:api`，
 * 用 `components['schemas']['MeResponse']` 等替换（见 frontend/CLAUDE.md 铁律 1）。
 */

export type Role = 'GUEST' | 'USER' | 'EDITOR' | 'ADMIN'
export type UserStatus = 'ACTIVE' | 'DISABLED'
export type DefaultScope = 'TODAY' | 'WEEK' | 'MONTH'

export const ROLE_LEVEL: Record<Role, number> = {
  GUEST: 0,
  USER: 10,
  EDITOR: 20,
  ADMIN: 30,
}

export const ROLE_LABEL: Record<Role, string> = {
  GUEST: '游客',
  USER: '普通用户',
  EDITOR: '编辑/运营',
  ADMIN: '管理员',
}

export function hasRole(actual: Role | undefined, required: Role): boolean {
  return ROLE_LEVEL[actual ?? 'GUEST'] >= ROLE_LEVEL[required]
}

export interface Preference {
  defaultScope: DefaultScope
  followedCategories: string[]
  followedTags: number[]
  mutedSources: number[]
  dailyReportOptIn: boolean
}

export interface UserBrief {
  userId: number
  email: string
  username: string
  avatarUrl: string | null
  role: Role
}

export interface Me extends UserBrief {
  lastLoginAt: string | null
  preference: Preference
}

export interface TokenResponse {
  accessToken: string
  refreshToken: string
  tokenType: string
  expiresIn: number
  user: UserBrief
}

export interface AdminUserItem extends UserBrief {
  status: UserStatus
  lastLoginAt: string | null
  createdAt: string
}
