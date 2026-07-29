import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { authApi, type LoginPayload, type RegisterPayload } from '@/features/auth/api/auth'
import type { Preference } from '@/features/auth/types'
import { getRefreshToken, onSessionExpired, refreshSession } from '@/lib/api/client'
import { useAuthStore } from '@/stores/authStore'

export const authKeys = {
  me: ['auth', 'me'] as const,
}

/**
 * 应用启动时用 localStorage 里的 refreshToken 静默恢复会话。
 * 同时订阅"会话失效"广播，清空登录态。
 */
export function useAuthBootstrap() {
  const { setUser, clear, setInitialized, initialized } = useAuthStore()
  const queryClient = useQueryClient()

  useEffect(() => onSessionExpired(() => {
    clear()
    queryClient.removeQueries({ queryKey: authKeys.me })
  }), [clear, queryClient])

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      if (!getRefreshToken()) {
        if (!cancelled) setInitialized(true)
        return
      }
      try {
        await refreshSession()
        const me = await authApi.me()
        if (!cancelled) {
          setUser(me)
          queryClient.setQueryData(authKeys.me, me)
        }
      } catch {
        if (!cancelled) clear()
      } finally {
        if (!cancelled) setInitialized(true)
      }
    }

    if (!initialized) void bootstrap()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

export function useMe(enabled = true) {
  const isAuthed = useAuthStore((s) => s.user !== null)
  return useQuery({
    queryKey: authKeys.me,
    queryFn: authApi.me,
    enabled: enabled && isAuthed,
    staleTime: 5 * 60_000,
  })
}

export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: LoginPayload) => authApi.login(payload),
    onSuccess: (data) => {
      setSession(data.user, data.accessToken, data.refreshToken)
      void queryClient.invalidateQueries({ queryKey: authKeys.me })
    },
  })
}

export function useRegister() {
  return useMutation({
    mutationFn: (payload: RegisterPayload) => authApi.register(payload),
  })
}

export function useLogout() {
  const clear = useAuthStore((s) => s.clear)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => authApi.logout(),
    // 无论后端成功与否，前端都要退出
    onSettled: () => {
      clear()
      queryClient.clear()
    },
  })
}

export function useUpdateProfile() {
  const setUser = useAuthStore((s) => s.setUser)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: authApi.updateProfile,
    onSuccess: (me) => {
      setUser(me)
      queryClient.setQueryData(authKeys.me, me)
    },
  })
}

export function useChangePassword() {
  return useMutation({ mutationFn: authApi.changePassword })
}

export function useUpdatePreference() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: Partial<Preference>) => authApi.updatePreference(payload),
    onSuccess: (preference) => {
      queryClient.setQueryData(authKeys.me, (old: unknown) =>
        old && typeof old === 'object' ? { ...old, preference } : old,
      )
    },
  })
}
