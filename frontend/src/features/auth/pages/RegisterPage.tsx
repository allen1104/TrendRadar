import { Radar } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  evaluatePassword,
  PasswordStrengthMeter,
} from '@/features/auth/components/PasswordStrengthMeter'
import { useLogin, useRegister } from '@/features/auth/hooks/useAuth'
import type { ApiError } from '@/lib/api/client'

export function RegisterPage() {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')

  const navigate = useNavigate()
  const register = useRegister()
  const login = useLogin()

  const strength = useMemo(() => evaluatePassword(password), [password])
  const mismatch = confirm.length > 0 && confirm !== password
  const canSubmit =
    email.trim() !== '' && username.trim().length >= 2 && strength.valid && !mismatch && confirm !== ''

  const error = (register.error ?? login.error) as ApiError | null
  const pending = register.isPending || login.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    register.mutate(
      { email: email.trim(), username: username.trim(), password },
      {
        // 注册成功后自动登录
        onSuccess: () =>
          login.mutate(
            { email: email.trim(), password },
            { onSuccess: () => navigate('/', { replace: true }) },
          ),
      },
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Radar className="mx-auto h-8 w-8 text-primary" aria-hidden />
          <CardTitle>注册 TrendRadar</CardTitle>
          <CardDescription>开始发现值得深入研究的科技趋势</CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="username">昵称</Label>
              <Input
                id="username"
                required
                minLength={2}
                maxLength={50}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <PasswordStrengthMeter password={password} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm">确认密码</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                aria-invalid={mismatch}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
              {mismatch && <p className="text-xs text-red-600">两次输入的密码不一致</p>}
            </div>

            {error && <Alert variant="error">{error.message}</Alert>}

            <Button type="submit" className="w-full" disabled={!canSubmit} loading={pending}>
              注册
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            已有账号？{' '}
            <Link to="/login" className="text-primary hover:underline">
              去登录
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
