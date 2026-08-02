import type { QuickQuestion } from '@/features/assistant/api/assistant'

import { cn } from '@/lib/utils'

interface QuickQuestionsProps {
  items: QuickQuestion[]
  /** 已经问过的 key（点击后灰化） */
  askedKeys: Set<string>
  onPick: (q: QuickQuestion) => void
}

/** 横向滚动的 Chips 列表，点击即发送。 */
export function QuickQuestions({ items, askedKeys, onPick }: QuickQuestionsProps) {
  if (items.length === 0) return null
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-thin">
      {items.map((q) => {
        const disabled = askedKeys.has(q.key)
        return (
          <button
            key={q.key}
            type="button"
            disabled={disabled}
            onClick={() => onPick(q)}
            className={cn(
              'shrink-0 text-xs rounded-full border px-3 py-1 transition',
              disabled
                ? 'opacity-40 cursor-not-allowed border-border text-muted-foreground'
                : 'border-border hover:border-primary hover:text-primary',
            )}
            title={q.question}
          >
            {q.label}
          </button>
        )
      })}
    </div>
  )
}