import { LogOut, Radar, User as UserIcon } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Toaster } from '@/components/ui/toast'
import { useAuthBootstrap, useLogout } from '@/features/auth/hooks/useAuth'
import { hasRole, ROLE_LABEL, type Role } from '@/features/auth/types'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'

interface NavItem {
  to: string
  label: string
  minRole: Role
}

/** 菜单按角色渲染（见 doc/SPEC-auth.md「前端页面」） */
const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '热点中心', minRole: 'GUEST' },
  { to: '/trends', label: '趋势分析', minRole: 'GUEST' },
  { to: '/collections', label: '我的收藏', minRole: 'USER' },
  { to: '/reports', label: '日报中心', minRole: 'GUEST' },
  { to: '/admin/ai', label: 'AI 配置', minRole: 'ADMIN' },
  { to: '/admin/sources', label: '采集源', minRole: 'ADMIN' },
  { to: '/admin/users', label: '用户管理', minRole: 'ADMIN' },
]

export function RootLayout() {
  useAuthBootstrap()

  const user = useAuthStore((s) => s.user)
  const role: Role = user?.role ?? 'GUEST'
  const navigate = useNavigate()
  const logout = useLogout()

  const visibleItems = NAV_ITEMS.filter((item) => hasRole(role, item.minRole))

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-6">
          <NavLink to="/" className="flex items-center gap-2 font-semibold">
            <Radar className="h-5 w-5 text-primary" aria-hidden />
            TrendRadar
          </NavLink>

          <nav className="flex flex-1 items-center gap-1">
            {visibleItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm transition-colors',
                    isActive
                      ? 'bg-muted font-medium text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          {user ? (
            <div className="flex items-center gap-2">
              <NavLink
                to="/me"
                className="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-muted"
              >
                <UserIcon className="h-4 w-4" aria-hidden />
                <span>{user.username}</span>
                <span className="text-xs text-muted-foreground">{ROLE_LABEL[user.role]}</span>
              </NavLink>
              <Button
                variant="ghost"
                size="icon"
                aria-label="登出"
                loading={logout.isPending}
                onClick={() =>
                  logout.mutate(undefined, {
                    onSettled: () => navigate('/login', { replace: true }),
                  })
                }
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => navigate('/login')}>
                登录
              </Button>
              <Button size="sm" onClick={() => navigate('/register')}>
                注册
              </Button>
            </div>
          )}
        </div>
      </header>

      <main>
        <Outlet />
      </main>

      <Toaster />
    </div>
  )
}
