import { createBrowserRouter } from 'react-router-dom'

import { AuthLayout } from '@/app/AuthLayout'
import { RootLayout } from '@/app/RootLayout'
import { AdminUsersPage } from '@/features/admin/pages/AdminUsersPage'
import { AiConfigPage } from '@/features/admin/pages/AiConfigPage'
import { SourceManagementPage } from '@/features/admin/pages/SourceManagementPage'
import { RedirectIfAuthenticated, RequireRole } from '@/features/auth/components/RequireRole'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { ProfilePage } from '@/features/auth/pages/ProfilePage'
import { RegisterPage } from '@/features/auth/pages/RegisterPage'

function Placeholder({ title, module }: { title: string; module: string }) {
  return (
    <div className="mx-auto max-w-3xl p-12 text-center">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-muted-foreground">
        该模块尚未实现，需求见 <code className="text-sm">doc/SPEC-{module}.md</code>
      </p>
    </div>
  )
}

/**
 * 路由表。随模块开发逐步补全。
 * 认证页走 AuthLayout（无导航栏），其余走 RootLayout。
 */
export const router = createBrowserRouter([
  {
    element: <AuthLayout />,
    children: [
      {
        path: '/login',
        element: (
          <RedirectIfAuthenticated>
            <LoginPage />
          </RedirectIfAuthenticated>
        ),
      },
      {
        path: '/register',
        element: (
          <RedirectIfAuthenticated>
            <RegisterPage />
          </RedirectIfAuthenticated>
        ),
      },
    ],
  },
  {
    path: '/',
    element: <RootLayout />,
    children: [
      { index: true, element: <Placeholder title="热点中心" module="hotspot" /> },
      { path: 'events/:id', element: <Placeholder title="热点详情" module="hotspot" /> },
      { path: 'trends', element: <Placeholder title="趋势分析" module="trend" /> },
      { path: 'reports', element: <Placeholder title="日报中心" module="report" /> },
      {
        path: 'collections',
        element: (
          <RequireRole minRole="USER">
            <Placeholder title="我的收藏" module="collection" />
          </RequireRole>
        ),
      },
      {
        path: 'me',
        element: (
          <RequireRole minRole="USER">
            <ProfilePage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/users',
        element: (
          <RequireRole minRole="ADMIN">
            <AdminUsersPage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/sources',
        element: (
          <RequireRole minRole="ADMIN">
            <SourceManagementPage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/ai',
        element: (
          <RequireRole minRole="ADMIN">
            <AiConfigPage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/sources',
        element: (
          <RequireRole minRole="ADMIN">
            <Placeholder title="采集源管理" module="source" />
          </RequireRole>
        ),
      },
      { path: '*', element: <NotFound /> },
    ],
  },
])

function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2">
      <p className="text-5xl font-bold text-muted-foreground">404</p>
      <p className="text-muted-foreground">页面不存在</p>
    </div>
  )
}
