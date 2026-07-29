import { create } from 'zustand'

import { clearRefreshToken, setAccessToken, setRefreshToken } from '@/lib/api/client'
import type { Me, Role, UserBrief } from '@/features/auth/types'

/**
 * 登录态。
 * accessToken 只放内存（见 doc/SPEC-auth.md），refreshToken 放 localStorage。
 */
interface AuthState {
  user: UserBrief | Me | null
  /** 启动时"用 refreshToken 静默恢复会话"是否已完成 */
  initialized: boolean
  setSession: (user: UserBrief, accessToken: string, refreshToken: string) => void
  setUser: (user: Me) => void
  clear: () => void
  setInitialized: (v: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initialized: false,

  setSession: (user, accessToken, refreshToken) => {
    setAccessToken(accessToken)
    setRefreshToken(refreshToken)
    set({ user })
  },

  setUser: (user) => set({ user }),

  clear: () => {
    setAccessToken(null)
    clearRefreshToken()
    set({ user: null })
  },

  setInitialized: (v) => set({ initialized: v }),
}))

/** 便捷选择器 */
export const useCurrentUser = () => useAuthStore((s) => s.user)
export const useCurrentRole = (): Role => useAuthStore((s) => s.user?.role ?? 'GUEST')
export const useIsAuthenticated = () => useAuthStore((s) => s.user !== null)
