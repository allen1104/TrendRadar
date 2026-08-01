import { useState } from 'react'
import { format, formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { Loader2, Play, RotateCcw } from 'lucide-react'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { toast } from '@/components/ui/toast'
import {
  type TaskDefinitionItem,
  type TaskRunLogItem,
} from '@/features/admin/api/admin'
import {
  useRetryTask,
  useTaskDefinitions,
  useTaskLog,
  useTaskLogs,
  useTriggerTask,
} from '@/features/admin/hooks/useAdmin'

type Tab = 'definitions' | 'logs'

export function AdminTasksPage() {
  const [tab, setTab] = useState<Tab>('definitions')

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">任务监控</h1>

      <div className="flex gap-1 rounded-lg bg-muted p-1">
        <button
          type="button"
          onClick={() => setTab('definitions')}
          className={`rounded-md px-4 py-1.5 text-sm transition-colors ${
            tab === 'definitions' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'
          }`}
        >
          任务定义
        </button>
        <button
          type="button"
          onClick={() => setTab('logs')}
          className={`rounded-md px-4 py-1.5 text-sm transition-colors ${
            tab === 'logs' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'
          }`}
        >
          运行日志
        </button>
      </div>

      {tab === 'definitions' ? <DefinitionsTab /> : <LogsTab />}
    </div>
  )
}

function DefinitionsTab() {
  const { data, isPending } = useTaskDefinitions()
  const trigger = useTriggerTask()

  if (isPending) return <div className="text-muted-foreground">加载中…</div>

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {data?.map((t) => (
        <DefinitionCard key={t.taskName} item={t} onTrigger={() => triggerNow(t, trigger)} />
      ))}
    </div>
  )
}

function triggerNow(t: TaskDefinitionItem, trigger: ReturnType<typeof useTriggerTask>) {
  if (!t.manualTriggerable) {
    toast.error('该任务不支持手动触发')
    return
  }
  if (t.isRunning) {
    toast.error('任务正在运行')
    return
  }
  trigger.mutate(
    { taskName: t.taskName },
    {
      onSuccess: (r) => toast.success(`已触发，taskId=${r.taskId.slice(0, 8)}…`),
      onError: (e: unknown) => {
        const err = e as { detail?: string }
        toast.error(err?.detail ?? '触发失败')
      },
    },
  )
}

function DefinitionCard({
  item,
  onTrigger,
}: {
  item: TaskDefinitionItem
  onTrigger: () => void
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <h3 className="truncate font-medium">{item.displayName}</h3>
          <code className="text-xs text-muted-foreground">{item.taskName}</code>
        </div>
        {item.isRunning && <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden />}
      </div>
      <dl className="mt-3 space-y-1 text-xs text-muted-foreground">
        <div className="flex justify-between">
          <dt>cron</dt>
          <dd className="font-mono">{item.cron ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt>最近运行</dt>
          <dd>
            {item.lastRunAt ? formatDistanceToNow(new Date(item.lastRunAt), { addSuffix: true, locale: zhCN }) : '—'}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt>状态</dt>
          <dd>
            {item.lastRunStatus ? (
              <Badge variant={item.lastRunStatus === 'SUCCESS' ? 'success' : item.lastRunStatus === 'FAILED' ? 'danger' : 'outline'}>
                {item.lastRunStatus}
              </Badge>
            ) : (
              '—'
            )}
          </dd>
        </div>
      </dl>
      <div className="mt-3 flex justify-end">
        <Button size="sm" disabled={!item.manualTriggerable || item.isRunning} onClick={onTrigger}>
          <Play className="mr-1 h-3 w-3" /> 立即执行
        </Button>
      </div>
    </Card>
  )
}

function LogsTab() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const { data, isPending } = useTaskLogs({
    page,
    size: 20,
    ...(statusFilter ? { status: statusFilter as TaskRunLogItem['status'] } : {}),
  })
  const [selectedId, setSelectedId] = useState<number | null>(null)

  if (isPending) return <div className="text-muted-foreground">加载中…</div>

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(1)
          }}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">全部状态</option>
          <option value="RUNNING">RUNNING</option>
          <option value="SUCCESS">SUCCESS</option>
          <option value="FAILED">FAILED</option>
          <option value="RETRYING">RETRYING</option>
          <option value="SKIPPED">SKIPPED</option>
        </select>
      </div>

      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">任务</th>
              <th className="px-3 py-2 text-left font-medium">触发</th>
              <th className="px-3 py-2 text-left font-medium">状态</th>
              <th className="px-3 py-2 text-right font-medium">耗时</th>
              <th className="px-3 py-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((r) => (
              <tr
                key={r.id}
                onClick={() => setSelectedId(r.id)}
                className="cursor-pointer border-t border-border hover:bg-muted/30"
              >
                <td className="px-3 py-2">{r.taskName}</td>
                <td className="px-3 py-2">
                  <Badge variant="outline">{r.triggerType}</Badge>
                </td>
                <td className="px-3 py-2">
                  <Badge
                    variant={
                      r.status === 'SUCCESS'
                        ? 'success'
                        : r.status === 'FAILED'
                          ? 'danger'
                          : r.status === 'RUNNING'
                            ? 'warning'
                            : 'outline'
                    }
                  >
                    {r.status}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {r.durationMs != null ? `${r.durationMs}ms` : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  {r.status === 'FAILED' && <RetryButton runId={r.id} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* 分页 */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            上一页
          </Button>
          <span className="tabular-nums">
            {data.page} / {data.pages} 页
          </span>
          <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>
            下一页
          </Button>
        </div>
      )}

      {selectedId !== null && <LogDetailDrawer runId={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  )
}

