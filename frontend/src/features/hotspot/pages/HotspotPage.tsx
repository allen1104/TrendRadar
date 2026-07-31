import { ChevronLeft, ChevronRight, RotateCcw, Search, SlidersHorizontal, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { hasRole, type Role } from '@/features/auth/types'
import type { CategoryFilter, Scope } from '@/features/hotspot/api/hotspot'
import { EventCard } from '@/features/hotspot/components/EventCard'
import { EventListSkeleton } from '@/features/hotspot/components/EventCardSkeleton'
import { useEventList, useTags } from '@/features/hotspot/hooks/useHotspot'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'

const SCOPES: Array<{ value: Scope; label: string }> = [
  { value: 'TODAY', label: '今日' },
  { value: 'WEEK', label: '本周' },
  { value: 'MONTH', label: '本月' },
  { value: 'ALL', label: '全部' },
]

const CATEGORIES: Array<{ value: CategoryFilter; label: string }> = [
  { value: 'ALL', label: '全部' },
  { value: 'GLOBAL', label: '全球' },
  { value: 'CN', label: '国内' },
  { value: 'AI', label: 'AI' },
  { value: 'GITHUB', label: 'GitHub' },
  { value: 'PAPER', label: '论文' },
  { value: 'AGENT', label: 'Agent' },
]

const SORTS = [
  { value: '-recommendIndex', label: '推荐指数' },
  { value: '-heatScore', label: '热度' },
  { value: '-lastSeenAt', label: '最新' },
  { value: '-sourceCount', label: '来源数' },
]

const PAGE_SIZE = 20

export function HotspotPage() {
  const [params, setParams] = useSearchParams()
  const user = useAuthStore((s) => s.user)
  const role: Role = user?.role ?? 'GUEST'
  const isEditor = hasRole(role, 'EDITOR')

  // ---------------------------------------------- URL ↔ 状态
  const scope = (params.get('scope') as Scope) || 'TODAY'
  const category = (params.get('category') as CategoryFilter) || 'ALL'
  const sort = params.get('sort') || '-recommendIndex'
  const keyword = params.get('keyword') || ''
  const minRecommend = params.get('minRecommend')
  const tagIds = params.getAll('tagIds').map(Number).filter(Boolean)
  const includeHidden = params.get('includeHidden') === 'true'
  const page = Number(params.get('page') || 1)

  const [showFilters, setShowFilters] = useState(false)
  const [keywordDraft, setKeywordDraft] = useState(keyword)

  useEffect(() => setKeywordDraft(keyword), [keyword])

  // 搜索框 300ms debounce
  useEffect(() => {
    if (keywordDraft === keyword) return
    const t = setTimeout(() => {
      if (keywordDraft && keywordDraft.trim().length < 2) return
      patch({ keyword: keywordDraft.trim() || null, page: null })
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keywordDraft])

  function patch(next: Record<string, string | number | null>) {
    const sp = new URLSearchParams(params)
    for (const [k, v] of Object.entries(next)) {
      if (v === null || v === '') sp.delete(k)
      else sp.set(k, String(v))
    }
    setParams(sp, { replace: false })
  }

  function toggleTag(id: number) {
    const sp = new URLSearchParams(params)
    const current = sp.getAll('tagIds')
    sp.delete('tagIds')
    const next = current.includes(String(id))
      ? current.filter((x) => x !== String(id))
      : [...current, String(id)]
    next.forEach((x) => sp.append('tagIds', x))
    sp.delete('page')
    setParams(sp)
  }

  function resetFilters() {
    setParams(new URLSearchParams({ scope, category }))
  }

  const query = useMemo(
    () => ({
      scope,
      category,
      sort,
      keyword: keyword || undefined,
      tagIds: tagIds.length ? tagIds : undefined,
      minRecommend: minRecommend ? Number(minRecommend) : undefined,
      includeHidden: includeHidden || undefined,
      page,
      size: PAGE_SIZE,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scope, category, sort, keyword, params.toString(), page],
  )

  const { data, isPending, isError, error, isFetching } = useEventList(query)
  const { data: hotTags } = useTags({ limit: 20 })

  const hasCustomFilter =
    Boolean(keyword) || tagIds.length > 0 || Boolean(minRecommend) || includeHidden

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-6 py-6 xl:grid-cols-[1fr_280px]">
      <div className="min-w-0">
        {/* ---------------------------------------- 维度 Tab */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1 rounded-lg bg-muted p-1">
            {SCOPES.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => patch({ scope: s.value, page: null })}
                className={cn(
                  'rounded-md px-4 py-1.5 text-sm transition-colors',
                  scope === s.value
                    ? 'bg-background font-medium shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {s.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {CATEGORIES.map((c) => (
              <button
                key={c.value}
                type="button"
                onClick={() => patch({ category: c.value, page: null })}
                className={cn(
                  'rounded-full border px-3 py-1 text-sm transition-colors',
                  category === c.value
                    ? 'border-primary bg-primary/10 font-medium text-primary'
                    : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {/* ---------------------------------------- 搜索 + 筛选 */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              value={keywordDraft}
              onChange={(e) => setKeywordDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') patch({ keyword: keywordDraft.trim() || null, page: null })
              }}
              placeholder="搜索热点标题或摘要（≥2 字符）"
              className="pl-9 pr-9"
              aria-label="搜索热点"
            />
            {keywordDraft && (
              <button
                type="button"
                aria-label="清除搜索"
                onClick={() => {
                  setKeywordDraft('')
                  patch({ keyword: null, page: null })
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          <select
            value={sort}
            onChange={(e) => patch({ sort: e.target.value, page: null })}
            aria-label="排序方式"
            className="h-9 rounded-md border border-border bg-background px-3 text-sm"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>

          <Button
            variant={showFilters ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowFilters((v) => !v)}
          >
            <SlidersHorizontal className="mr-1.5 h-4 w-4" />
            筛选
            {hasCustomFilter && <span className="ml-1.5 h-1.5 w-1.5 rounded-full bg-primary" />}
          </Button>

          {hasCustomFilter && (
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              <RotateCcw className="mr-1.5 h-4 w-4" />
              重置
            </Button>
          )}
        </div>

        {showFilters && (
          <Card className="mt-3 space-y-4 p-4">
            <div>
              <label
                htmlFor="minRecommend"
                className="mb-1.5 block text-sm font-medium text-muted-foreground"
              >
                推荐指数下限：{minRecommend || 0}
              </label>
              <input
                id="minRecommend"
                type="range"
                min={0}
                max={100}
                step={5}
                value={Number(minRecommend || 0)}
                onChange={(e) =>
                  patch({ minRecommend: Number(e.target.value) || null, page: null })
                }
                className="w-full accent-primary"
              />
            </div>

            {hotTags && hotTags.length > 0 && (
              <div>
                <p className="mb-1.5 text-sm font-medium text-muted-foreground">标签</p>
                <div className="flex flex-wrap gap-1.5">
                  {hotTags.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => toggleTag(t.id)}
                      className={cn(
                        'rounded-full border px-2.5 py-0.5 text-xs',
                        tagIds.includes(t.id)
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-border text-muted-foreground hover:text-foreground',
                      )}
                    >
                      {t.displayName}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {isEditor && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">显示已隐藏事件</span>
                <Switch
                  checked={includeHidden}
                  onCheckedChange={(v) =>
                    patch({ includeHidden: v ? 'true' : null, page: null })
                  }
                  aria-label="显示已隐藏事件"
                />
              </div>
            )}
          </Card>
        )}

        {/* ---------------------------------------- 列表 */}
        <div className="mt-4">
          {isPending ? (
            <EventListSkeleton />
          ) : isError ? (
            <Alert variant="error">
              加载失败：{error instanceof Error ? error.message : '未知错误'}
            </Alert>
          ) : data && data.items.length === 0 ? (
            <Card className="flex flex-col items-center gap-3 py-16 text-center">
              <Search className="h-10 w-10 text-muted-foreground/40" aria-hidden />
              <p className="text-muted-foreground">当前筛选条件下暂无热点</p>
              <Button variant="outline" size="sm" onClick={resetFilters}>
                重置筛选
              </Button>
            </Card>
          ) : (
            <div className={cn('space-y-3', isFetching && 'opacity-60 transition-opacity')}>
              {data?.items.map((e) => (
                <EventCard key={e.id} event={e} isEditor={isEditor} />
              ))}
            </div>
          )}
        </div>

        {/* ---------------------------------------- 分页 */}
        {data && data.pages > 1 && (
          <div className="mt-6 flex items-center justify-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => patch({ page: page - 1 })}
            >
              <ChevronLeft className="h-4 w-4" />
              上一页
            </Button>
            <span className="text-sm text-muted-foreground tabular-nums">
              {data.page} / {data.pages} 页 · 共 {data.total} 条
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= data.pages}
              onClick={() => patch({ page: page + 1 })}
            >
              下一页
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>

      {/* ---------------------------------------- 右侧栏 */}
      <aside className="hidden space-y-4 xl:block">
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">热门标签</h2>
          {hotTags && hotTags.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {hotTags.slice(0, 15).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => toggleTag(t.id)}
                  className="rounded-full bg-muted px-2.5 py-0.5 text-xs hover:bg-primary/10 hover:text-primary"
                >
                  {t.displayName}
                  {t.eventCount ? (
                    <span className="ml-1 text-muted-foreground">{t.eventCount}</span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">暂无标签（AI 分析产出后出现）</p>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold">当前榜单</h2>
          <dl className="space-y-1.5 text-xs text-muted-foreground">
            <div className="flex justify-between">
              <dt>时间维度</dt>
              <dd>
                <Badge variant="outline">
                  {SCOPES.find((s) => s.value === scope)?.label ?? scope}
                </Badge>
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>分类</dt>
              <dd>
                <Badge variant="outline">
                  {CATEGORIES.find((c) => c.value === category)?.label ?? category}
                </Badge>
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>命中事件</dt>
              <dd className="tabular-nums">{data?.total ?? '—'}</dd>
            </div>
          </dl>
        </Card>
      </aside>
    </div>
  )
}
