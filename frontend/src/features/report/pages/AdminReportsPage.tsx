import { useState } from 'react'

import {
  REPORT_TYPE_NAMES,
  type ReportType,
} from '../api/reports'
import {
  useAdminGenerate,
  useReportsList,
} from '../hooks/useReport'

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

const TYPES: ReportType[] = ['AI', 'TECH', 'GITHUB', 'AGENT']

export function AdminReportsPage() {
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState<ReportType | 'ALL'>('ALL')
  const [genType, setGenType] = useState<ReportType>('AI')
  const [genDate, setGenDate] = useState<string>(todayISO())
  const [force, setForce] = useState(false)
  const [genResult, setGenResult] = useState<string | null>(null)

  const { data, isLoading } = useReportsList({
    reportType: filter === 'ALL' ? undefined : filter,
    page,
    size: 20,
  })
  const generate = useAdminGenerate()

  async function handleGenerate() {
    setGenResult(null)
    try {
      const r = await generate.mutateAsync({
        reportType: genType,
        reportDate: genDate,
        force,
      })
      if (r.skipped) {
        setGenResult(`已跳过：${r.detail ?? '候选池不足'}`)
      } else {
        setGenResult(`生成成功：report #${r.reportId} (${r.status})`)
      }
    } catch (e: unknown) {
      setGenResult(`失败：${(e as Error).message}`)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-6 text-3xl font-bold">日报审核</h1>

      {/* 手动生成 */}
      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="mb-4 text-lg font-semibold">手动生成</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <select
            value={genType}
            onChange={(e) => setGenType(e.target.value as ReportType)}
            className="rounded border border-gray-300 px-3 py-2 text-sm"
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {REPORT_TYPE_NAMES[t]}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={genDate}
            onChange={(e) => setGenDate(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2 text-sm"
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
            />
            覆盖已存在
          </label>
          <button
            onClick={handleGenerate}
            disabled={generate.isPending}
            className="rounded bg-blue-500 px-4 py-2 text-sm text-white hover:bg-blue-600 disabled:opacity-50"
          >
            {generate.isPending ? '生成中…' : '生成'}
          </button>
        </div>
        {genResult && (
          <p className="mt-3 text-sm text-gray-700">{genResult}</p>
        )}
      </div>

      {/* 列表 */}
      <div className="mb-4 flex gap-2">
        <button
          onClick={() => {
            setFilter('ALL')
            setPage(1)
          }}
          className={`rounded px-3 py-1 text-sm ${
            filter === 'ALL' ? 'bg-blue-500 text-white' : 'bg-gray-100'
          }`}
        >
          全部
        </button>
        {TYPES.map((t) => (
          <button
            key={t}
            onClick={() => {
              setFilter(t)
              setPage(1)
            }}
            className={`rounded px-3 py-1 text-sm ${
              filter === t ? 'bg-blue-500 text-white' : 'bg-gray-100'
            }`}
          >
            {REPORT_TYPE_NAMES[t]}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded bg-gray-100"
            />
          ))}
        </div>
      ) : !data?.items.length ? (
        <div className="rounded border border-dashed border-gray-300 py-12 text-center text-gray-500">
          暂无日报
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left">类型</th>
                <th className="px-3 py-2 text-left">日期</th>
                <th className="px-3 py-2 text-left">标题</th>
                <th className="px-3 py-2 text-left">状态</th>
                <th className="px-3 py-2 text-left">条目</th>
                <th className="px-3 py-2 text-left">费用</th>
                <th className="px-3 py-2 text-left">操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id} className="border-t border-gray-100">
                  <td className="px-3 py-2 text-xs">
                    {REPORT_TYPE_NAMES[r.reportType]}
                  </td>
                  <td className="px-3 py-2 text-xs">{r.reportDate}</td>
                  <td className="px-3 py-2">{r.title}</td>
                  <td className="px-3 py-2 text-xs">
                    <span
                      className={`rounded px-2 py-0.5 ${
                        r.status === 'PUBLISHED'
                          ? 'bg-green-100 text-green-700'
                          : r.status === 'DRAFT'
                          ? 'bg-yellow-100 text-yellow-700'
                          : r.status === 'FAILED'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs">{r.itemCount}</td>
                  <td className="px-3 py-2 text-xs">$0</td>
                  <td className="px-3 py-2 text-xs">
                    <a
                      href={`/reports/${r.id}`}
                      className="text-blue-500 hover:underline"
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 分页 */}
      {data && data.pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
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