function RetryButton({ runId }: { runId: number }) {
  const retry = useRetryTask()
  return (
    <Button
      size="sm"
      variant="outline"
      onClick={(e) => {
        e.stopPropagation()
        retry.mutate(runId, {
          onSuccess: () => toast.success('已重新投递'),
          onError: (err: unknown) => {
            const e = err as { detail?: string }
            toast.error(e?.detail ?? '重试失败')
          },
        })
      }}
    >
      <RotateCcw className="mr-1 h-3 w-3" /> 重试
    </Button>
  )
}

function LogDetailDrawer({ runId, onClose }: { runId: number; onClose: () => void }) {
  const { data, isPending } = useTaskLog(runId)

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-[480px] overflow-y-auto border-l border-border bg-background shadow-xl">
      <div className="flex items-center justify-between border-b border-border p-4">
        <h2 className="font-semibold">任务日志 #{runId}</h2>
        <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
          ✕
        </button>
      </div>
      <div className="space-y-4 p-4">
        {isPending && <div className="text-muted-foreground">加载中…</div>}
        {data && (
          <>
            <Field label="任务">{data.taskName}</Field>
            <Field label="触发">{data.triggerType}</Field>
            <Field label="状态">
              <Badge>{data.status}</Badge>
            </Field>
            {data.startedAt && <Field label="开始">{format(new Date(data.startedAt), 'yyyy-MM-dd HH:mm:ss')}</Field>}
            {data.finishedAt && <Field label="结束">{format(new Date(data.finishedAt), 'yyyy-MM-dd HH:mm:ss')}</Field>}
            {data.durationMs != null && <Field label="耗时">{data.durationMs}ms</Field>}
            <div>
              <p className="mb-1 text-xs text-muted-foreground">入参</p>
              <pre className="rounded bg-muted p-2 text-xs">{JSON.stringify(data.argsSummary, null, 2)}</pre>
            </div>
            {data.resultSummary && (
              <div>
                <p className="mb-1 text-xs text-muted-foreground">结果</p>
                <pre className="rounded bg-muted p-2 text-xs">{JSON.stringify(data.resultSummary, null, 2)}</pre>
              </div>
            )}
            {data.errorMessage && (
              <Alert variant="error">
                <p className="mb-1 font-semibold">错误</p>
                <p className="text-xs">{data.errorMessage}</p>
                {data.traceback && (
                  <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-2 text-xs">{data.traceback}</pre>
                )}
              </Alert>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-16 text-xs text-muted-foreground">{label}</span>
      <span>{children}</span>
    </div>
  )
}