/** TrendPage：趋势分析 4 屏（总览 / 关键词 / 实体 / 词云）+ URL 同步窗口。*/

import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'

import {
  type EntityTrendItem,
  type KeywordTrendItem,
  type TrendWindow,
  useEntityTrends,
  useKeywordTrends,
  useOverview,
  useWordCloud,
} from '@/features/trend'

const WINDOWS: { value: TrendWindow; label: string }[] = [
  { value: '7D', label: '最近 7 天' },
  { value: '30D', label: '最近 30 天' },
  { value: '1Y', label: '最近一年' },
]

function parseWindow(raw: string | null): TrendWindow {
  if (raw === '30D' || raw === '1Y') return raw
  return '7D'
}

export function TrendPage() {
  const [search, setSearch] = useSearchParams()
  const window = parseWindow(search.get('window'))
  const setWindow = (w: TrendWindow) => {
    const next = new URLSearchParams(search)
    next.set('window', w)
    setSearch(next, { replace: true })
  }

  const overviewQ = useOverview(window)
  const keywordsQ = useKeywordTrends(window, 'GROWTH', 20)
  const entitiesQ = useEntityTrends(window, 'COMPANY', 20)
  const wordcloudQ = useWordCloud(window, 100, 'ALL')

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4">
      {/* 顶部 Tab */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">趋势分析</h1>
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              onClick={() => setWindow(w.value)}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
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

      {/* 第一屏 · 总览 */}
      <OverviewSection data={overviewQ.data} isLoading={overviewQ.isLoading} />

      {/* 第二屏 · 关键词趋势 */}
      <Card className="p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">关键词趋势</h2>
          <span className="text-xs text-muted-foreground">增长最快</span>
        </div>
        <KeywordList items={keywordsQ.data?.items ?? []} isLoading={keywordsQ.isLoading} />
        {keywordsQ.data?.newcomers && keywordsQ.data.newcomers.length > 0 && (
          <div className="mt-4 border-t pt-4">
            <div className="mb-2 text-sm font-medium text-muted-foreground">
              🆕 新出现（growth ≥ 3 且 previous=0）
            </div>
            <div className="flex flex-wrap gap-2">
              {keywordsQ.data.newcomers.slice(0, 10).map((it) => (
                <Badge key={it.keyword} variant="outline">
                  {it.displayName} · {it.current}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* 第三屏 · 实体排行 */}
      <Card className="p-6">
        <h2 className="mb-4 text-lg font-semibold">最热门公司</h2>
        <EntityBarChart items={entitiesQ.data?.items ?? []} isLoading={entitiesQ.isLoading} />
      </Card>

      {/* 第四屏 · 词云 */}
      <Card className="p-6">
        <h2 className="mb-4 text-lg font-semibold">词云</h2>
        <WordCloudChart items={wordcloudQ.data?.items ?? []} isLoading={wordcloudQ.isLoading} />
      </Card>
    </div>
  )
}

// ============================================================ Overview


function OverviewSection({
  data,
  isLoading,
}: {
  data: ReturnType<typeof useOverview>['data']
  isLoading: boolean
}) {
  const eventLineOption = useMemo(() => {
    if (!data) return {}
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 40, top: 20, bottom: 30 },
      xAxis: {
        type: 'category',
        data: data.dailySeries.map((p) => p.date),
      },
      yAxis: [
        { type: 'value', name: '事件数', position: 'left' },
        {
          type: 'value',
          name: '平均推荐',
          position: 'right',
          min: 0,
          max: 100,
        },
      ],
      series: [
        {
          type: 'line',
          data: data.dailySeries.map((p) => p.eventCount),
          areaStyle: { opacity: 0.3 },
          smooth: true,
          name: '事件数',
        },
        {
          type: 'line',
          yAxisIndex: 1,
          data: data.dailySeries.map((p) => p.avgRecommend ?? 0),
          smooth: true,
          name: '平均推荐',
          lineStyle: { type: 'dashed' },
        },
      ],
    }
  }, [data])

  const categoryOption = useMemo(() => {
    if (!data) return {}
    return {
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          data: data.categoryDistribution.map((c) => ({
            name: c.category,
            value: c.count,
          })),
          label: { formatter: '{b}: {c} ({d}%)' },
        },
      ],
    }
  }, [data])

  const regionOption = useMemo(() => {
    if (!data) return {}
    return {
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: '70%',
          data: data.regionDistribution.map((r) => ({
            name: r.region,
            value: r.count,
          })),
        },
      ],
    }
  }, [data])

  if (isLoading) {
    return (
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="h-24 p-4" />
        ))}
      </div>
    )
  }

  if (!data) return <Alert>暂无数据</Alert>

  const { summary, topRisingKeywords, topCompanies, topProjects } = data

  return (
    <div className="space-y-4">
      {/* 4 个指标卡 */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard title="总事件数" value={summary.totalEvents} />
        <MetricCard title="总文章数" value={summary.totalArticles} />
        <MetricCard
          title="日均事件"
          value={summary.avgEventsPerDay.toFixed(1)}
        />
        <MetricCard
          title="环比增长"
          value={`${(summary.eventGrowthRate * 100).toFixed(1)}%`}
          trend={summary.eventGrowthRate}
        />
      </div>

      {/* 大图 */}
      <Card className="p-6">
        <h3 className="mb-4 text-sm font-medium text-muted-foreground">每日事件量趋势</h3>
        <ReactECharts option={eventLineOption} style={{ height: 280 }} />
      </Card>

      {/* 分类 + 区域 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="p-6">
          <h3 className="mb-4 text-sm font-medium text-muted-foreground">分类分布</h3>
          <ReactECharts option={categoryOption} style={{ height: 240 }} />
        </Card>
        <Card className="p-6">
          <h3 className="mb-4 text-sm font-medium text-muted-foreground">区域分布</h3>
          <ReactECharts option={regionOption} style={{ height: 240 }} />
        </Card>
      </div>

      {/* Top 列表 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <TopListCard title="上升最快关键词" items={topRisingKeywords} />
        <TopListCard title="最热门公司" items={topCompanies} />
        <TopListCard title="最热门项目" items={topProjects} />
      </div>
    </div>
  )
}

function MetricCard({
  title,
  value,
  trend,
}: {
  title: string
  value: string | number
  trend?: number
}) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className="mt-2 text-2xl font-bold">{value}</div>
      {trend !== undefined && (
        <div
          className={`mt-1 text-xs ${trend >= 0 ? 'text-green-600' : 'text-red-600'}`}
        >
          {trend >= 0 ? '↑' : '↓'} {Math.abs(trend * 100).toFixed(1)}%
        </div>
      )}
    </Card>
  )
}

function TopListCard({
  title,
  items,
}: {
  title: string
  items: { displayName: string; growthRate: number; current: number | null }[]
}) {
  return (
    <Card className="p-6">
      <h3 className="mb-4 text-sm font-medium text-muted-foreground">{title}</h3>
      <ul className="space-y-2">
        {items.map((it, i) => (
          <li key={`${it.displayName}-${i}`} className="flex items-center justify-between text-sm">
            <span className="flex-1 truncate">
              {i + 1}. {it.displayName}
            </span>
            <span
              className={`text-xs ${
                it.growthRate >= 0 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {(it.growthRate * 100).toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

// ============================================================ Keywords


function KeywordList({
  items,
  isLoading,
}: {
  items: KeywordTrendItem[]
  isLoading: boolean
}) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i} className="h-12" />
        ))}
      </div>
    )
  }
  if (items.length === 0) {
    return <Alert>当前窗口暂无关键词数据</Alert>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-12 py-2">#</th>
            <th>关键词</th>
            <th className="w-20 text-right">当前</th>
            <th className="w-20 text-right">环比</th>
            <th className="w-20 text-right">热度</th>
            <th className="w-32">趋势</th>
            <th className="w-20">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={it.keyword} className="border-b last:border-0">
              <td className="py-2 text-muted-foreground">{i + 1}</td>
              <td className="font-medium">{it.displayName}</td>
              <td className="text-right">{it.current}</td>
              <td
                className={`text-right ${
                  it.growthRate >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {(it.growthRate * 100).toFixed(0)}%
              </td>
              <td className="text-right">{it.heatSum.toFixed(0)}</td>
              <td>
                <MiniSpark
                  points={it.series.map((p) => p.eventCount)}
                  positive={it.growthRate >= 0}
                />
              </td>
              <td>
                <Link
                  to={`/trends/${encodeURIComponent(it.keyword)}?window=${window_default(it)}`}
                  className="text-xs text-primary hover:underline"
                >
                  详情
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function window_default(_it: KeywordTrendItem): string {
  // 占位：详情页自己从 URL 拿
  return '7D'
}

function MiniSpark({ points, positive }: { points: number[]; positive: boolean }) {
  const option = useMemo(() => {
    return {
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: 'category', show: false, data: points.map((_, i) => i) },
      yAxis: { type: 'value', show: false },
      series: [
        {
          type: 'line',
          data: points,
          smooth: true,
          showSymbol: false,
          lineStyle: {
            color: positive ? '#16a34a' : '#dc2626',
            width: 1.5,
          },
        },
      ],
    }
  }, [points, positive])
  return <ReactECharts option={option} style={{ height: 28, width: 100 }} />
}

// ============================================================ Entities


function EntityBarChart({
  items,
  isLoading,
}: {
  items: EntityTrendItem[]
  isLoading: boolean
}) {
  const option = useMemo(() => {
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 80, right: 40, top: 20, bottom: 30 },
      xAxis: { type: 'value' },
      yAxis: {
        type: 'category',
        data: items.map((it) => it.displayName).reverse(),
      },
      series: [
        {
          type: 'bar',
          data: items.map((it) => it.heatSum).reverse(),
          itemStyle: { color: '#3b82f6' },
        },
      ],
    }
  }, [items])

  if (isLoading) return <Card className="h-64" />
  if (items.length === 0) return <Alert>暂无实体数据</Alert>
  return <ReactECharts option={option} style={{ height: 360 }} />
}

// ============================================================ WordCloud


function WordCloudChart({
  items,
  isLoading,
}: {
  items: { text: string; value: number; growthRate: number | null }[]
  isLoading: boolean
}) {
  const option = useMemo(() => {
    return {
      tooltip: { show: true },
      series: [
        {
          type: 'wordCloud',
          shape: 'circle',
          sizeRange: [14, 56],
          rotationRange: [-45, 45],
          gridSize: 8,
          drawOutOfBound: false,
          textStyle: {
            fontFamily: 'sans-serif',
            fontWeight: 'bold',
            color: () => {
              const colors = ['#dc2626', '#ea580c', '#16a34a', '#0284c7', '#7c3aed']
              return colors[Math.floor(Math.random() * colors.length)]
            },
          },
          data: items.map((it) => ({
            name: it.text,
            value: it.value,
          })),
        },
      ],
    }
  }, [items])

  if (isLoading) return <Card className="h-72" />
  if (items.length === 0) return <Alert>暂无词云数据</Alert>
  return <ReactECharts option={option} style={{ height: 320 }} />
}
