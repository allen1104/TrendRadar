import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toast'
import { PasswordStrengthMeter, evaluatePassword } from '@/features/auth/components/PasswordStrengthMeter'
import {
  useChangePassword,
  useMe,
  useUpdatePreference,
  useUpdateProfile,
} from '@/features/auth/hooks/useAuth'
import { ROLE_LABEL, type DefaultScope } from '@/features/auth/types'
import type { ApiError } from '@/lib/api/client'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/lib/utils'

const TABS = [
  { key: 'profile', label: '基本资料' },
  { key: 'preference', label: '偏好设置' },
  { key: 'security', label: '安全' },
] as const

type TabKey = (typeof TABS)[number]['key']

const CATEGORIES = [
  'AI',
  'AGENT',
  'LLM',
  'MCP',
  'PROGRAMMING',
  'OPENSOURCE',
  'PAPER',
  'STARTUP',
  'HARDWARE',
  'INTERNET',
  'BUSINESS',
]

export function ProfilePage() {
  const [tab, setTab] = useState<TabKey>('profile')
  const { data: me, isLoading } = useMe()

  if (isLoading || !me) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <div className="h-8 w-40 animate-pulse rounded bg-muted" />
        <div className="mt-6 h-64 animate-pulse rounded-xl bg-muted" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">个人中心</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {me.email} · {ROLE_LABEL[me.role]}
        </p>
      </header>

      <nav className="mb-6 flex gap-1 border-b border-border" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === t.key
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'profile' && <ProfileTab username={me.username} avatarUrl={me.avatarUrl} />}
      {tab === 'preference' && <PreferenceTab preference={me.preference} />}
      {tab === 'security' && <SecurityTab />}
    </div>
  )
}

function ProfileTab({ username, avatarUrl }: { username: string; avatarUrl: string | null }) {
  const [name, setName] = useState(username)
  const [avatar, setAvatar] = useState(avatarUrl ?? '')
  const update = useUpdateProfile()
  const error = update.error as ApiError | null

  const dirty = name !== username || avatar !== (avatarUrl ?? '')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">基本资料</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="username">昵称</Label>
          <Input
            id="username"
            value={name}
            maxLength={50}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="avatar">头像地址</Label>
          <Input
            id="avatar"
            value={avatar}
            placeholder="https://..."
            onChange={(e) => setAvatar(e.target.value)}
          />
        </div>

        {error && <Alert variant="error">{error.message}</Alert>}

        <Button
          disabled={!dirty || name.trim().length < 2}
          loading={update.isPending}
          onClick={() =>
            update.mutate(
              { username: name.trim(), avatarUrl: avatar.trim() || null },
              { onSuccess: () => toast.success('资料已更新') },
            )
          }
        >
          保存
        </Button>
      </CardContent>
    </Card>
  )
}

function PreferenceTab({ preference }: { preference: import('@/features/auth/types').Preference }) {
  const [scope, setScope] = useState<DefaultScope>(preference.defaultScope)
  const [categories, setCategories] = useState<string[]>(preference.followedCategories)
  const [optIn, setOptIn] = useState(preference.dailyReportOptIn)
  const update = useUpdatePreference()
  const error = update.error as ApiError | null

  const toggleCategory = (c: string) =>
    setCategories((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">偏好设置</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-1.5">
          <Label htmlFor="scope">默认时间维度</Label>
          <Select
            id="scope"
            value={scope}
            onChange={(e) => setScope(e.target.value as DefaultScope)}
          >
            <option value="TODAY">今日热点</option>
            <option value="WEEK">本周热点</option>
            <option value="MONTH">本月热点</option>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>关注分类</Label>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((c) => {
              const active = categories.includes(c)
              return (
                <button
                  key={c}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleCategory(c)}
                  className={cn(
                    'rounded-md border px-2.5 py-1 text-xs font-medium transition-colors',
                    active
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:bg-muted',
                  )}
                >
                  {c}
                </button>
              )
            })}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <Label>订阅每日日报</Label>
            <p className="text-xs text-muted-foreground">日报模块上线后生效</p>
          </div>
          <Switch checked={optIn} onCheckedChange={setOptIn} aria-label="订阅每日日报" />
        </div>

        {error && <Alert variant="error">{error.message}</Alert>}

        <Button
          loading={update.isPending}
          onClick={() =>
            update.mutate(
              {
                defaultScope: scope,
                followedCategories: categories,
                dailyReportOptIn: optIn,
              },
              { onSuccess: () => toast.success('偏好已保存') },
            )
          }
        >
          保存
        </Button>
      </CardContent>
    </Card>
  )
}

function SecurityTab() {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')

  const navigate = useNavigate()
  const clear = useAuthStore((s) => s.clear)
  const change = useChangePassword()
  const error = change.error as ApiError | null

  const strength = evaluatePassword(newPassword)
  const mismatch = confirm.length > 0 && confirm !== newPassword
  const canSubmit = oldPassword !== '' && strength.valid && !mismatch && confirm !== ''

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">修改密码</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="old">原密码</Label>
          <Input
            id="old"
            type="password"
            autoComplete="current-password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="new">新密码</Label>
          <Input
            id="new"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <PasswordStrengthMeter password={newPassword} />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="confirm-new">确认新密码</Label>
          <Input
            id="confirm-new"
            type="password"
            autoComplete="new-password"
            aria-invalid={mismatch}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          {mismatch && <p className="text-xs text-red-600">两次输入的密码不一致</p>}
        </div>

        <Alert variant="info">修改密码后所有登录状态会失效，需要重新登录。</Alert>

        {error && <Alert variant="error">{error.message}</Alert>}

        <Button
          disabled={!canSubmit}
          loading={change.isPending}
          onClick={() =>
            change.mutate(
              { oldPassword, newPassword },
              {
                onSuccess: () => {
                  toast.success('密码已修改，请重新登录')
                  clear()
                  navigate('/login', { replace: true })
                },
              },
            )
          }
        >
          修改密码
        </Button>
      </CardContent>
    </Card>
  )
}
