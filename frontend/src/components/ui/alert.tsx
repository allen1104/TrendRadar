import { AlertCircle, CheckCircle2, Info } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

const styles = {
  error: 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300',
  success: 'border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300',
  info: 'border-border bg-muted text-muted-foreground',
} as const

const icons = { error: AlertCircle, success: CheckCircle2, info: Info } as const

export function Alert({
  variant = 'info',
  className,
  children,
}: {
  variant?: keyof typeof styles
  className?: string
  children: ReactNode
}) {
  const Icon = icons[variant]
  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={cn(
        'flex items-start gap-2 rounded-md border px-3 py-2 text-sm',
        styles[variant],
        className,
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">{children}</div>
    </div>
  )
}
