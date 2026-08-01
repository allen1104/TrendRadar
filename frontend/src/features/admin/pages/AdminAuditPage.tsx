import { useState } from 'react'
import { format } from 'date-fns'
import { X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAuditLog, useAuditLogs } from '@/features/admin/hooks/useAdmin'
import type { AuditAction, AuditLogItem, TargetType } from '@/features/admin/api/admin'

const ACTION_LABEL: Record<string, string> = {
  EVENT_PIN: '事件置顶',
  EVENT_HIDE: '事件隐藏',
  EVENT_EDIT: '事件编辑',
  EVENT_SPLIT: '事件拆分',
  EVENT_MERGE: '事件合并',
  EVENT_REANALYZE: '事件重分析',
  SOURCE_CREATE: '新建采集源',
  SOURCE_UPDATE: '修改采集源',
  SOURCE_DELETE: '删除采集源',
  SOURCE_MANUAL_RUN: '手动触发采集',
  SOURCE_AUTO_DISABLED: '采集源自动禁用',
  PROVIDER_CREATE: '新建 Provider',
  PROVIDER_UPDATE: '修改 Provider',
  PROVIDER_DELETE: '删除 Provider',
  MODEL_CREATE: '新建模型',
  MODEL_UPDATE: '修改模型',
  MODEL_DELETE: '删除模型',
  PROMPT_CREATE: '新建 Prompt',
  PROMPT_ACTIVATE: '激活 Prompt',
  USER_ROLE_CHANGE: '修改用户角色',
  USER_STATUS_CHANGE: '修改用户状态',
  CONFIG_UPDATE: '修改系统配置',
  SYSTEM_ALERT: '系统告警',
  AI_DAILY_LIMIT_REACHED: 'AI 日限额触顶',
  SYSTEM_TASK_PAUSED: '系统任务暂停',
}

export function AdminAuditPage() {
  const [page, setPage] = useState(1)
  const [actionFilter, setActionFilter] = useState<string>('')
  const [targetFilter, setTargetFilter] = useState<string>('')
  const [userIdFilter, setUserIdFilter] = useState<string>('')
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const { data, isPending } = useAuditLogs({
    page,
    size: 20,
    ...(actionFilter ? { action: actionFilter as AuditAction } : {}),
    ...(targetFilter ? { targetType: targetFilter as TargetType } : {}),
    ...(userIdFilter ? { userId: Number(userIdFilter) } : {}),
  })

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">审计日志</h1>

      {/* 筛选 */}
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <Input
          placeholder="操作人 user_id"
          type="number"
          value={userIdFilter}
          onChange={(e) => {
            setUserIdFilter(e.target.value)
            setPage(1)
          }}
          className="w-32"
        />
        <select
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value)
            setPage(1)
          }}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">全部动作</option>
          {Object.entries(ACTION_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select
          value={targetFilter}
          onChange={(e) => {
            setTargetFilter(e.target.value)
            setPage(1)
          }}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">全部对象</option>
          {['EVENT', 'SOURCE', 'USER', 'PROMPT', 'MODEL', 'PROVIDER', 'CONFIG', 'SYSTEM'].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </Card>

      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">时间</th>
              <th className="px-3 py-2 text-left font-medium">操作人</th>
              <th className="px-3 py-2 text-left font-medium">动作</th>
              <th className="px-3 py-2 text-left font-medium">对象</th>
              <th className="px-3 py-2 text-left font-medium">ID</th>
              <th className="px-3 py-2 text-left font-medium">IP</th>
            </tr>
          </thead>
          <tbody>
            {isPending && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  加载中…
                </td>
              </tr>
            )}
            {data?.items.map((r) => (
              <tr key={r.id} onClick={() => setSelectedId(r.id)} className="cursor-pointer border-t border-border hover:bg-muted/30">
                <td className="px-3 py-2 text-xs">{format(new Date(r.createdAt), 'MM-dd HH:mm:ss')}</td>
                <td className="px-3 py-2">
                  {r.username ?? <span className="text-muted-foreground">系统</span>}
                  {r.userId && <span className="ml-1 text-xs text-muted-foreground">#{r.userId}</span>}
                </td>
                <td className="px-3 py-2">
                  <Badge variant="outline">{ACTION_LABEL[r.action] ?? r.action}</Badge>
                </td>
                <td className="px-3 py-2">{r.targetType}</td>
                <td className="px-3 py-2 text-xs">{r.targetId ?? '—'}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{r.ip ?? '—'}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  无匹配记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="rounded border border-border bg-background px-3 py-1 text-sm disabled:opacity-50"
          >
            上一页
          </button>
          <span className="tabular-nums">
            {data.page} / {data.pages} 页
          </span>
          <button
            type="button"
            disabled={page >= data.pages}
            onClick={() => setPage(page + 1)}
            className="rounded border border-border bg-background px-3 py-1 text-sm disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      )}

      {selectedId !== null && <AuditDetailDrawer id={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  )
}

function AuditDetailDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, isPending } = useAuditLog(id)

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-[520px] overflow-y-auto border-l border-border bg-background shadow-xl">
      <div className="flex items-center justify-between border-b border-border p-4">
        <h2 className="font-semibold">审计日志 #{id}</h2>
        <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-4 p-4 text-sm">
        {isPending && <div className="text-muted-foreground">加载中…</div>}
        {data && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <KV k="动作" v={ACTION_LABEL[data.action] ?? data.action} />
              <KV k="对象" v={`${data.targetType}${data.targetId ? ` #${data.targetId}` : ''}`} />
              <KV k="操作人" v={data.username ? `${data.username} #${data.userId}` : '系统'} />
              <KV k="时间" v={format(new Date(data.createdAt), 'yyyy-MM-dd HH:mm:ss')} />
              <KV k="IP" v={data.ip ?? '—'} />
              <KV k="trace_id" v={data.traceId ?? '—'} />
            </div>
            {data.note && <KV k="备注" v={data.note} />}

            <DiffBlock title="变更前" data={data.beforeValue} />
            <DiffBlock title="变更后" data={data.afterValue} />

            {data.userAgent && (
              <div>
                <p className="mb-1 text-xs text-muted-foreground">User-Agent</p>
                <pre className="rounded bg-muted p-2 text-xs break-all whitespace-pre-wrap">
                  {data.userAgent}
                </pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{k}</p>
      <p className="text-sm">{v}</p>
    </div>
  )
}

function DiffBlock({ title, data }: { title: string; data: Record<string, unknown> | null }) {
  return (
    <div>
      <p className="mb-1 text-xs text-muted-foreground">{title}</p>
      <pre className="max-h-72 overflow-auto rounded bg-muted p-2 text-xs">
        {data ? JSON.stringify(data, null, 2) : '（无）'}
      </pre>
    </div>
  )
}

// avoid unused-import warning on AuditLogItem
void ({} as AuditLogItem)