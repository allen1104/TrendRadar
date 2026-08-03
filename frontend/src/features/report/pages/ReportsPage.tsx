import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  REPORT_TYPE_NAMES,
  type ReportType,
} from '../api/reports'
import { useReportsList } from '../hooks/useReport'

const TYPES: (ReportType | 'ALL')[] = ['ALL', 'AI', 'TECH', 'GITHUB', 'AGENT']

export function ReportsPage() {
  const [tab, setTab] = useState<ReportType | 'ALL'>('ALL')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useReportsList({
    reportType: tab === 'ALL' ? undefined : tab,
    page,
    size: 20,
  })

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold">日报中心</h1>
        <a
          href="/api/v1/reports/rss"
          target="_blank"
          rel="noreferrer"
          className="text-sm text-blue-500 hover:underline"
        >
          📡 RSS 公开源
        </a>
      </div>

      {/* 类型 Tab */}
      <div className="mb-6 flex gap-2 border-b border-gray-200 pb-2">
        {TYPES.map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t)
              setPage(1)
            }}
            className={`rounded-t px-4 py-2 text-sm font-medium transition ${
              tab === t
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {t === 'ALL' ? '全部' : REPORT_TYPE_NAMES[t]}
          </button>
        ))}
      </div>

      {/* 列表 */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-24 animate-pulse rounded-lg bg-gray-100"
            />
          ))}
        </div>
      ) : !data?.items.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-16 text-center text-gray-500">
          暂无日报
        </div>
      ) : (
        <div className="space-y-4">
          {data.items.map((r) => (
            <Link
              key={r.id}
              to={`/reports/${r.id}`}
              className="block rounded-lg border border-gray-200 bg-white p-5 transition hover:border-blue-300 hover:shadow-sm"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="mb-2 flex items-center gap-2 text-xs">
                    <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-600">
                      {REPORT_TYPE_NAMES[r.reportType]}
                    </span>
                    <span className="text-gray-500">{r.reportDate}</span>
                    <span className="text-gray-400">·</span>
                    <span className="text-gray-500">
                      {r.itemCount} 条
                    </span>
                    <span className="text-gray-400">·</span>
                    <span className="text-gray-500">
                      {r.viewCount} 阅读
                    </span>
                  </div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    {r.title}
                  </h2>
                  {r.intro && (
                    <p className="mt-2 line-clamp-2 text-sm text-gray-600">
                      {r.intro}
                    </p>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* 分页 */}
      {data && data.pages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-2">
          <button
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded border border-gray-300 px-3 py-1 text-sm disabled:opacity-50"
          >
            上一页
          </button>
          <span className="text-sm text-gray-600">
            {page} / {data.pages}
          </span>
          <button
            disabled={page === data.pages}
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            className="rounded border border-gray-300 px-3 py-1 text-sm disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}