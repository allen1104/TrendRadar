import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { toast } from '@/components/ui/toast'
import { adminUserApi, type AdminUserQuery } from '@/features/auth/api/auth'
import {
  ROLE_LABEL,
  type AdminUserItem,
  type Role,
  type UserStatus,
} from '@/features/auth/types'
import type { ApiError } from '@/lib/api/client'
import { useAuthStore } from '@/stores/authStore'

const adminUserKeys = {
  list: (q: AdminUserQuery) => ['admin', 'users', 'list', q] as const,
}

const roleBadgeVariant: Record<Role, 'default' | 'outline' | 'success' | 'warning' | 'danger'> = {
  GUEST: 'outline',
  USER: 'outline',
  EDITOR: 'warning',
  ADMIN: 'danger',
}

export function AdminUsersPage() {
  const [keyword, setKeyword] = useState('')
  const [role, setRole] = useState<Role | ''>('')
  const [status, setStatus] = useState<UserStatus | ''>('')
  const [page, setPage] = useState(1)

  const query: AdminUserQuery = {
    page,
    size: 20,
    keyword: keyword.trim() || undefined,
    role: role || undefined,
    status: status || undefined,
    sort: '-createdAt',
  }

  const { data, isLoading, error } = useQuery({
    queryKey: adminUserKeys.list(query),
    queryFn: () => adminUserApi.list(query),
  })

  const queryClient = useQueryClient()
  const currentUserId = useAuthStore((s) => s.user?.userId)

  const update = useMutation({
    mutationFn: ({ userId, ...payload }: { userId: number; role?: Role; status?: UserStatus }) =>
      adminUserApi.update(userId, payload),
    onSuccess: () => {
      toast.success('已更新')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  const resetFilters = () => {
    setKeyword('')
    setRole('')
    setStatus('')
    setPage(1)
  }

  return (
    <div className="mx-auto max-w-6xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">用户管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          共 {data?.total ?? 0} 位用户。系统至少保留一个启用中的管理员。
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Input
            placeholder="搜索邮箱或昵称"
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value)
              setPage(1)
            }}
          />
        </div>
        <Select
          className="w-36"
          value={role}
          onChange={(e) => {
            setRole(e.target.value as Role | '')
            setPage(1)
          }}
        >
          <option value="">全部角色</option>
          <option value="USER">普通用户</option>
          <option value="EDITOR">编辑/运营</option>
          <option value="ADMIN">管理员</option>
        </Select>
        <Select
          className="w-32"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as UserStatus | '')
            setPage(1)
          }}
        >
          <option value="">全部状态</option>
          <option value="ACTIVE">启用</option>
          <option value="DISABLED">禁用</option>
        </Select>
        <Button variant="ghost" onClick={resetFilters}>
          重置
        </Button>
      </div>

      {error && <Alert variant="error">{(error as ApiError).message}</Alert>}

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">邮箱</th>
                <th className="px-4 py-3 font-medium">昵称</th>
                <th className="px-4 py-3 font-medium">角色</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">最后登录</th>
                <th className="px-4 py-3 font-medium">注册时间</th>
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td colSpan={6} className="px-4 py-3">
                      <div className="h-5 animate-pulse rounded bg-muted" />
                    </td>
                  </tr>
                ))}

              {!isLoading && data?.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                    没有匹配的用户
                  </td>
                </tr>
              )}

              {data?.items.map((u) => (
                <UserRow
                  key={u.userId}
                  user={u}
                  isSelf={u.userId === currentUserId}
                  pending={update.isPending}
                  onChange={(payload) => update.mutate({ userId: u.userId, ...payload })}
                />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {data && data.pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            {data.page} / {data.pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= data.pages}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}

function UserRow({
  user,
  isSelf,
  pending,
  onChange,
}: {
  user: AdminUserItem
  isSelf: boolean
  pending: boolean
  onChange: (payload: { role?: Role; status?: UserStatus }) => void
}) {
  const confirmAnd = (message: string, payload: { role?: Role; status?: UserStatus }) => {
    if (window.confirm(message)) onChange(payload)
  }

  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-4 py-3">
        {user.email}
        {isSelf && <span className="ml-2 text-xs text-muted-foreground">（我）</span>}
      </td>
      <td className="px-4 py-3">{user.username}</td>
      <td className="px-4 py-3">
        {isSelf ? (
          <Badge variant={roleBadgeVariant[user.role]}>{ROLE_LABEL[user.role]}</Badge>
        ) : (
          <Select
            className="h-8 w-32"
            value={user.role}
            disabled={pending}
            onChange={(e) =>
              confirmAnd(
                `确定把 ${user.username} 的角色改为 ${ROLE_LABEL[e.target.value as Role]}？`,
                { role: e.target.value as Role },
              )
            }
          >
            <option value="USER">普通用户</option>
            <option value="EDITOR">编辑/运营</option>
            <option value="ADMIN">管理员</option>
          </Select>
        )}
      </td>
      <td className="px-4 py-3">
        {isSelf ? (
          <Badge variant={user.status === 'ACTIVE' ? 'success' : 'danger'}>
            {user.status === 'ACTIVE' ? '启用' : '禁用'}
          </Badge>
        ) : (
          <Button
            size="sm"
            variant={user.status === 'ACTIVE' ? 'outline' : 'destructive'}
            disabled={pending}
            onClick={() =>
              confirmAnd(
                user.status === 'ACTIVE'
                  ? `确定禁用 ${user.username}？禁用后该用户无法登录。`
                  : `确定启用 ${user.username}？`,
                { status: user.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE' },
              )
            }
          >
            {user.status === 'ACTIVE' ? '禁用' : '启用'}
          </Button>
        )}
      </td>
      <td className="px-4 py-3 text-muted-foreground">{formatTime(user.lastLoginAt)}</td>
      <td className="px-4 py-3 text-muted-foreground">{formatTime(user.createdAt)}</td>
    </tr>
  )
}

function formatTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}
