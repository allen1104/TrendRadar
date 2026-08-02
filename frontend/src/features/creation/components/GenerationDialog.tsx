import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { Platform, Style } from '@/features/creation/api/creation'

interface PlatformOptionLite {
  key: Platform
  name: string
  targetWords: [number, number]
}

interface StyleOptionLite {
  key: Style
  name: string
  description: string
}

interface GenerationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  platforms: PlatformOptionLite[]
  styles: StyleOptionLite[]
  onSubmit: (body: {
    platform: Platform
    style: Style
    targetWords: number
    audience: string
    extraRequirement: string
  }) => void
  estimatedCostUsd: number
}

/**
 * 生成配置弹窗：选平台 + 风格 + 高级选项。
 * 模态用纯 div 实现（避免引入 Radix/shadcn Dialog）。
 */
export function GenerationDialog({
  open,
  onOpenChange,
  platforms,
  styles,
  onSubmit,
  estimatedCostUsd,
}: GenerationDialogProps) {
  const [platform, setPlatform] = useState<Platform>('WECHAT')
  const [style, setStyle] = useState<Style>('DEEP_DIVE')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [targetWords, setTargetWords] = useState<number>(2500)
  const [audience, setAudience] = useState('')
  const [extraRequirement, setExtraRequirement] = useState('')

  if (!open) return null

  const meta = platforms.find((p) => p.key === platform)
  const minW = meta?.targetWords[0] ?? 1000
  const maxW = meta?.targetWords[1] ?? 3000

  const handleSubmit = () => {
    onSubmit({ platform, style, targetWords, audience, extraRequirement })
    onOpenChange(false)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false)
      }}
      role="dialog"
      aria-label="生成文章"
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border bg-background p-6 shadow-xl">
        <div className="mb-4">
          <h2 className="text-lg font-semibold">✍️ 生成文章</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            选择目标平台与写作风格，AI 将基于该事件的多源材料为你生成稿件。
          </p>
        </div>

        <div className="space-y-4">
          {/* 平台选择 */}
          <div>
            <Label className="text-sm">平台</Label>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {platforms.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => {
                    setPlatform(p.key)
                    setTargetWords(p.targetWords[0])
                  }}
                  className={cn(
                    'rounded-lg border px-3 py-2 text-left text-sm transition',
                    platform === p.key
                      ? 'border-primary bg-primary/10 ring-1 ring-primary'
                      : 'hover:bg-muted/40',
                  )}
                >
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {p.targetWords[0]}-{p.targetWords[1]} 字
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* 风格选择 */}
          <div>
            <Label className="text-sm">风格</Label>
            <div className="mt-2 grid grid-cols-5 gap-2">
              {styles.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => setStyle(s.key)}
                  title={s.description}
                  className={cn(
                    'rounded-lg border px-3 py-2 text-center text-sm transition',
                    style === s.key
                      ? 'border-primary bg-primary/10 ring-1 ring-primary'
                      : 'hover:bg-muted/40',
                  )}
                >
                  {s.name}
                </button>
              ))}
            </div>
          </div>

          {/* 高级选项 */}
          <div>
            <button
              type="button"
              onClick={() => setAdvancedOpen((v) => !v)}
              className="text-sm text-primary hover:underline"
            >
              {advancedOpen ? '▼' : '▶'} 高级选项
            </button>
            {advancedOpen && (
              <div className="mt-2 space-y-3 rounded-lg border bg-muted/20 p-3">
                <div>
                  <Label className="text-xs">
                    目标字数（推荐区间 {minW}-{maxW}）
                  </Label>
                  <div className="mt-1 flex items-center gap-2">
                    <input
                      type="range"
                      min={Math.floor(minW * 0.5)}
                      max={Math.ceil(maxW * 1.5)}
                      value={targetWords}
                      onChange={(e) => setTargetWords(Number(e.target.value))}
                      className="flex-1"
                    />
                    <Input
                      type="number"
                      value={targetWords}
                      onChange={(e) => setTargetWords(Number(e.target.value))}
                      className="w-20"
                    />
                  </div>
                </div>
                <div>
                  <Label className="text-xs">目标受众</Label>
                  <Input
                    value={audience}
                    onChange={(e) => setAudience(e.target.value)}
                    placeholder="如：AI 应用开发者"
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs">附加要求（≤500 字）</Label>
                  <textarea
                    value={extraRequirement}
                    onChange={(e) => setExtraRequirement(e.target.value)}
                    placeholder="重点展开架构部分，加入与 LangGraph 的对比"
                    rows={3}
                    maxLength={500}
                    className="mt-1 flex w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                  />
                </div>
              </div>
            )}
          </div>

          <div className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            预计消耗约 ${estimatedCostUsd.toFixed(3)}，耗时 20-40 秒
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit}>开始生成</Button>
        </div>
      </div>
    </div>
  )
}