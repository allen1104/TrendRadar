/** KeywordDetailPage：单关键词下钻曲线 + 共现词 + 相关事件。*/

import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { Alert } from '@/components/ui/alert'
import { Card } from '@/components/ui/card'

import { useKeywordDetail } from '@/features/trend'
import type { TrendWindow } from '@/features/trend/api/trend'

function parseWindow(raw: string | null): TrendWindow {
  if (raw === '30D' || raw === '1Y') return raw
  return '7D'
}

const WINDOWS: { value: TrendWindow; label: string }[] = [
  { value: '7D', label: '最近 7 天' },
  { value: '30D', label: '最近 30 天' },
  { value: '1Y', label: '最近一年' },
]

export function KeywordDetailPage() {
  const { keyword = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const window = parseWindow(search.get('window'))

  const q = useKeywordDetail(keyword, window)
  const setWindow = (w: TrendWindow) => {
    const next = new URLSearchParams(search)
    next.set('window', w)
    setSearch(next, { replace: true })
  }

  const seriesOption = useMemo(() => {
    if (!q.data) return {}
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['事件数', '文章数', '热度'] },
      grid: { left: 40, right: 40, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: q.data.series.map((p) => p.date) },
      yAxis: [
        { type: 'value', name: '事件/文章' },
        { type: 'value', name: '热度', position: 'right' },
      ],
      series: [
        {
          name: '事件数',
          type: 'line',
          smooth: true,
          data: q.data.series.map((p) => p.eventCount),
        },
        {
          name: '文章数',
          type: 'line',
          smooth: true,
          data: q.data.series.map((p) => p.articleCount ?? 0),
        },
        {
          name: '热度',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          data: q.data.series.map((p) => p.heatSum ?? 0),
        },
      ],
    }
  }, [q.data])

  if (q.isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-4">
        <Card className="h-12" />
        <Card className="h-72" />
      </div>
    )
  }

  if (q.isError) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-4">
        <Link to="/trends" className="text-sm text-primary hover:underline">
          ← 返回趋势
        </Link>
        <Alert>暂无数据或关键词不存在</Alert>
      </div>
    )
  }

  if (q.isError || !q.data) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-4">
        <Link to="/trends" className="text-sm text-primary hover:underline">
          ← 返回趋势
        </Link>
        <Alert>暂无数据或关键词不存在</Alert>
      </div>
    )
  }

  const { displayName, growthRate, relatedKeywords, topEvents } = q.data

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      <Link to="/trends" className="text-sm text-primary hover:underline">
        ← 返回趋势
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{displayName}</h1>
          <div className="mt-1 text-sm text-muted-foreground">
            增长率{' '}
            <span
              className={
                growthRate >= 0 ? 'text-green-600' : 'text-red-600'
              }
            >
              {(growthRate * 100).toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              onClick={() => setWindow(w.value)}
              className={`rounded-md px-3 py-1 text-sm transition-colors ${
                window === w.value
                  ? 'bg-background font-medium shadow'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <Card className="p-6">
        <h3 className="mb-4 text-sm font-medium text-muted-foreground">趋势曲线</h3>
        <ReactECharts option={seriesOption} style={{ height: 320 }} />
      </Card>

      {relatedKeywords.length > 0 && (
        <Card className="p-6">
          <h3 className="mb-4 text-sm font-medium text-muted-foreground">
            共现关键词
          </h3>
          <div className="flex flex-wrap gap-2">
            {relatedKeywords.map((rk) => (
              <Link
                key={rk.displayName}
                to={`/trends/${encodeURIComponent(rk.displayName)}`}
                className="rounded-full border bg-muted px-3 py-1 text-xs hover:border-primary"
              >
                {rk.displayName} · {rk.coOccurrence}
              </Link>
            ))}
          </div>
        </Card>
      )}

      {topEvents.length > 0 && (
        <Card className="p-6">
          <h3 className="mb-4 text-sm font-medium text-muted-foreground">
            相关热点事件
          </h3>
          <ul className="space-y-3">
            {topEvents.map((ev) => (
              <li key={ev.id} className="border-b pb-2 last:border-0">
                <Link
                  to={`/events/${ev.id}`}
                  className="font-medium hover:text-primary"
                >
                  {ev.title}
                </Link>
                <div className="mt-1 text-xs text-muted-foreground">
                  推荐指数 {ev.recommendIndex.toFixed(1)}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
