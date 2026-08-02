import { Link, useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  useCreationDrafts,
  useCreationOptions,
  useDeleteDraft,
} from '@/features/creation/hooks/useCreation'
import type { Platform, Style } from '@/features/creation/api/creation'

/** 我的草稿列表页。 */
export function CreationDraftsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const page = Number(searchParams.get('page') ?? '1')
  const platform = (searchParams.get('platform') as Platform | null) ?? undefined
  const style = (searchParams.get('style') as Style | null) ?? undefined
  const keyword = searchParams.get('keyword') ?? ''
  const [keywordInput, setKeywordInput] = useStateDebounced(keyword, (v) =>
    setSearchParams((p) => {
      const np = new URLSearchParams(p)
      if (v) np.set('keyword', v)
      else np.delete('keyword')
      np.set('page', '1')
      return np
    }),
  )

  const { data, isLoading } = useCreationDrafts({
    platform,
    style,
    keyword: keyword || undefined,
    page,
    size: 20,
  })

  const { data: options } = useCreationOptions()
  const deleteDraft = useDeleteDraft()

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">✍️ 我的草稿</h1>
        <Link to="/">
          <Button variant="outline">← 返回热点中心</Button>
        </Link>
      </div>

      {/* 顶部筛选 */}
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border bg-muted/20 p-3">
        <Input
          value={keywordInput}
          onChange={(e) => setKeywordInput(e.target.value)}
          placeholder="搜索标题或正文"
          className="max-w-xs"
        />
        {options && (
          <>
            <select
              value={platform ?? ''}
              onChange={(e) =>
                setSearchParams((p) => {
                  const np = new URLSearchParams(p)
                  if (e.target.value) np.set('platform', e.target.value)
                  else np.delete('platform')
                  np.set('page', '1')
                  return np
                })
              }
              className="rounded-md border bg-background px-2 py-1 text-sm"
            >
              <option value="">全部平台</option>
              {options.platforms.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name}
                </option>
              ))}
            </select>
            <select
              value={style ?? ''}
              onChange={(e) =>
                setSearchParams((p) => {
                  const np = new URLSearchParams(p)
                  if (e.target.value) np.set('style', e.target.value)
                  else np.delete('style')
                  np.set('page', '1')
                  return np
                })
              }
              className="rounded-md border bg-background px-2 py-1 text-sm"
            >
              <option value="">全部风格</option>
              {options.styles.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </select>
          </>
        )}
        {(platform || style || keyword) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSearchParams(new URLSearchParams())}
          >
            重置
          </Button>
        )}
      </div>

      {/* 卡片网格 */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-40 animate-pulse rounded-lg border bg-muted/30"
            />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-lg border bg-muted/10 py-16 text-center">
          <p className="text-4xl">📝</p>
          <p className="text-muted-foreground">还没有草稿，去热点中心找选题吧</p>
          <Link to="/">
            <Button>热点中心</Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {data.items.map((d) => (
            <div
              key={d.id}
              className="group relative flex flex-col rounded-lg border bg-card p-4 transition hover:border-primary/50 hover:shadow"
            >
              <div className="mb-2 flex items-center gap-2 text-xs">
                <span className="rounded bg-primary/10 px-2 py-0.5 text-primary">
                  {d.platform}
                </span>
                <span className="rounded bg-muted px-2 py-0.5">{d.style}</span>
                {d.isEdited && (
                  <span className="rounded bg-yellow-100 px-2 py-0.5 text-yellow-700">
                    ✏️
                  </span>
                )}
                <span
                  className={
                    'ml-auto rounded px-2 py-0.5 ' +
                    (d.status === 'DONE'
                      ? 'bg-green-100 text-green-700'
                      : d.status === 'FAILED'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-blue-100 text-blue-700')
                  }
                >
                  {d.status}
                </span>
              </div>
              <h3 className="line-clamp-2 text-sm font-medium leading-snug">
                {d.title || '（无标题）'}
              </h3>
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {d.eventTitle ?? `事件 #${d.eventId}`}
              </p>
              <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                <span>{d.wordCount} 字</span>
                <span>{new Date(d.createdAt).toLocaleString('zh-CN')}</span>
              </div>
              <div className="absolute right-2 top-2 hidden gap-1 group-hover:flex">
                <Link to={`/creation/drafts/${d.id}`}>
                  <Button variant="outline" size="sm">
                    打开
                  </Button>
                </Link>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (window.confirm('确认删除该草稿？')) deleteDraft.mutate(d.id)
                  }}
                >
                  删除
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 分页 */}
      {data && data.pages > 1 && (
        <div className="mt-6 flex justify-center gap-2">
          <Button
            variant="outline"
            disabled={page <= 1}
            onClick={() =>
              setSearchParams((p) => {
                const np = new URLSearchParams(p)
                np.set('page', String(page - 1))
                return np
              })
            }
          >
            上一页
          </Button>
          <span className="flex items-center text-sm text-muted-foreground">
            第 {page} / {data.pages} 页
          </span>
          <Button
            variant="outline"
            disabled={page >= data.pages}
            onClick={() =>
              setSearchParams((p) => {
                const np = new URLSearchParams(p)
                np.set('page', String(page + 1))
                return np
              })
            }
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}

// ----- 内联 hook：搜索 debounce（300ms） -----

import { useEffect, useState as useReactState } from 'react'

function useStateDebounced<T>(initial: T, onCommit: (v: T) => void) {
  const [value, setValue] = useReactState(initial)
  useEffect(() => {
    const t = window.setTimeout(() => onCommit(value), 300)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])
  return [value, setValue] as const
}