import { X } from 'lucide-react'
import { useEffect } from 'react'
import { create } from 'zustand'

import { cn } from '@/lib/utils'

export interface Toast {
  id: number
  message: string
  variant: 'success' | 'error' | 'info'
}

interface ToastState {
  toasts: Toast[]
  push: (message: string, variant?: Toast['variant']) => void
  dismiss: (id: number) => void
}

let nextId = 1

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (message, variant = 'info') =>
    set((s) => ({ toasts: [...s.toasts, { id: nextId++, message, variant }] })),
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

export const toast = {
  success: (m: string) => useToastStore.getState().push(m, 'success'),
  error: (m: string) => useToastStore.getState().push(m, 'error'),
  info: (m: string) => useToastStore.getState().push(m, 'info'),
}

const variantStyles = {
  success: 'border-green-500/40 bg-green-500/10 text-green-800 dark:text-green-200',
  error: 'border-red-500/40 bg-red-500/10 text-red-800 dark:text-red-200',
  info: 'border-border bg-background text-foreground',
} as const

function ToastItem({ item }: { item: Toast }) {
  const dismiss = useToastStore((s) => s.dismiss)

  useEffect(() => {
    const timer = setTimeout(() => dismiss(item.id), 4000)
    return () => clearTimeout(timer)
  }, [item.id, dismiss])

  return (
    <div
      role="status"
      className={cn(
        'flex items-start gap-2 rounded-md border px-4 py-3 text-sm shadow-lg',
        variantStyles[item.variant],
      )}
    >
      <span className="flex-1">{item.message}</span>
      <button
        type="button"
        onClick={() => dismiss(item.id)}
        aria-label="关闭提示"
        className="opacity-60 hover:opacity-100"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts)
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem item={t} />
        </div>
      ))}
    </div>
  )
}
