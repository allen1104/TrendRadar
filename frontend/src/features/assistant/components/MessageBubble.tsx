import { memo, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import type { AssistantMessage, CitationItem, Feedback } from '@/features/assistant/api/assistant'
import { cn } from '@/lib/utils'

interface MessageBubbleProps {
  message: AssistantMessage
  /** 当前用户对此消息是否有反馈（与 message.feedback 同源，乐观更新用） */
  onFeedback?: (messageId: number, feedback: Feedback) => void
  onRegenerate?: (messageId: number) => void
}

/**
 * 渲染单条消息（USER 或 ASSISTANT）。
 * ASSISTANT 消息额外渲染 Markdown、引用上标、工具条（👍/👎/重新生成/复制）。
 */
function MessageBubbleRaw({ message, onFeedback, onRegenerate }: MessageBubbleProps) {
  const isUser = message.role === 'USER'

  return (
    <div className={cn('flex flex-col gap-2', isUser ? 'items-end' : 'items-start')}>
      <div
        className={cn(
          'max-w-[90%] rounded-lg px-3 py-2 text-sm leading-relaxed break-words',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground border border-border',
        )}
      >
        {message.content ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeSanitize]}
              components={markdownComponents(message.citations)}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        ) : isUser ? (
          <span className="opacity-60">…</span>
        ) : (
          <span className="opacity-50 italic">正在生成…</span>
        )}
      </div>

      {/* ASSISTANT 工具条 */}
      {!isUser && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <button
            type="button"
            aria-label="点赞"
            title="点赞"
            disabled={!onFeedback}
            onClick={() => onFeedback?.(message.id, message.feedback === 'LIKE' ? null : 'LIKE')}
            className={cn(
              'hover:text-foreground transition',
              message.feedback === 'LIKE' && 'text-primary font-medium',
            )}
          >
            👍
          </button>
          <button
            type="button"
            aria-label="点踩"
            title="点踩"
            disabled={!onFeedback}
            onClick={() =>
              onFeedback?.(message.id, message.feedback === 'DISLIKE' ? null : 'DISLIKE')
            }
            className={cn(
              'hover:text-foreground transition',
              message.feedback === 'DISLIKE' && 'text-destructive font-medium',
            )}
          >
            👎
          </button>
          {onRegenerate && message.status === 'DONE' && (
            <button
              type="button"
              aria-label="重新生成"
              title="重新生成"
              onClick={() => onRegenerate(message.id)}
              className="hover:text-foreground transition"
            >
              ⟳ 重新生成
            </button>
          )}
          <button
            type="button"
            aria-label="复制"
            title="复制 Markdown"
            onClick={() => {
              void navigator.clipboard.writeText(message.content)
            }}
            className="hover:text-foreground transition"
          >
            📋
          </button>
          {message.modelAlias && message.status === 'DONE' && (
            <span className="ml-1 opacity-70">
              {message.modelAlias} · {(message.latencyMs ?? 0) / 1000}s · $
              {message.costUsd.toFixed(4)}
            </span>
          )}
          {message.errorMessage && (
            <span className="text-destructive ml-1">⚠ {message.errorMessage}</span>
          )}
        </div>
      )}

      {/* ASSISTANT 引用来源列表 */}
      {!isUser && message.citations.length > 0 && message.status === 'DONE' && (
        <details className="text-xs text-muted-foreground max-w-[90%]">
          <summary className="cursor-pointer hover:text-foreground">📎 引用来源</summary>
          <ol className="mt-1 space-y-1 list-decimal list-inside">
            {message.citations.map((c) => (
              <li key={`${c.index}-${c.articleId}`}>
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline"
                >
                  {c.title}
                </a>
                <span className="opacity-60 ml-1">· {c.sourceName}</span>
              </li>
            ))}
          </ol>
        </details>
      )}

      {/* FAILED 状态 */}
      {!isUser && message.status === 'FAILED' && (
        <div className="text-xs text-destructive">
          生成失败{message.errorMessage ? `：${message.errorMessage}` : ''}
        </div>
      )}
    </div>
  )
}

/**
 * 把文本中的 [n] 替换为带 tooltip 的上标 <sup>。
 * 由 react-markdown 回调传入 children（可能是 string / array）。
 */
function renderCitationsInNode(
  children: React.ReactNode,
  citations: CitationItem[],
): React.ReactNode {
  if (citations.length === 0) return children
  const byIndex = new Map(citations.map((c) => [c.index, c]))
  return walkAndReplaceCitations(children, byIndex)
}

function walkAndReplaceCitations(
  node: ReactNode,
  byIndex: Map<number, CitationItem>,
): ReactNode {
  if (typeof node === 'string') {
    const parts = node.split(/(\[\d+\])/g)
    if (parts.length === 1) return node
    return parts.map((part, i) => {
      const m = /^\[(\d+)\]$/.exec(part)
      if (!m) return part
      const idx = Number(m[1])
      const c = byIndex.get(idx)
      if (!c) return part
      return (
        <sup key={`cite-${idx}-${i}`} className="mx-0.5">
          <a
            href={c.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary no-underline hover:underline"
            title={`[${idx}] ${c.title} · ${c.sourceName}`}
          >
            [{idx}]
          </a>
        </sup>
      )
    })
  }
  if (Array.isArray(node)) {
    return node.map((child, i) => (
      <span key={i}>{walkAndReplaceCitations(child, byIndex)}</span>
    ))
  }
  return node
}

export const MessageBubble = memo(MessageBubbleRaw)

/** react-markdown 组件映射（把 [n] 渲染成可点击上标）。 */
function markdownComponents(citations: CitationItem[]): Components {
  return {
    p: ({ children }) => <p>{renderCitationsInNode(children, citations)}</p>,
    li: ({ children }) => <li>{renderCitationsInNode(children, citations)}</li>,
  }
}

// 显式声明避免未用导入报错
void Object