import { useMemo } from 'react'

import { cn } from '@/lib/utils'

export interface PasswordStrength {
  score: 0 | 1 | 2 | 3
  label: string
  valid: boolean
}

/** 与后端 validate_password_strength 保持一致：≥8 位，含大写、小写、数字 */
export function evaluatePassword(password: string): PasswordStrength {
  const checks = [
    password.length >= 8,
    /[a-z]/.test(password),
    /[A-Z]/.test(password),
    /\d/.test(password),
  ]
  const valid = checks.every(Boolean)
  const passed = checks.filter(Boolean).length

  if (!password) return { score: 0, label: '', valid: false }
  if (passed <= 2) return { score: 1, label: '弱', valid }
  if (passed === 3) return { score: 2, label: '中', valid }
  return { score: 3, label: password.length >= 12 ? '强' : '中', valid }
}

const barColors = ['bg-border', 'bg-red-500', 'bg-amber-500', 'bg-green-500'] as const

export function PasswordStrengthMeter({ password }: { password: string }) {
  const strength = useMemo(() => evaluatePassword(password), [password])

  if (!password) return null

  return (
    <div className="space-y-1">
      <div className="flex gap-1" aria-hidden>
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className={cn(
              'h-1 flex-1 rounded-full transition-colors',
              i <= strength.score ? barColors[strength.score] : 'bg-border',
            )}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        密码强度：{strength.label}
        {!strength.valid && ' · 至少 8 位，需含大写字母、小写字母和数字'}
      </p>
    </div>
  )
}
