import { Outlet } from 'react-router-dom'

import { Toaster } from '@/components/ui/toast'
import { useAuthBootstrap } from '@/features/auth/hooks/useAuth'

/** 登录/注册页布局：无导航栏，但仍要跑一次会话恢复探测 */
export function AuthLayout() {
  useAuthBootstrap()

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Outlet />
      <Toaster />
    </div>
  )
}
