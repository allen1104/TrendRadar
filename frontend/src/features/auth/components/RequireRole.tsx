import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { hasRole, ROLE_LABEL, type Role } from '@/features/auth/types'
import { useAuthStore } from '@/stores/authStore'

/**
 * 路由守卫。
 *
 * - 未登录 → 重定向 /login?redirect={当前路径}
 * - 已登录但角色不足 → 渲染 403
 *
 * 注意：前端权限只是体验优化，真正的校验在后端。
 */
export function RequireRole({
  minRole = 'USER',
  children,
}: {
  minRole?: Role
  children: ReactNode
}) {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  const location = useLocation()

  if (!initialized) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!user) {
    const redirect = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?redirect=${redirect}`} replace />
  }

  if (!hasRole(user.role, minRole)) {
    return <Forbidden required={minRole} actual={user.role} />
  }

  return <>{children}</>
}

function Forbidden({ required, actual }: { required: Role; actual: Role }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-2 text-center">
      <p className="text-5xl font-bold text-muted-foreground">403</p>
      <p className="text-lg font-medium">权限不足</p>
      <p className="text-sm text-muted-foreground">
        此页面需要 {ROLE_LABEL[required]} 及以上权限，当前身份为 {ROLE_LABEL[actual]}
      </p>
    </div>
  )
}

/** 已登录用户访问 /login、/register 时跳走 */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)

  if (!initialized) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }
  if (user) return <Navigate to="/" replace />
  return <>{children}</>
}
