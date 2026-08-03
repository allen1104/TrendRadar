import { useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  REPORT_TYPE_NAMES,
  type ExportFormat,
  type ReportItemWithEvent,
} from '../api/reports'
import {
  downloadReportExport,
  useReportDetail,
} from '../hooks/useReport'

const EXPORT_FORMATS: { value: ExportFormat; label: string }[] = [
  { value: 'MARKDOWN', label: 'Markdown' },
  { value: 'HTML', label: 'HTML' },
  { value: 'PDF', label: 'PDF' },
  { value: 'WECHAT_HTML', label: '微信 HTML' },
]

function renderMarkdown(md: string): string {
  // 极简渲染：行级处理
  const lines = md.split('\n')
  const out: string[] = []
  for (const raw of lines) {
    const line = raw
    if (line.startsWith('### ')) out.push(`<h3>${line.slice(4)}</h3>`)
    else if (line.startsWith('## ')) out.push(`<h2>${line.slice(3)}</h2>`)
    else if (line.startsWith('# ')) out.push(`<h1>${line.slice(2)}</h1>`)
    else if (line.startsWith('> ')) out.push(`<blockquote>${line.slice(2)}</blockquote>`)
    else if (line === '---') out.push('<hr />')
    else if (line.trim() === '') out.push('')
    else out.push(`<p>${line}</p>`)
  }
  return out.join('\n')
}

function ReportItemRow({ it }: { it: ReportItemWithEvent }) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        it.isTop ? 'border-orange-300 bg-orange-50' : 'border-gray-200 bg-white'
      }`}
    >
      <div className="mb-2 flex items-center gap-2 text-xs">
        <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-700">
          {it.section}
        </span>
        {it.isTop && (
          <span className="rounded bg-orange-500 px-2 py-0.5 text-white">
            🔥 头条
          </span>
        )}
      </div>
      <h4 className="mb-2 text-base font-semibold text-gray-900">
        {it.headline}
      </h4>
      <p className="text-sm text-gray-700">{it.brief}</p>
      {it.comment && (
        <div className="mt-2 rounded bg-yellow-50 px-3 py-2 text-xs text-yellow-800">
          💬 {it.comment}
        </div>
      )}
      {it.event && (
        <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
          <span>推荐 {it.event.recommendIndex.toFixed(1)}</span>
          <span>·</span>
          <span>{it.event.sourceCount} 来源</span>
          {it.event.primaryArticleUrl && (
            <>
              <span>·</span>
              <a
                href={it.event.primaryArticleUrl}
                target="_blank"
                rel="noreferrer"
                className="text-blue-500 hover:underline"
              >
                原文 →
              </a>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export function ReportReaderPage() {
  const { id } = useParams<{ id: string }>()
  const reportId = Number(id ?? 0)
  const { data: report, isLoading } = useReportDetail(reportId)
  const [exporting, setExporting] = useState<ExportFormat | null>(null)

  async function handleExport(format: ExportFormat) {
    setExporting(format)
    try {
      await downloadReportExport(reportId, format)
    } finally {
      setExporting(null)
    }
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="h-12 w-2/3 animate-pulse rounded bg-gray-100" />
        <div className="mt-4 h-4 w-1/3 animate-pulse rounded bg-gray-100" />
        <div className="mt-8 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded bg-gray-100"
            />
          ))}
        </div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16 text-center text-gray-500">
        日报不存在
      </div>
    )
  }

  const contentToShow = report.contentEdited || report.contentMd || ''

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 border-b border-gray-200 pb-6">
        <div className="mb-2 flex items-center gap-2 text-xs">
          <span className="rounded bg-blue-100 px-2 py-0.5 text-blue-700">
            {REPORT_TYPE_NAMES[report.reportType]}
          </span>
          <span className="text-gray-500">{report.reportDate}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">{report.itemCount} 条</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">{report.viewCount} 阅读</span>
        </div>
        <h1 className="text-3xl font-bold text-gray-900">{report.title}</h1>
        {report.intro && (
          <blockquote className="mt-4 border-l-4 border-blue-400 bg-blue-50 px-4 py-2 text-sm text-gray-700">
            {report.intro}
          </blockquote>
        )}
        {/* 导出 */}
        <div className="mt-4 flex gap-2">
          {EXPORT_FORMATS.map((f) => (
            <button
              key={f.value}
              onClick={() => handleExport(f.value)}
              disabled={exporting !== null}
              className="rounded border border-gray-300 px-3 py-1 text-xs hover:bg-gray-50 disabled:opacity-50"
            >
              {exporting === f.value ? '导出中…' : `导出 ${f.label}`}
            </button>
          ))}
        </div>
      </div>

      {/* Sections（按板块分组） */}
      {report.sections.length === 0 ? (
        <div
          className="prose prose-sm max-w-none"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(contentToShow) }}
        />
      ) : (
        <div className="space-y-8">
          {report.sections.map((sec) => (
            <section key={sec.name}>
              <h2 className="mb-3 border-l-4 border-blue-500 pl-3 text-xl font-bold text-gray-900">
                {sec.name}
              </h2>
              <div className="space-y-3">
                {sec.items.map((it) => (
                  <ReportItemRow key={it.id} it={it} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {report.outro && (
        <div className="mt-8 border-t border-gray-200 pt-6 text-center text-sm text-gray-500">
          {report.outro}
        </div>
      )}
    </div>
  )
}