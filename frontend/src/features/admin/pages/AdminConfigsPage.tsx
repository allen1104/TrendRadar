import { useMemo, useState } from 'react'
import { format } from 'date-fns'
import { Lock, RotateCcw, Save } from 'lucide-react'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toast'
import { type ConfigGroup, type ConfigItem } from '@/features/admin/api/admin'
import { useConfigs, useUpdateConfig } from '@/features/admin/hooks/useAdmin'

const GROUPS: { key: ConfigGroup; label: string }[] = [
  { key: 'DEDUPE', label: '去重聚合' },
  { key: 'RANK', label: '评分权重' },
  { key: 'AI', label: 'AI 设置' },
  { key: 'SCHEDULE', label: '任务调度' },
  { key: 'SEARCH', label: '搜索' },
  { key: 'GENERAL', label: '通用' },
]

export function AdminConfigsPage() {
  const [activeGroup, setActiveGroup] = useState<ConfigGroup>('DEDUPE')
  const { data: allConfigs, isPending } = useConfigs()
  const grouped = useMemo(() => {
    const m: Record<string, ConfigItem[]> = {}
    for (const g of GROUPS) m[g.key] = []
    if (allConfigs) {
      for (const c of allConfigs) {
        if (m[c.groupName]) m[c.groupName].push(c)
      }
    }
    return m
  }, [allConfigs])

  const configs = grouped[activeGroup] ?? []

  if (isPending) {
    return <div className="p-6 text-muted-foreground">加载中…</div>
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 p-6 xl:grid-cols-[200px_1fr]">
      {/* 左侧分组导航 */}
      <aside>
        <h1 className="mb-3 text-lg font-semibold">系统配置</h1>
        <nav className="space-y-1">
          {GROUPS.map((g) => (
            <button
              key={g.key}
              type="button"
              onClick={() => setActiveGroup(g.key)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                activeGroup === g.key
                  ? 'bg-primary/10 font-medium text-primary'
                  : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {g.label}
              <span className="ml-2 text-xs">({grouped[g.key]?.length ?? 0})</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* 右侧配置卡片 */}
      <div className="space-y-4">
        {configs.map((cfg) => (
          <ConfigCard key={cfg.id} item={cfg} />
        ))}
        {configs.length === 0 && (
          <Alert>该分组下暂无配置</Alert>
        )}
      </div>
    </div>
  )
}

function ConfigCard({ item }: { item: ConfigItem }) {
  const [draft, setDraft] = useState<unknown>(item.configValue)
  const update = useUpdateConfig()
  const dirty = JSON.stringify(draft) !== JSON.stringify(item.configValue)

  const save = () => {
    update.mutate(
      { key: item.configKey, value: draft },
      {
        onSuccess: () => {
          toast.success(`已保存 ${item.displayName}`)
          if (item.requiresRerun) {
            toast.info('该配置需重跑数据才生效')
          }
        },
        onError: (e: unknown) => {
          const err = e as { detail?: string }
          toast.error(err?.detail ?? '保存失败')
        },
      },
    )
  }

  const reset = () => setDraft(item.configValue)

  return (
    <Card className="p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 font-medium">
            {item.displayName}
            {item.requiresRerun && <Lock className="h-3.5 w-3.5 text-amber-500" aria-hidden />}
            <code className="text-xs text-muted-foreground">{item.configKey}</code>
          </h3>
          {item.description && (
            <p className="mt-1 text-xs text-muted-foreground">{item.description}</p>
          )}
        </div>
        <div className="text-right">
          <Badge variant="outline">{item.valueType}</Badge>
          <p className="mt-1 text-[10px] text-muted-foreground">
            更新于 {format(new Date(item.updatedAt), 'MM-dd HH:mm')}
          </p>
        </div>
      </div>

      <ConfigValueEditor item={item} value={draft} onChange={setDraft} />

      <div className="mt-4 flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" disabled={!dirty} onClick={reset}>
          <RotateCcw className="mr-1 h-3 w-3" /> 重置
        </Button>
        <Button size="sm" disabled={!dirty || update.isPending} onClick={save}>
          <Save className="mr-1 h-3 w-3" /> 保存
        </Button>
      </div>
    </Card>
  )
}

function ConfigValueEditor({
  item,
  value,
  onChange,
}: {
  item: ConfigItem
  value: unknown
  onChange: (v: unknown) => void
}) {
  switch (item.valueType) {
    case 'BOOL':
      return (
        <Switch
          checked={Boolean(value)}
          disabled={!item.isEditable}
          onCheckedChange={(v) => onChange(v)}
        />
      )
    case 'INT':
    case 'FLOAT': {
      const num = Number(value ?? 0)
      const min = item.minValue ?? 0
      const max = item.maxValue ?? 100
      const step = item.valueType === 'INT' ? 1 : 0.01
      return (
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={num}
            onChange={(e) => onChange(item.valueType === 'INT' ? Number(e.target.value) : parseFloat(e.target.value))}
            className="flex-1 accent-primary"
          />
          <Input
            type="number"
            value={num}
            min={min}
            max={max}
            step={step}
            onChange={(e) =>
              onChange(item.valueType === 'INT' ? Number(e.target.value) : parseFloat(e.target.value))
            }
            className="w-28"
          />
        </div>
      )
    }
    case 'STRING':
      return (
        <Input
          value={String(value ?? '')}
          disabled={!item.isEditable}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'JSON':
      return (
        <textarea
          rows={6}
          className="w-full rounded-md border border-border bg-background p-2 font-mono text-xs"
          value={JSON.stringify(value, null, 2)}
          disabled={!item.isEditable}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value))
            } catch {
              // 让用户继续输入，只是不更新状态直到 JSON 合法
            }
          }}
        />
      )
    default:
      return <pre className="rounded bg-muted p-3 text-xs">{JSON.stringify(value, null, 2)}</pre>
  }
}