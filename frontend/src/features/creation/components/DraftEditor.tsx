import { memo, useEffect, useRef, useState, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type {
  DraftDetail,
  ExportFormat,
  OutlineItem,
} from '@/features/creation/api/creation'

interface DraftEditorProps {
  draft: DraftDetail
  outline: OutlineItem[]
  streamingContent: string
  isStreaming: boolean
  view: 'edit' | 'preview' | 'wechat'
  onViewChange: (v: 'edit' | 'preview' | 'wechat') => void
  onTitleEdit: (title: string) => void
  onContentEdit: (content: string) => void
  onRegenerate: () => void
  onExport: (fmt: ExportFormat) => void
  onCopy: () => void
  regenerateRemaining: number
  platformSupportsWechat: boolean
}

function DraftEditorRaw({
  draft,
  outline,
  streamingContent,
  isStreaming,
  view,
  onViewChange,
  onTitleEdit,
  onContentEdit,
  onRegenerate,
  onExport,
  onCopy,
  regenerateRemaining,
  platformSupportsWechat,
}: DraftEditorProps) {
  // 优先用流式内容；否则用 AI 原文；最后用用户编辑
  const displayContent =
    isStreaming && streamingContent
      ? streamingContent
      : draft.contentEdited ?? draft.content

  const [editBuffer, setEditBuffer] = useState(draft.contentEdited ?? '')
  const debounceRef = useRef<number | null>(null)
  const [savedAt, setSavedAt] = useState<string | null>(null)

  // 内容变更时启动 debounce 自动保存
  useEffect(() => {
    setEditBuffer(draft.contentEdited ?? draft.content)
  }, [draft.id, draft.contentEdited, draft.content])

  useEffect(() => {
    if (editBuffer === (draft.contentEdited ?? draft.content)) return
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      onContentEdit(editBuffer)
      setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
    }, 3000)
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editBuffer])

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：标题 + 元信息 */}
      <div className="border-b px-6 py-3">
        <Input
          value={draft.title}
          onChange={(e) => onTitleEdit(e.target.value)}
          disabled={isStreaming}
          className="text-lg font-semibold"
          placeholder="（生成中…）"
        />
        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
          <span>{draft.platform}</span>
          <span>·</span>
          <span>{draft.style}</span>
          <span>·</span>
          <span>{displayContent.length} 字</span>
          {draft.modelAlias && (
            <>
              <span>·</span>
              <span>{draft.modelAlias}</span>
            </>
          )}
          {draft.costUsd > 0 && (
            <>
              <span>·</span>
              <span>${draft.costUsd.toFixed(4)}</span>
            </>
          )}
          {savedAt && (
            <>
              <span>·</span>
              <span>已保存 {savedAt}</span>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 左侧：大纲 */}
        <aside className="w-64 overflow-y-auto border-r bg-muted/20 p-4 text-sm">
          <div className="mb-2 font-medium">大纲</div>
          {outline.length === 0 ? (
            <p className="text-xs text-muted-foreground">生成中会出现大纲…</p>
          ) : (
            <ol className="space-y-2">
              {outline.map((o, i) => (
                <li key={i}>
                  <div className="font-medium">{o.heading}</div>
                  {o.points.length > 0 && (
                    <ul className="ml-3 mt-1 space-y-0.5 text-xs text-muted-foreground">
                      {o.points.map((p, j) => (
                        <li key={j}>· {p}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
          )}
          {draft.coverSuggestion && (
            <div className="mt-6">
              <div className="mb-1 font-medium">💡 封面建议</div>
              <p className="text-xs text-muted-foreground">
                {draft.coverSuggestion}
              </p>
            </div>
          )}
          {draft.tagsSuggestion.length > 0 && (
            <div className="mt-4">
              <div className="mb-1 font-medium">🏷 建议标签</div>
              <div className="flex flex-wrap gap-1">
                {draft.tagsSuggestion.map((t) => (
                  <span
                    key={t}
                    className="rounded-md bg-primary/10 px-2 py-0.5 text-xs text-primary"
                  >
                    #{t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </aside>

        {/* 中间：内容区 */}
        <main className="flex-1 overflow-y-auto">
          {/* 视图切换 */}
          <div className="flex items-center justify-between border-b bg-muted/10 px-6 py-2 text-sm">
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => onViewChange('edit')}
                className={cn(
                  'rounded px-3 py-1 transition',
                  view === 'edit' && 'bg-primary text-primary-foreground',
                )}
              >
                编辑
              </button>
              <button
                type="button"
                onClick={() => onViewChange('preview')}
                className={cn(
                  'rounded px-3 py-1 transition',
                  view === 'preview' && 'bg-primary text-primary-foreground',
                )}
              >
                预览
              </button>
              {platformSupportsWechat && (
                <button
                  type="button"
                  onClick={() => onViewChange('wechat')}
                  className={cn(
                    'rounded px-3 py-1 transition',
                    view === 'wechat' && 'bg-primary text-primary-foreground',
                  )}
                >
                  微信预览
                </button>
              )}
            </div>
            {isStreaming && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
                正在生成…
              </span>
            )}
          </div>

          <div className="px-6 py-4">
            {view === 'edit' && (
              <textarea
                value={editBuffer}
                onChange={(e) => setEditBuffer(e.target.value)}
                disabled={isStreaming}
                rows={24}
                className="w-full resize-none border-0 bg-transparent font-mono text-sm leading-relaxed outline-none"
              />
            )}
            {view === 'preview' && (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                {displayContent ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSanitize]}
                    components={markdownComponents}
                  >
                    {displayContent}
                  </ReactMarkdown>
                ) : (
                  <p className="text-muted-foreground italic">
                    {isStreaming ? '生成中…' : '正文为空'}
                  </p>
                )}
              </div>
            )}
            {view === 'wechat' && (
              <div
                className="mx-auto max-w-[375px] rounded-lg bg-white p-4 text-sm leading-relaxed shadow-md"
                style={{ fontFamily: '-apple-system, sans-serif' }}
              >
                <h1 className="mb-3 text-center text-base font-bold">
                  {draft.title}
                </h1>
                <WechatBody content={displayContent} />
              </div>
            )}
          </div>
        </main>
      </div>

      {/* 底部操作条 */}
      <div className="flex items-center justify-between border-t bg-muted/20 px-6 py-2 text-sm">
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onRegenerate}
            disabled={isStreaming || regenerateRemaining <= 0}
          >
            ⟳ 重新生成 ({regenerateRemaining}/5)
          </Button>
          <Button variant="outline" size="sm" onClick={onCopy}>
            📋 复制全文
          </Button>
        </div>
        <div className="flex gap-2">
          <select
            onChange={(e) => {
              if (e.target.value) onExport(e.target.value as ExportFormat)
              e.target.value = ''
            }}
            className="rounded-md border bg-background px-2 py-1 text-sm"
            defaultValue=""
            disabled={isStreaming}
          >
            <option value="" disabled>
              导出 ▾
            </option>
            <option value="MARKDOWN">Markdown</option>
            <option value="HTML">HTML</option>
            <option value="WECHAT_HTML">微信 HTML</option>
            <option value="TXT">纯文本</option>
          </select>
        </div>
      </div>
    </div>
  )
}

const markdownComponents: Components = {}

// 微信公众号样式的简易渲染（与后端 render_wechat_html 类似但简化）
function WechatBody({ content }: { content: string }) {
  if (!content) return <p className="text-gray-400 italic">正文为空</p>
  const lines = content.split('\n')
  const out: ReactNode[] = []
  lines.forEach((line, i) => {
    const s = line.trim()
    if (!s) return
    if (s.startsWith('# '))
      out.push(
        <p key={i} style={{ fontWeight: 'bold', fontSize: '17px', margin: '1em 0 0.5em' }}>
          {s.slice(2)}
        </p>,
      )
    else if (s.startsWith('## '))
      out.push(
        <p key={i} style={{ fontWeight: 'bold', fontSize: '15px', margin: '0.8em 0 0.4em', color: '#333' }}>
          {s.slice(3)}
        </p>,
      )
    else if (s.startsWith('### '))
      out.push(
        <p key={i} style={{ fontWeight: 'bold', fontSize: '14px', margin: '0.6em 0 0.3em', color: '#555' }}>
          {s.slice(4)}
        </p>,
      )
    else if (/^[-*]\s+/.test(s))
      out.push(
        <p key={i} style={{ paddingLeft: '1em', margin: '0.2em 0' }}>
          • {s.replace(/^[-*]\s+/, '')}
        </p>,
      )
    else if (s === '---')
      out.push(<hr key={i} style={{ border: 'none', borderTop: '1px solid #eee', margin: '1em 0' }} />)
    else
      out.push(
        <p key={i} style={{ margin: '0.5em 0', lineHeight: 1.8 }}>
          {inlineMd(s)}
        </p>,
      )
  })
  return <>{out}</>
}

function inlineMd(s: string): ReactNode {
  // 极简：**bold** *em* `code` [text](url)
  const parts: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) parts.push(s.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**'))
      parts.push(<strong key={i++}>{tok.slice(2, -2)}</strong>)
    else if (tok.startsWith('*'))
      parts.push(<em key={i++}>{tok.slice(1, -1)}</em>)
    else if (tok.startsWith('`'))
      parts.push(
        <code key={i++} style={{ background: '#f4f4f5', padding: '0 4px' }}>
          {tok.slice(1, -1)}
        </code>,
      )
    else if (tok.startsWith('[')) {
      const lm = /\[([^\]]+)\]\(([^)]+)\)/.exec(tok)
      if (lm)
        parts.push(
          <a key={i++} href={lm[2]} style={{ color: '#1e6bb8' }}>
            {lm[1]}
          </a>,
        )
    }
    last = m.index + tok.length
  }
  if (last < s.length) parts.push(s.slice(last))
  return <>{parts}</>
}

export const DraftEditor = memo(DraftEditorRaw)