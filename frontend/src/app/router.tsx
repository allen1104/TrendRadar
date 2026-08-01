import { createBrowserRouter } from 'react-router-dom'

import { AuthLayout } from '@/app/AuthLayout'
import { RootLayout } from '@/app/RootLayout'
import { AdminAuditPage } from '@/features/admin/pages/AdminAuditPage'
import { AdminConfigsPage } from '@/features/admin/pages/AdminConfigsPage'
import { AdminDashboardPage } from '@/features/admin/pages/AdminDashboardPage'
import { AdminTasksPage } from '@/features/admin/pages/AdminTasksPage'
import { AdminUsersPage } from '@/features/admin/pages/AdminUsersPage'
import { AiConfigPage } from '@/features/admin/pages/AiConfigPage'
import { SourceManagementPage } from '@/features/admin/pages/SourceManagementPage'
import { RedirectIfAuthenticated, RequireRole } from '@/features/auth/components/RequireRole'
import { LoginPage } from '@/features/auth/pages/LoginPage'
import { ProfilePage } from '@/features/auth/pages/ProfilePage'
import { RegisterPage } from '@/features/auth/pages/RegisterPage'
import { CollectionPage } from '@/features/collection/pages/CollectionPage'
import { EventDetailPage } from '@/features/hotspot/pages/EventDetailPage'
import { HotspotPage } from '@/features/hotspot/pages/HotspotPage'

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
      { index: true, element: <HotspotPage /> },
      { path: 'events/:id', element: <EventDetailPage /> },
      {
        path: 'admin',
        element: (
          <RequireRole minRole="EDITOR">
            <AdminDashboardPage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/config',
        element: (
          <RequireRole minRole="ADMIN">
            <AdminConfigsPage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/tasks',
        element: (
          <RequireRole minRole="EDITOR">
            <AdminTasksPage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/audit',
        element: (
          <RequireRole minRole="ADMIN">
            <AdminAuditPage />
          </RequireRole>
        ),
      },
      { path: 'trends', element: <Placeholder title="趋势分析" module="trend" /> },
      { path: 'reports', element: <Placeholder title="日报中心" module="report" /> },
      {
        path: 'collections',
        element: (
          <RequireRole minRole="USER">
            <CollectionPage />
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
