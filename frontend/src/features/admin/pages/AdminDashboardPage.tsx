import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import ReactECharts from 'echarts-for-react'
import { Activity, AlertTriangle, Flame, Newspaper, Sparkles, Users } from 'lucide-react'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { useDashboard } from '@/features/admin/hooks/useAdmin'

export function AdminDashboardPage() {
  const { data, isPending, isError, error } = useDashboard()

  if (isPending) {
    return (
      <div className="mx-auto max-w-7xl animate-pulse p-6">
        <div className="h-8 w-1/3 rounded bg-muted" />
        <div className="mt-6 grid grid-cols-3 gap-4">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-28 rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <Alert variant="error" className="mx-auto max-w-3xl">
        加载失败：{error instanceof Error ? error.message : '未知错误'}
      </Alert>
    )
  }

  if (!data) return null

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">总览仪表盘</h1>

      {/* 告警横幅 */}
      {data.recentAlerts.length > 0 && (
        <Alert variant={data.aiCost.limitReached ? 'error' : 'info'}>
          <AlertTriangle className="mr-2 inline h-4 w-4" aria-hidden />
          {data.recentAlerts[0].message}
        </Alert>
      )}

      {/* 6 个指标卡 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <MetricCard icon={<Newspaper className="h-5 w-5" />} label="事件总数" value={data.overview.totalEvents} sub={`今日 +${data.overview.todayNewEvents}`} />
        <MetricCard icon={<Sparkles className="h-5 w-5" />} label="文章总数" value={data.overview.totalArticles} sub={`今日 +${data.overview.todayNewArticles}`} />
        <MetricCard icon={<Activity className="h-5 w-5" />} label="启用源数" value={data.overview.activeSources} />
        <MetricCard icon={<Users className="h-5 w-5" />} label="用户数" value={data.overview.totalUsers} />
        <MetricCard icon={<Flame className="h-5 w-5 text-orange-500" />} label="AI 今日费用" value={`$${data.aiCost.todayUsd.toFixed(2)}`} sub={`本月 $${data.aiCost.monthUsd.toFixed(2)} / 限额 $${data.aiCost.dailyLimitUsd}`} />
        <MetricCard
          icon={<AlertTriangle className="h-5 w-5" />}
          label="待处理事件"
          value={data.pipelineHealth.pendingAi + data.pipelineHealth.pendingClean + data.pipelineHealth.pendingEmbed}
          sub={`PENDING_AI ${data.pipelineHealth.pendingAi} · RAW ${data.pipelineHealth.pendingClean} · CLEANED ${data.pipelineHealth.pendingEmbed}`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 流水线漏斗 */}
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold">流水线漏斗</h2>
          <ReactECharts
            style={{ height: 280 }}
            notMerge
            lazyUpdate
            option={{
              tooltip: { trigger: 'item' },
              series: [
                {
                  type: 'funnel',
                  data: [
                    { name: 'RAW', value: data.pipelineHealth.articleByStatus.RAW ?? 0 },
                    { name: 'CLEANED', value: data.pipelineHealth.articleByStatus.CLEANED ?? 0 },
                    { name: 'EMBEDDED', value: data.pipelineHealth.articleByStatus.EMBEDDED ?? 0 },
                    { name: 'CLUSTERED', value: data.pipelineHealth.articleByStatus.CLUSTERED ?? 0 },
                    { name: 'ANALYZED', value: data.pipelineHealth.eventByStatus.ANALYZED ?? 0 },
                  ],
                },
              ],
            }}
          />
        </Card>

        {/* 7 日趋势 */}
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold">7 日趋势</h2>
          <ReactECharts
            style={{ height: 280 }}
            notMerge
            lazyUpdate
            option={{
              tooltip: { trigger: 'axis' },
              legend: { data: ['文章', '事件'] },
              grid: { left: 40, right: 50, top: 36, bottom: 28 },
              xAxis: { type: 'category', data: data.trend7d.map((p) => p.date.slice(5)) },
              yAxis: [{ type: 'value', name: '文章' }, { type: 'value', name: '费用 USD' }],
              series: [
                { name: '文章', type: 'bar', data: data.trend7d.map((p) => p.articles) },
                { name: '事件', type: 'line', smooth: true, data: data.trend7d.map((p) => p.events) },
              ],
            }}
          />
        </Card>
      </div>

      {/* 采集源状态 */}
      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold">采集源状态</h2>
        <table className="w-full text-sm">
          <thead className="text-muted-foreground">
            <tr>
              <th className="py-2 text-left font-medium">名称</th>
              <th className="py-2 text-left font-medium">启用</th>
              <th className="py-2 text-left font-medium">最后运行</th>
              <th className="py-2 text-left font-medium">状态</th>
              <th className="py-2 text-right font-medium">今日采集</th>
              <th className="py-2 text-right font-medium">连续失败</th>
            </tr>
          </thead>
          <tbody>
            {data.sourceStatus.map((s) => (
              <tr key={s.id} className="border-t border-border">
                <td className="py-2">{s.name}</td>
                <td className="py-2">{s.enabled ? '是' : '否'}</td>
                <td className="py-2 text-muted-foreground">
                  {s.lastRunAt ? formatDistanceToNow(new Date(s.lastRunAt), { addSuffix: true, locale: zhCN }) : '—'}
                </td>
                <td className="py-2">
                  <Badge variant={s.lastRunStatus === 'SUCCESS' ? 'success' : s.lastRunStatus === 'FAILED' ? 'danger' : 'outline'}>
                    {s.lastRunStatus ?? '—'}
                  </Badge>
                </td>
                <td className="py-2 text-right tabular-nums">{s.todayCount}</td>
                <td className="py-2 text-right tabular-nums">
                  {s.consecutiveFails >= 3 ? <span className="text-red-500">{s.consecutiveFails}</span> : s.consecutiveFails}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* 最近告警 */}
      {data.recentAlerts.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">最近告警</h2>
          <ul className="space-y-2 text-sm">
            {data.recentAlerts.map((a) => (
              <li key={a.id} className="flex items-center gap-2">
                <Badge variant={a.level === 'ERROR' ? 'danger' : 'warning'}>{a.level}</Badge>
                <span>{a.message}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {formatDistanceToNow(new Date(a.createdAt), { addSuffix: true, locale: zhCN })}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

function MetricCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode
  label: string
  value: number | string
  sub?: string
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
          {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
        </div>
        <div className="text-muted-foreground">{icon}</div>
      </div>
    </Card>
  )
}