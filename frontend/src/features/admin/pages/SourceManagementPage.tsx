import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { toast } from '@/components/ui/toast'
import {
  sourceApi,
  type Region,
  type RunStatus,
  type SourceCategory,
  type SourceItem,
} from '@/features/admin/api/source'
import type { ApiError } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const sourceKeys = {
  list: (q: object) => ['admin', 'sources', 'list', q] as const,
  plugins: ['admin', 'sources', 'plugins'] as const,
  logs: (id: number) => ['admin', 'sources', id, 'logs'] as const,
}

const statusBadge: Record<RunStatus, 'success' | 'warning' | 'danger' | 'outline'> = {
  SUCCESS: 'success',
  PARTIAL: 'warning',
  FAILED: 'danger',
  RUNNING: 'outline',
}

const statusLabel: Record<RunStatus, string> = {
  SUCCESS: '成功',
  PARTIAL: '部分',
  FAILED: '失败',
  RUNNING: '运行中',
}

export function SourceManagementPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [enabledOnly, setEnabledOnly] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [editing, setEditing] = useState<{ id: number | null } | null>(null)
  const [logsSourceId, setLogsSourceId] = useState<number | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: sourceKeys.list({ page, enabledOnly, keyword }),
    queryFn: () =>
      sourceApi.list({
        page,
        size: 20,
        enabled_only: enabledOnly || undefined,
        keyword: keyword.trim() || undefined,
      }),
  })
  const { data: plugins } = useQuery({
    queryKey: sourceKeys.plugins,
    queryFn: sourceApi.listPlugins,
  })

  const del = useMutation({
    mutationFn: sourceApi.delete,
    onSuccess: () => {
      toast.success('已删除')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'sources', 'list'] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      sourceApi.update(id, { enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'sources'] })
    },
  })

  const runNow = useMutation({
    mutationFn: sourceApi.runNow,
    onSuccess: (data) => {
      toast.success(`任务已提交 (${data.taskId ?? data.status})`)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'sources'] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  return (
    <div className="mx-auto max-w-6xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">采集源管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          采集器插件由代码注册（新增 1 个 = 新增 1 个文件 + 打 @register_plugin）
        </p>
      </header>

      <SourceEditor
        open={!!editing}
        plugins={plugins ?? []}
        editingId={editing?.id ?? null}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          void queryClient.invalidateQueries({ queryKey: ['admin', 'sources'] })
        }}
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Input
            placeholder="搜索名称"
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value)
              setPage(1)
            }}
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabledOnly}
            onChange={(e) => setEnabledOnly(e.target.checked)}
          />
          只看启用中
        </label>
        <div className="ml-auto flex gap-2">
          <Button onClick={() => setEditing({ id: null })}>+ 新建采集源</Button>
        </div>
      </div>

      {error && <Alert variant="error">{(error as ApiError).message}</Alert>}

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">名称 / 插件</th>
                <th className="px-4 py-3 font-medium">区域</th>
                <th className="px-4 py-3 font-medium">分类</th>
                <th className="px-4 py-3 font-medium">cron</th>
                <th className="px-4 py-3 font-medium">权重</th>
                <th className="px-4 py-3 font-medium">启用</th>
                <th className="px-4 py-3 font-medium">最后状态</th>
                <th className="px-4 py-3 font-medium">连续失败</th>
                <th className="px-4 py-3 font-medium">今日数</th>
                <th className="px-4 py-3 font-medium text-right" />
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td colSpan={10} className="px-4 py-3">
                      <div className="h-5 animate-pulse rounded bg-muted" />
                    </td>
                  </tr>
                ))}

              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center text-muted-foreground">
                    还没有采集源
                  </td>
                </tr>
              )}

              {data?.items.map((s) => (
                <SourceRow
                  key={s.id}
                  source={s}
                  busy={toggle.isPending || runNow.isPending}
                  rowWarning={s.consecutiveFails >= 3}
                  onEdit={() => setEditing({ id: s.id })}
                  onDelete={() => {
                    if (window.confirm(`确定删除采集源「${s.name}」？`)) {
                      del.mutate(s.id)
                    }
                  }}
                  onToggle={(enabled) => toggle.mutate({ id: s.id, enabled })}
                  onRun={() => runNow.mutate(s.id)}
                  onLogs={() => setLogsSourceId(s.id)}
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

      <TestRunDrawer onClose={() => setEditing(null)} />
      <LogsDrawer sourceId={logsSourceId} onClose={() => setLogsSourceId(null)} />
    </div>
  )
}

function SourceRow({
  source,
  busy,
  rowWarning,
  onEdit,
  onDelete,
  onToggle,
  onRun,
  onLogs,
}: {
  source: SourceItem
  busy: boolean
  rowWarning: boolean
  onEdit: () => void
  onDelete: () => void
  onToggle: (enabled: boolean) => void
  onRun: () => void
  onLogs: () => void
}) {
  return (
    <tr className={cn('border-b border-border last:border-0', rowWarning && 'bg-amber-50/50 dark:bg-amber-950/20')}>
      <td className="px-4 py-3">
        <div className="font-medium">{source.name}</div>
        <div className="text-xs text-muted-foreground">{source.pluginKey}</div>
      </td>
      <td className="px-4 py-3">
        <Badge variant="outline">{source.region}</Badge>
      </td>
      <td className="px-4 py-3">
        <Badge variant="outline">{source.category}</Badge>
      </td>
      <td className="px-4 py-3 font-mono text-xs">{source.cron}</td>
      <td className="px-4 py-3 text-center">{source.weight}</td>
      <td className="px-4 py-3">
        <label>
          <input
            type="checkbox"
            checked={source.enabled}
            disabled={busy}
            onChange={(e) => onToggle(e.target.checked)}
          />
        </label>
      </td>
      <td className="px-4 py-3">
        {source.lastRunStatus ? (
          <Badge variant={statusBadge[source.lastRunStatus]}>
            {statusLabel[source.lastRunStatus]}
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        {source.consecutiveFails > 0 ? (
          <span
            className={cn(
              'font-mono text-xs',
              source.consecutiveFails >= 5 ? 'text-red-600 font-semibold' : 'text-amber-600',
            )}
          >
            {source.consecutiveFails}
            {source.consecutiveFails >= 5 && (
              <span className="ml-1 text-xs text-red-600">→ 自动禁用</span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground">0</span>
        )}
      </td>
      <td className="px-4 py-3 text-center text-muted-foreground">{source.todayCount}</td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="outline" disabled={busy} onClick={onRun}>
            运行
          </Button>
          <Button size="sm" variant="ghost" onClick={onLogs}>
            日志
          </Button>
          <Button size="sm" variant="ghost" onClick={onEdit}>
            编辑
          </Button>
          <Button size="sm" variant="destructive" onClick={onDelete}>
            删除
          </Button>
        </div>
      </td>
    </tr>
  )
}

function SourceEditor({
  open,
  plugins,
  editingId,
  onClose,
  onSaved,
}: {
  open: boolean
  plugins: { pluginKey: string; displayName: string; region: Region; category: SourceCategory; defaultCron: string; defaultWeight: number; implemented: boolean }[]
  editingId: number | null
  onClose: () => void
  onSaved: () => void
}) {
  const queryClient = useQueryClient()
  const { data: detail } = useQuery({
    queryKey: ['admin', 'source', editingId],
    queryFn: () => sourceApi.get(editingId!),
    enabled: open && editingId !== null,
  })

  const [form, setForm] = useState<{
    pluginKey: string
    name: string
    region: Region
    category: SourceCategory
    homeUrl: string
    cron: string
    weight: number
    enabled: boolean
  }>({
    pluginKey: '',
    name: '',
    region: 'GLOBAL',
    category: 'NEWS',
    homeUrl: '',
    cron: '',
    weight: 5,
    enabled: false,
  })

  // 编辑时拉详情填充
  if (editingId && detail && form.name === '' && form.pluginKey === '') {
    setForm({
      pluginKey: detail.pluginKey,
      name: detail.name,
      region: detail.region,
      category: detail.category,
      homeUrl: detail.homeUrl ?? '',
      cron: detail.cron,
      weight: detail.weight,
      enabled: detail.enabled,
    })
  }

  const create = useMutation({
    mutationFn: sourceApi.create,
    onSuccess: () => {
      toast.success('已创建')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'sources'] })
      onSaved()
    },
    onError: (e) => toast.error((e as ApiError).message),
  })
  const update = useMutation({
    mutationFn: (data: Parameters<typeof sourceApi.update>[1]) =>
      sourceApi.update(editingId!, data),
    onSuccess: () => {
      toast.success('已保存')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'sources'] })
      void queryClient.invalidateQueries({ queryKey: ['admin', 'source', editingId] })
      onSaved()
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  if (!open) return null

  const selectPlugin = (key: string) => {
    const p = plugins.find((x) => x.pluginKey === key)
    if (!p) {
      setForm((f) => ({ ...f, pluginKey: key }))
      return
    }
    setForm((f) => ({
      ...f,
      pluginKey: key,
      region: p.region,
      category: p.category,
      cron: p.defaultCron,
      weight: p.defaultWeight,
    }))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-6">
      <Card className="w-full max-w-2xl">
        <CardContent className="space-y-4 p-6">
          <h3 className="text-lg font-semibold">
            {editingId ? '编辑采集源' : '新建采集源'}
          </h3>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>插件</Label>
              <Select
                value={form.pluginKey}
                onChange={(e) => selectPlugin(e.target.value)}
                disabled={!!editingId}
              >
                <option value="">— 选择 —</option>
                {plugins.map((p) => (
                  <option key={p.pluginKey} value={p.pluginKey} disabled={!p.implemented}>
                    {p.displayName} {p.implemented ? '' : '(未实现)'}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>名称</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Hacker News"
              />
            </div>
            <div className="space-y-1.5">
              <Label>区域</Label>
              <Select
                value={form.region}
                onChange={(e) => setForm((f) => ({ ...f, region: e.target.value as Region }))}
              >
                <option value="GLOBAL">GLOBAL</option>
                <option value="CN">CN</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>分类</Label>
              <Select
                value={form.category}
                onChange={(e) =>
                  setForm((f) => ({ ...f, category: e.target.value as SourceCategory }))
                }
              >
                <option value="NEWS">NEWS</option>
                <option value="CODE">CODE</option>
                <option value="PAPER">PAPER</option>
                <option value="PRODUCT">PRODUCT</option>
                <option value="BLOG">BLOG</option>
                <option value="MODEL">MODEL</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>cron（5 段）</Label>
              <Input
                value={form.cron}
                onChange={(e) => setForm((f) => ({ ...f, cron: e.target.value }))}
                placeholder="0 * * * *"
              />
            </div>
            <div className="space-y-1.5">
              <Label>权重 (1-10)</Label>
              <Input
                type="number"
                min="1"
                max="10"
                value={form.weight}
                onChange={(e) => setForm((f) => ({ ...f, weight: Number(e.target.value) }))}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>主页 URL</Label>
            <Input
              value={form.homeUrl}
              onChange={(e) => setForm((f) => ({ ...f, homeUrl: e.target.value }))}
              placeholder="https://news.ycombinator.com"
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
            />
            启用此采集源
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button
              loading={create.isPending || update.isPending}
              disabled={!form.pluginKey || !form.name || !form.cron}
              onClick={() => {
                const body: Parameters<typeof sourceApi.create>[0] = {
                  pluginKey: form.pluginKey,
                  name: form.name,
                  region: form.region,
                  category: form.category,
                  cron: form.cron,
                  weight: form.weight,
                  enabled: form.enabled,
                  ...(form.homeUrl ? { homeUrl: form.homeUrl } : {}),
                }
                if (editingId) {
                  update.mutate(body)
                } else {
                  create.mutate(body)
                }
              }}
            >
              {editingId ? '保存' : '创建'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function TestRunDrawer(_: { onClose: () => void }): null {
  // 占位：试跑功能通过后端 sourceApi.test 调用，UI 上点击"运行"按钮直接显示 toast
  return null
}

function LogsDrawer({
  sourceId,
  onClose,
}: {
  sourceId: number | null
  onClose: () => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: sourceKeys.logs(sourceId ?? 0),
    queryFn: () => sourceApi.listLogs(sourceId!, { page: 1, size: 50 }),
    enabled: sourceId !== null,
    refetchInterval: 5000,
  })

  if (sourceId === null) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="flex w-full max-w-2xl flex-col bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold">运行日志</h3>
            <p className="text-xs text-muted-foreground">
              source #{sourceId} · 共 {data?.total ?? 0} 条
              <span className="ml-2 text-muted-foreground/60">5 秒自动刷新</span>
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {isLoading && (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-16 animate-pulse rounded bg-muted" />
              ))}
            </div>
          )}

          {!isLoading && (data?.items.length ?? 0) === 0 && (
            <div className="py-12 text-center text-sm text-muted-foreground">
              还没有运行记录
            </div>
          )}

          <div className="space-y-3">
            {data?.items.map((log) => (
              <LogEntry key={log.id} log={log} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function LogEntry({ log }: { log: import('@/features/admin/api/source').RunLog }) {
  const statusBadge: Record<RunStatus, 'success' | 'warning' | 'danger' | 'outline'> = {
    SUCCESS: 'success',
    PARTIAL: 'warning',
    FAILED: 'danger',
    RUNNING: 'outline',
  }
  const statusLabel: Record<RunStatus, string> = {
    SUCCESS: '成功',
    PARTIAL: '部分',
    FAILED: '失败',
    RUNNING: '运行中',
  }
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant={statusBadge[log.status]}>{statusLabel[log.status]}</Badge>
          <Badge variant="outline">{log.triggerType === 'MANUAL' ? '手动' : '计划'}</Badge>
          <span className="text-xs text-muted-foreground">#{log.id}</span>
        </div>
        <div className="text-xs text-muted-foreground">
          {new Date(log.startedAt).toLocaleString('zh-CN')}
        </div>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-3 text-sm">
        <div>
          <div className="text-xs text-muted-foreground">抓取 / 新增</div>
          <div className="font-mono">
            {log.fetchedCount} / {log.newCount}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">耗时</div>
          <div className="font-mono">{log.durationMs ? `${(log.durationMs / 1000).toFixed(2)}s` : '—'}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Celery Task</div>
          <div className="truncate font-mono text-xs">{log.taskId ?? '—'}</div>
        </div>
      </div>
      {log.errorMessage && (
        <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted/50 p-2 text-xs text-red-600 dark:text-red-400">
          {log.errorMessage}
        </pre>
      )}
    </div>
  )
}
