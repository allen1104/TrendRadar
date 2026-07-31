import ReactECharts from 'echarts-for-react'
import { format, formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import {
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  Flame,
  Loader2,
  Lock,
  Pin,
  XCircle,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toast'
import { hasRole, type Role } from '@/features/auth/types'
import type { EventDetail } from '@/features/hotspot/api/hotspot'
import {
  useEventDetail,
  useEventTrend,
  useRelatedEvents,
  useUnlockField,
  useUpdateEvent,
} from '@/features/hotspot/hooks/useHotspot'
import { useAuthStore } from '@/stores/authStore'

const REGION_LABEL: Record<string, string> = {
  GLOBAL: '全球',
  CN: '国内',
  MIXED: '全球+国内',
}

const MATCH_LEVEL_LABEL: Record<string, string> = {
  FINGERPRINT: '指纹',
  TITLE: '标题',
  VECTOR: '向量',
  MANUAL: '人工',
}

export function EventDetailPage() {
  const { id } = useParams<{ id: string }>()
  const eventId = Number(id)
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const role: Role = user?.role ?? 'GUEST'
  const isEditor = hasRole(role, 'EDITOR')

  const { data, isPending, isError, error } = useEventDetail(eventId, { pollWhilePending: true })
  const { data: trend } = useEventTrend(eventId)
  const { data: related } = useRelatedEvents(eventId)

  if (isPending) return <DetailSkeleton />

  if (isError) {
    const status = (error as { status?: number } | undefined)?.status
    if (status === 404) {
      return (
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-3 py-24 text-center">
          <p className="text-5xl font-bold text-muted-foreground">404</p>
          <p className="text-muted-foreground">事件不存在或已下架</p>
          <Button variant="outline" onClick={() => navigate('/')}>
            返回热点中心
          </Button>
        </div>
      )
    }
    return (
      <div className="mx-auto max-w-3xl p-6">
        <Alert variant="error">
          加载失败：{error instanceof Error ? error.message : '未知错误'}
        </Alert>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="mx-auto max-w-7xl px-6 py-6 pb-24">
      <Link
        to="/"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        返回热点中心
      </Link>

      <Header event={data} />

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          <AnalysisSection event={data} />
          <ArticlesSection event={data} isEditor={isEditor} />
        </div>

        <aside className="space-y-4">
          <RadarCard event={data} />
          {trend && trend.points.length > 0 && <TrendCard points={trend.points} />}
          {data.tags.length > 0 && (
            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold">标签</h2>
              <div className="flex flex-wrap gap-1.5">
                {data.tags.map((t) => (
                  <Link
                    key={t.id}
                    to={`/?tagIds=${t.id}&scope=ALL`}
                    className="rounded-full bg-muted px-2.5 py-0.5 text-xs hover:bg-primary/10 hover:text-primary"
                  >
                    {t.displayName}
                  </Link>
                ))}
              </div>
            </Card>
          )}
          {related && related.length > 0 && (
            <Card className="p-4">
              <h2 className="mb-3 text-sm font-semibold">相关事件</h2>
              <ul className="space-y-3">
                {related.map((r) => (
                  <li key={r.id}>
                    <Link
                      to={`/events/${r.id}`}
                      className="line-clamp-2 text-sm hover:text-primary"
                    >
                      {r.title}
                    </Link>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      推荐 {r.recommendIndex.toFixed(1)}
                      {r.similarity !== null && ` · 相似 ${(r.similarity * 100).toFixed(0)}%`}
                    </p>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </aside>
      </div>

      {isEditor && <EditorBar event={data} />}
    </div>
  )
}

// ------------------------------------------------------------------ 分区组件

function Header({ event }: { event: EventDetail }) {
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {event.isPinned && (
          <Badge variant="warning" className="gap-1">
            <Pin className="h-3 w-3" aria-hidden />
            置顶
          </Badge>
        )}
        {event.isHidden && <Badge variant="danger">已隐藏</Badge>}
        {event.categories.map((c) => (
          <Badge key={c}>{c}</Badge>
        ))}
        <Badge variant="outline">{REGION_LABEL[event.region] ?? event.region}</Badge>
        {event.isManuallyEdited && <Badge variant="outline">已人工校对</Badge>}
      </div>

      <h1 className="text-2xl font-bold leading-tight">{event.title}</h1>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
        <span className="flex items-center gap-1">
          <Flame className="h-4 w-4 text-orange-500" aria-hidden />
          热度 {event.heatScore.toFixed(1)}
        </span>
        <span>推荐指数 {event.recommendIndex.toFixed(1)}</span>
        <span>
          {event.sourceCount} 个来源 · {event.articleCount} 篇文章
        </span>
        <span>
          首次出现 {format(new Date(event.firstSeenAt), 'yyyy-MM-dd HH:mm')}
        </span>
        <span>
          最后更新{' '}
          {formatDistanceToNow(new Date(event.lastSeenAt), { addSuffix: true, locale: zhCN })}
        </span>
      </div>
    </div>
  )
}

function AnalysisSection({ event }: { event: EventDetail }) {
  const a = event.analysis

  if (!a) {
    return (
      <Card className="flex flex-col items-center gap-3 py-14 text-center">
        {event.status === 'AI_FAILED' ? (
          <>
            <XCircle className="h-8 w-8 text-muted-foreground/40" aria-hidden />
            <p className="text-muted-foreground">AI 分析失败，可在后台重跑分析任务</p>
          </>
        ) : (
          <>
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground/40" aria-hidden />
            <p className="text-muted-foreground">AI 正在分析中，稍后自动刷新…</p>
          </>
        )}
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <blockquote className="rounded-lg border-l-4 border-primary bg-primary/5 p-4 text-base font-medium">
        {a.summaryOneLine}
      </blockquote>

      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold text-muted-foreground">完整总结</h2>
        <p className="whitespace-pre-wrap leading-relaxed">{a.summary}</p>
      </Card>

      {a.keyPoints.length > 0 && (
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">核心观点</h2>
          <ol className="space-y-2">
            {a.keyPoints.map((p, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {i + 1}
                </span>
                <span className="leading-relaxed">{p}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {a.innovations.length > 0 && (
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">创新点</h2>
          <ul className="space-y-2">
            {a.innovations.map((p, i) => (
              <li key={i} className="flex gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-500" aria-hidden />
                <span className="leading-relaxed">{p}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {a.audience.length > 0 && (
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">适合人群</h2>
          <div className="flex flex-wrap gap-1.5">
            {a.audience.map((x) => (
              <Badge key={x} variant="outline">
                {x}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <WorthCard
          title="值得写公众号吗"
          yes={a.worthArticle}
          why={a.worthArticleWhy}
        />
        <WorthCard title="值得深入研究吗" yes={a.worthResearch} why={a.worthResearchWhy} />
      </div>

      <p className="text-xs text-muted-foreground">
        由 {a.modelAlias} · prompt v{a.promptVersion} 于{' '}
        {format(new Date(a.analyzedAt), 'yyyy-MM-dd HH:mm')} 产出
      </p>
    </div>
  )
}

function WorthCard({ title, yes, why }: { title: string; yes: boolean; why: string | null }) {
  return (
    <Card className="p-5">
      <div className="mb-2 flex items-center gap-2">
        {yes ? (
          <CheckCircle2 className="h-5 w-5 text-green-500" aria-hidden />
        ) : (
          <XCircle className="h-5 w-5 text-muted-foreground" aria-hidden />
        )}
        <h3 className="font-semibold">{title}</h3>
      </div>
      <p className="text-sm text-muted-foreground">{why || (yes ? '值得' : '暂不推荐')}</p>
    </Card>
  )
}

function ArticlesSection({ event, isEditor }: { event: EventDetail; isEditor: boolean }) {
  return (
    <Card className="p-5">
      <h2 className="mb-4 text-sm font-semibold text-muted-foreground">
        来源文章（{event.articles.length}）
      </h2>
      <ul className="divide-y divide-border">
        {event.articles.map((a) => (
          <li key={a.id} className="py-3 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-center gap-1.5">
              {a.isPrimary && <Badge variant="success">主</Badge>}
              {a.source && <Badge variant="outline">{a.source.name}</Badge>}
              {isEditor && a.matchLevel && (
                <Badge variant="outline">
                  {MATCH_LEVEL_LABEL[a.matchLevel] ?? a.matchLevel}
                  {a.similarity !== null && ` ${a.similarity.toFixed(3)}`}
                </Badge>
              )}
            </div>
            <a
              href={a.url}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-1 flex items-start gap-1.5 font-medium hover:text-primary"
            >
              {a.title}
              <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0" aria-hidden />
            </a>
            <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
              {a.author && <span>{a.author}</span>}
              <span>{format(new Date(a.publishedAt), 'yyyy-MM-dd HH:mm')}</span>
              {Object.entries(a.metrics).map(([k, v]) => (
                <span key={k}>
                  {k} {v}
                </span>
              ))}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function RadarCard({ event }: { event: EventDetail }) {
  const option = {
    tooltip: {},
    radar: {
      indicator: [
        { name: '热度', max: 100 },
        { name: '价值', max: 100 },
        { name: '原创', max: 100 },
        { name: '趋势', max: 100 },
        { name: '推荐', max: 100 },
      ],
      radius: '65%',
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: [
              event.heatScore,
              event.valueScore ?? 0,
              event.originalityScore ?? 0,
              event.trendScore ?? 0,
              event.recommendIndex,
            ],
            name: '评分',
            areaStyle: { opacity: 0.25 },
          },
        ],
      },
    ],
  }
  return (
    <Card className="p-4">
      <h2 className="mb-1 text-sm font-semibold">评分雷达</h2>
      <ReactECharts option={option} style={{ height: 240 }} notMerge lazyUpdate />
    </Card>
  )
}

function TrendCard({ points }: { points: Array<{ date: string; heatScore: number; sourceCount: number }> }) {
  const option = {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 32, top: 24, bottom: 28 },
    xAxis: { type: 'category', data: points.map((p) => p.date.slice(5)) },
    yAxis: [
      { type: 'value', name: '热度' },
      { type: 'value', name: '来源', minInterval: 1 },
    ],
    series: [
      {
        name: '热度',
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.15 },
        data: points.map((p) => p.heatScore),
      },
      {
        name: '来源数',
        type: 'line',
        yAxisIndex: 1,
        data: points.map((p) => p.sourceCount),
      },
    ],
  }
  return (
    <Card className="p-4">
      <h2 className="mb-1 text-sm font-semibold">7 日热度曲线</h2>
      <ReactECharts option={option} style={{ height: 200 }} notMerge lazyUpdate />
    </Card>
  )
}

function EditorBar({ event }: { event: EventDetail }) {
  const update = useUpdateEvent(event.id)
  const unlock = useUnlockField(event.id)

  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-6 py-3">
        <span className="text-sm font-medium text-muted-foreground">运营模式</span>

        <label className="flex items-center gap-2 text-sm">
          <Pin className="h-4 w-4" aria-hidden />
          置顶
          <Switch
            checked={event.isPinned}
            disabled={update.isPending}
            onCheckedChange={(v) =>
              update.mutate(
                { isPinned: v, ...(v ? { isHidden: false } : {}) },
                { onSuccess: () => toast.success(v ? '已置顶' : '已取消置顶') },
              )
            }
            aria-label="置顶"
          />
        </label>

        <label className="flex items-center gap-2 text-sm">
          {event.isHidden ? (
            <EyeOff className="h-4 w-4" aria-hidden />
          ) : (
            <Eye className="h-4 w-4" aria-hidden />
          )}
          隐藏
          <Switch
            checked={event.isHidden}
            disabled={update.isPending}
            onCheckedChange={(v) =>
              update.mutate(
                { isHidden: v, ...(v ? { isPinned: false } : {}) },
                { onSuccess: () => toast.success(v ? '已隐藏' : '已取消隐藏') },
              )
            }
            aria-label="隐藏"
          />
        </label>

        {event.manualLockedFields.length > 0 && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Lock className="h-4 w-4" aria-hidden />
            已锁定：
            {event.manualLockedFields.map((f) => (
              <Button
                key={f}
                variant="outline"
                size="sm"
                loading={unlock.isPending}
                onClick={() =>
                  unlock.mutate(f, { onSuccess: () => toast.success(`已解除 ${f} 的锁定`) })
                }
              >
                {f} ✕
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div className="mx-auto max-w-7xl animate-pulse px-6 py-6">
      <div className="h-4 w-24 rounded bg-muted" />
      <div className="mt-4 h-8 w-3/4 rounded bg-muted" />
      <div className="mt-3 h-4 w-1/2 rounded bg-muted" />
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <div className="h-20 rounded-lg bg-muted" />
          <div className="h-40 rounded-lg bg-muted" />
          <div className="h-52 rounded-lg bg-muted" />
        </div>
        <div className="space-y-4">
          <div className="h-64 rounded-lg bg-muted" />
          <div className="h-48 rounded-lg bg-muted" />
        </div>
      </div>
    </div>
  )
}
