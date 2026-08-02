import { ApiError, http } from '@/lib/api/client'

// ---------- 类型（与后端 schema 对齐） ----------

export type MessageRole = 'USER' | 'ASSISTANT'
export type MessageStatus = 'PENDING' | 'STREAMING' | 'DONE' | 'FAILED'
export type Feedback = 'LIKE' | 'DISLIKE' | null

export interface ThreadSummary {
  id: number
  title: string
  messageCount: number
  lastMessageAt: string | null
  createdAt: string
}

export interface ThreadCreateResponse {
  id: number
  title: string
  messageCount: number
}

export interface CitationItem {
  index: number
  articleId: number
  title: string
  url: string
  sourceName: string
}

export interface AssistantMessage {
  id: number
  role: MessageRole
  content: string
  quickQuestionKey: string | null
  citations: CitationItem[]
  modelAlias: string | null
  promptTokens: number
  completionTokens: number
  costUsd: number
  latencyMs: number | null
  status: MessageStatus
  errorMessage: string | null
  feedback: Feedback
  createdAt: string
}

export interface QuickQuestion {
  key: string
  label: string
  question: string
}

// ---------- 事件 payload（前端自定义） ----------

export interface StreamDoneEvent {
  messageId: number
  promptTokens: number
  completionTokens: number
  costUsd: number
  latencyMs: number
}

export interface StreamErrorEvent {
  errorCode: string
  detail: string
}

export type StreamEvent =
  | { event: 'start'; data: { messageId: number; modelAlias: string | null } }
  | { event: 'delta'; data: { content: string } }
  | { event: 'citations'; data: { citations: CitationItem[] } }
  | { event: 'done'; data: StreamDoneEvent }
  | { event: 'error'; data: StreamErrorEvent }

// ---------- API ----------

function qs(params: Record<string, unknown>): string {
  const usp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    usp.append(k, String(v))
  }
  const s = usp.toString()
  return s ? `?${s}` : ''
}

export const assistantApi = {
  // ----- 快捷问题（GUEST 可访问） -----
  quickQuestions: () =>
    http.get<{ items: QuickQuestion[] }>('/assistant/quick-questions').then((r) => r.data),

  // ----- thread 列表 / 创建 -----
  listThreads: (eventId: number) =>
    http.get<ThreadSummary[]>(`/events/${eventId}/assistant/threads${qs({})}`).then((r) => r.data),

  createThread: (eventId: number) =>
    http
      .post<ThreadCreateResponse>(`/events/${eventId}/assistant/threads`, {})
      .then((r) => r.data),

  // ----- messages -----
  listMessages: (threadId: number) =>
    http.get<AssistantMessage[]>(`/assistant/threads/${threadId}/messages`).then((r) => r.data),

  deleteThread: (threadId: number) =>
    http.delete(`/assistant/threads/${threadId}`).then(() => undefined),

  setFeedback: (messageId: number, feedback: Feedback) =>
    http
      .post(`/assistant/messages/${messageId}/feedback`, { feedback })
      .then(() => undefined),
}

// ---------- SSE 消费者 ----------

export interface StreamHandlers {
  onStart?: (data: { messageId: number; modelAlias: string | null }) => void
  onDelta?: (data: { content: string }) => void
  onCitations?: (data: { citations: CitationItem[] }) => void
  onDone?: (data: StreamDoneEvent) => void
  onError?: (data: StreamErrorEvent) => void
}

/**
 * 通过 fetch + ReadableStream 手动解析 SSE（EventSource 不支持 POST body）。
 * 返回 AbortController，调用 .abort() 即可中断（后端会保存已生成部分）。
 */
export function consumeSSE(
  url: string,
  body: { question?: string | null; quickQuestionKey?: string | null },
  handlers: StreamHandlers,
): AbortController {
  const ac = new AbortController()
  void (async () => {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ac.signal,
        credentials: 'include',
      })
      if (!resp.ok || !resp.body) {
        const text = await resp.text()
        handlers.onError?.({
          errorCode: 'HTTP_ERROR',
          detail: text || `HTTP ${resp.status}`,
        })
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // SSE 帧以 \n\n 分隔
        let sep: number
        // eslint-disable-next-line no-cond-assign
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          parseFrame(frame, handlers)
        }
      }
      // 流结束后残留的帧
      if (buffer.trim()) parseFrame(buffer, handlers)
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      handlers.onError?.({
        errorCode: 'NETWORK_ERROR',
        detail: (e as Error).message ?? '未知网络错误',
      })
    }
  })()
  return ac
}

function parseFrame(frame: string, handlers: StreamHandlers): void {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  const raw = dataLines.join('\n')
  if (!raw) return
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    parsed = raw
  }
  switch (event) {
    case 'start':
      handlers.onStart?.(parsed as { messageId: number; modelAlias: string | null })
      break
    case 'delta':
      handlers.onDelta?.(parsed as { content: string })
      break
    case 'citations':
      handlers.onCitations?.(parsed as { citations: CitationItem[] })
      break
    case 'done':
      handlers.onDone?.(parsed as StreamDoneEvent)
      break
    case 'error':
      handlers.onError?.(parsed as StreamErrorEvent)
      break
    default:
      // ignore unknown frames
      break
  }
}

// re-export ApiError for callers needing to catch non-SSE errors
export { ApiError }