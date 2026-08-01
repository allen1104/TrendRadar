import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { ExternalLink, Flame, Globe, MapPin, PenLine, Pin } from 'lucide-react'
import { memo } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { CollectionStarButton } from '@/features/collection/components/CollectionStarButton'
import type { EventListItem } from '@/features/hotspot/api/hotspot'
import { cn } from '@/lib/utils'

const REGION_LABEL: Record<string, string> = {
  GLOBAL: '全球',
  CN: '国内',
  MIXED: '全球+国内',
}

/** 推荐指数环形进度 */
function RecommendRing({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value))
  const r = 18
  const c = 2 * Math.PI * r
  return (
    <div className="relative h-12 w-12 shrink-0" title={`推荐指数 ${pct.toFixed(1)}`}>
      <svg className="h-12 w-12 -rotate-90" viewBox="0 0 44 44" aria-hidden>
        <circle cx="22" cy="22" r={r} fill="none" strokeWidth="4" className="stroke-muted" />
        <circle
          cx="22"
          cy="22"
          r={r}
          fill="none"
          strokeWidth="4"
          strokeLinecap="round"
          className={cn(
            pct >= 80 ? 'stroke-red-500' : pct >= 50 ? 'stroke-amber-500' : 'stroke-primary',
          )}
          strokeDasharray={c}
          strokeDashoffset={c - (c * pct) / 100}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold tabular-nums">
        {pct.toFixed(0)}
      </span>
    </div>
  )
}

interface Props {
  event: EventListItem
  isEditor?: boolean
}

function EventCardInner({ event, isEditor = false }: Props) {
  const sources = event.sources.slice(0, 3)
  const restCount = event.sources.length - sources.length

  return (
    <Card
      className={cn(
        'group relative p-5 transition-colors hover:border-primary/40',
        event.isHidden && 'opacity-55',
      )}
    >
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          {/* 顶部标记行 */}
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            {event.isPinned && (
              <Badge variant="warning" className="gap-1">
                <Pin className="h-3 w-3" aria-hidden />
                置顶
              </Badge>
            )}
            {event.isHidden && isEditor && <Badge variant="danger">已隐藏</Badge>}
            {event.categories.slice(0, 3).map((c) => (
              <Badge key={c}>{c}</Badge>
            ))}
            <Badge variant="outline" className="gap-1">
              {event.region === 'CN' ? (
                <MapPin className="h-3 w-3" aria-hidden />
              ) : (
                <Globe className="h-3 w-3" aria-hidden />
              )}
              {REGION_LABEL[event.region] ?? event.region}
            </Badge>
            {event.isManuallyEdited && <Badge variant="outline">已校对</Badge>}
            {event.worthArticle && (
              <Badge variant="success" className="gap-1">
                <PenLine className="h-3 w-3" aria-hidden />
                值得写
              </Badge>
            )}
          </div>

          <Link
            to={`/events/${event.id}`}
            className="line-clamp-2 text-base font-semibold leading-snug hover:text-primary"
          >
            {event.title}
          </Link>

          {event.summaryOneLine ? (
            <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
              {event.summaryOneLine}
            </p>
          ) : (
            <p className="mt-1.5 text-sm italic text-muted-foreground/70">
              {event.status === 'AI_FAILED' ? 'AI 分析失败，暂无总结' : 'AI 正在分析中…'}
            </p>
          )}
        </div>

        <div className="flex flex-col items-center gap-2">
          <RecommendRing value={event.recommendIndex} />
          <CollectionStarButton eventId={event.id} isCollected={event.isCollected ?? false} />
        </div>
      </div>

      {/* 底部信息条 */}
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <Globe className="h-3.5 w-3.5" aria-hidden />
          {event.sourceCount} 个来源 · {event.articleCount} 篇
        </span>

        <span className="flex items-center gap-1" title="来源">
          {sources.map((s) => (
            <span key={s.id} className="rounded bg-muted px-1.5 py-0.5">
              {s.name}
            </span>
          ))}
          {restCount > 0 && <span className="rounded bg-muted px-1.5 py-0.5">+{restCount}</span>}
        </span>

        <span className="flex items-center gap-1" title="热度分">
          <Flame className="h-3.5 w-3.5 text-orange-500" aria-hidden />
          {event.heatScore.toFixed(1)}
        </span>

        <time dateTime={event.lastSeenAt} className="ml-auto">
          {formatDistanceToNow(new Date(event.lastSeenAt), { addSuffix: true, locale: zhCN })}
        </time>

        {event.primaryArticleUrl && (
          <a
            href={event.primaryArticleUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="flex items-center gap-1 hover:text-foreground"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            原文
          </a>
        )}
      </div>

      {event.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {event.tags.slice(0, 6).map((t) => (
            <span key={t.id} className="text-xs text-muted-foreground">
              #{t.displayName}
            </span>
          ))}
        </div>
      )}
    </Card>
  )
}

export const EventCard = memo(EventCardInner)
