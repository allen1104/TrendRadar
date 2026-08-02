import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { MessageBubble } from '@/features/assistant/components/MessageBubble'
import { QuickQuestions } from '@/features/assistant/components/QuickQuestions'
import {
  assistantApi,
  consumeSSE,
  type AssistantMessage,
  type Feedback,
} from '@/features/assistant/api/assistant'
import {
  useCreateThread,
  useDeleteThread,
  useMessages,
  useQuickQuestions,
  useSetFeedback,
  useThreads,
} from '@/features/assistant/hooks/useAssistant'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface AssistantPanelProps {
  eventId: number
  eventTitle: string
  open: boolean
  onClose: () => void
  /** 当前用户是否登录（未登录时面板灰化所有功能） */
  isAuthenticated: boolean
}

/** 问 AI 抽屉内容（外层 Drawer/Sheet 由调用方包）。 */
export function AssistantPanel({
  eventId,
  eventTitle,
  open,
  onClose,
  isAuthenticated,
}: AssistantPanelProps) {
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [streamingMessageId, setStreamingMessageId] = useState<number | null>(null)
  const [streamingContent, setStreamingContent] = useState('')
  const [askedKeys, setAskedKeys] = useState<Set<string>>(new Set())
  const [remaining, setRemaining] = useState<number | null>(null) // TODO: hook to user rate limit
  const abortRef = useRef<AbortController | null>(null)
  const messageListRef = useRef<HTMLDivElement | null>(null)

  const threadsQ = useThreads(eventId)
  const quickQQ = useQuickQuestions()
  const messagesQ = useMessages(activeThreadId)
  const createThreadM = useCreateThread(eventId)
  const deleteThreadM = useDeleteThread(eventId)
  const setFeedbackM = useSetFeedback(eventId)

  // 打开面板且没有 active thread 时，自动选最近一个
  useEffect(() => {
    if (!open) return
    if (activeThreadId !== null) return
    const first = threadsQ.data?.[0]
    if (first) {
      setActiveThreadId(first.id)
    }
  }, [open, threadsQ.data, activeThreadId])

  // 流式期间实时滚到底
  useEffect(() => {
    if (!messageListRef.current) return
    messageListRef.current.scrollTop = messageListRef.current.scrollHeight
  }, [messagesQ.data?.length, streamingContent])

  const messages: AssistantMessage[] = useMemo(() => {
    const list = messagesQ.data ?? []
    if (!streamingMessageId || streamingContent === '') return list
    // 把流式中的 placeholder 替换为实时内容
    return list.map((m) =>
      m.id === streamingMessageId
        ? { ...m, content: streamingContent, status: 'STREAMING' as const }
        : m,
    )
  }, [messagesQ.data, streamingMessageId, streamingContent])

  // 真正发起流式调用（POST 到后端 SSE）
  const startStream = useCallback(
    async (threadId: number, question: string, quickQuestionKey: string | null) => {
      // 取消上一次
      abortRef.current?.abort()
      const ac = new AbortController()
      abortRef.current = ac
      setStreamingContent('')
      setStreamingMessageId(null)
      const url = `/api/v1/assistant/threads/${threadId}/messages`
      const ac2 = consumeSSE(
        url,
        { question, quickQuestionKey },
        {
          onStart: ({ messageId }) => {
            setStreamingMessageId(messageId)
          },
          onDelta: ({ content }) => {
            setStreamingContent((prev) => prev + content)
          },
          onDone: () => {
            setStreamingMessageId(null)
            setStreamingContent('')
            void messagesQ.refetch()
          },
          onError: ({ detail }) => {
            // eslint-disable-next-line no-alert
            alert(`生成失败：${detail}`)
            setStreamingMessageId(null)
            setStreamingContent('')
          },
        },
      )
      // 替换为最新 ac
      ac.abort()
      abortRef.current = ac2
    },
    [messagesQ],
  )

  const handleSend = useCallback(
    async (question: string, quickQuestionKey: string | null) => {
      if (!isAuthenticated) {
        // eslint-disable-next-line no-alert
        alert('请先登录')
        return
      }
      if (!question.trim()) return
      let threadId = activeThreadId
      if (threadId === null) {
        // 自动建一个新 thread
        const t = await createThreadM.mutateAsync()
        threadId = t.id
        setActiveThreadId(t.id)
      }
      if (quickQuestionKey) {
        setAskedKeys((prev) => new Set(prev).add(quickQuestionKey))
      }
      setDraft('')
      await startStream(threadId, question, quickQuestionKey)
    },
    [activeThreadId, createThreadM, startStream, isAuthenticated],
  )

  const handleRegenerate = useCallback(
    async (messageId: number) => {
      if (!isAuthenticated) return
      // 找到该 message 所在 thread + 上一次 USER message
      const msgs = messagesQ.data ?? []
      const idx = msgs.findIndex((m) => m.id === messageId)
      if (idx <= 0) return
      let userMsgIdx = idx - 1
      while (userMsgIdx >= 0 && msgs[userMsgIdx].role !== 'USER') userMsgIdx -= 1
      if (userMsgIdx < 0) return
      const userMsg = msgs[userMsgIdx]
      if (!activeThreadId) return
      const ac = new AbortController()
      abortRef.current?.abort()
      abortRef.current = ac
      setStreamingContent('')
      setStreamingMessageId(null)
      const url = `/api/v1/assistant/messages/${messageId}/regenerate`
      consumeSSE(
        url,
        {},
        {
          onStart: ({ messageId: mid }) => setStreamingMessageId(mid),
          onDelta: ({ content }) => setStreamingContent((prev) => prev + content),
          onDone: () => {
            setStreamingMessageId(null)
            setStreamingContent('')
            void messagesQ.refetch()
          },
          onError: ({ detail }) => {
            // eslint-disable-next-line no-alert
            alert(`重新生成失败：${detail}`)
            setStreamingMessageId(null)
            setStreamingContent('')
          },
        },
      )
      void userMsg // referenced for clarity
    },
    [messagesQ, activeThreadId, isAuthenticated],
  )

  const handleFeedback = useCallback(
    (messageId: number, feedback: Feedback) => {
      if (!isAuthenticated) return
      setFeedbackM.mutate({ messageId, feedback })
    },
    [setFeedbackM, isAuthenticated],
  )

  const handleNewThread = useCallback(async () => {
    const t = await createThreadM.mutateAsync()
    setActiveThreadId(t.id)
    setStreamingMessageId(null)
    setStreamingContent('')
    setAskedKeys(new Set())
  }, [createThreadM])

  const handleDeleteThread = useCallback(
    async (threadId: number) => {
      // eslint-disable-next-line no-alert
      if (!window.confirm('确认删除该会话？')) return
      await deleteThreadM.mutateAsync(threadId)
      if (activeThreadId === threadId) {
        setActiveThreadId(null)
        setStreamingMessageId(null)
        setStreamingContent('')
      }
    },
    [deleteThreadM, activeThreadId],
  )

  // 关闭面板时取消流式
  useEffect(() => {
    if (!open) {
      abortRef.current?.abort()
      abortRef.current = null
      setStreamingMessageId(null)
      setStreamingContent('')
    }
  }, [open])

  // 占位限流计数（接口 SPEC §限流；本期不做 headroom 计算，仅占位）
  useEffect(() => {
    if (!isAuthenticated) return
    setRemaining(20) // 始终按 system_config.ai_user_rate_limit 默认值占位
  }, [isAuthenticated])

  const isStreaming = streamingMessageId !== null
  const threads = threadsQ.data ?? []
  const quickQuestions = quickQQ.data?.items ?? []

  return (
    <div
      className={cn(
        'flex h-full w-full flex-col bg-background',
        !open && 'hidden',
      )}
    >
      {/* Header */}
      <header className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-medium">💬 问 AI</h2>
          <p className="mt-0.5 text-xs text-muted-foreground truncate">
            关于：{eventTitle}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleNewThread}
            disabled={!isAuthenticated || createThreadM.isPending}
            title="新建会话"
          >
            ⟳
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose} title="关闭">
            ✕
          </Button>
        </div>
      </header>

      {/* Thread 切换 */}
      {threads.length > 0 && (
        <div className="border-b border-border px-4 py-2 flex items-center gap-2">
          <select
            className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-xs"
            value={activeThreadId ?? ''}
            onChange={(e) => {
              const v = e.target.value ? Number(e.target.value) : null
              setActiveThreadId(v)
              setAskedKeys(new Set())
            }}
          >
            {threads.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}（{t.messageCount}）
              </option>
            ))}
          </select>
          {activeThreadId !== null && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleDeleteThread(activeThreadId)}
              title="删除会话"
              className="text-destructive"
            >
              🗑
            </Button>
          )}
        </div>
      )}

      {/* Message list */}
      <div
        ref={messageListRef}
        className="flex-1 overflow-y-auto px-4 py-3 space-y-4"
      >
        {!isAuthenticated && (
          <div className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
            请先登录，即可向 AI 提问。
          </div>
        )}
        {isAuthenticated && (messagesQ.data?.length ?? 0) === 0 && !isStreaming && (
          <div className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
            还没有对话。从下方快捷问题开始，或直接输入你的问题。
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            onFeedback={isAuthenticated ? handleFeedback : undefined}
            onRegenerate={isAuthenticated ? handleRegenerate : undefined}
          />
        ))}
        {isStreaming && streamingContent === '' && (
          <div className="text-xs text-muted-foreground italic">AI 正在思考…</div>
        )}
      </div>

      {/* Quick questions */}
      {isAuthenticated && quickQuestions.length > 0 && activeThreadId !== null && (
        <div className="border-t border-border px-4 py-2">
          <p className="text-xs text-muted-foreground mb-1">快捷提问：</p>
          <QuickQuestions
            items={quickQuestions}
            askedKeys={askedKeys}
            onPick={(q) => void handleSend(q.question, q.key)}
          />
        </div>
      )}

      {/* Input */}
      <div className="border-t border-border px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void handleSend(draft, null)
              }
            }}
            placeholder={isAuthenticated ? '输入你的问题…' : '请先登录'}
            disabled={!isAuthenticated}
            rows={2}
            maxLength={1000}
            className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button
            onClick={() => void handleSend(draft, null)}
            disabled={!isAuthenticated || !draft.trim() || isStreaming}
            className="self-stretch"
          >
            {isStreaming ? '停止' : '发送'}
          </Button>
        </div>
        <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>{draft.length}/1000</span>
          {remaining !== null && (
            <span>本小时剩余 {remaining}/20 次</span>
          )}
        </div>
      </div>
    </div>
  )
}

// 防止 Tree-shaking 把 ApiError 引用抹掉（api.ts 内部 re-export）
void assistantApi