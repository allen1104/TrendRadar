import { http } from '@/lib/api/client'

// ---------- 类型（与后端 schema 对齐） ----------

export type Platform =
  | 'WECHAT'
  | 'BLOG'
  | 'WEIBO'
  | 'XHS'
  | 'ZHIHU'
  | 'MARKDOWN'

export type Style =
  | 'TECHNICAL'
  | 'MARKETING'
  | 'DEEP_DIVE'
  | 'NEWS'
  | 'CASUAL'

export type DraftStatus = 'GENERATING' | 'DONE' | 'FAILED'
export type ExportFormat = 'MARKDOWN' | 'HTML' | 'WECHAT_HTML' | 'TXT'

export interface PlatformOption {
  key: Platform
  name: string
  icon: string
  targetWords: [number, number]
  description: string
}

export interface StyleOption {
  key: Style
  name: string
  description: string
}

export interface OptionsResponse {
  platforms: PlatformOption[]
  styles: StyleOption[]
}

export interface OutlineItem {
  heading: string
  points: string[]
}

export interface DraftSummary {
  id: number
  eventId: number
  eventTitle: string | null
  platform: Platform
  style: Style
  title: string
  wordCount: number
  isEdited: boolean
  status: DraftStatus
  regenerateCount: number
  costUsd: number
  createdAt: string
}

export interface DraftListResponse {
  items: DraftSummary[]
  total: number
  page: number
  size: number
  pages: number
}

export interface DraftDetail {
  id: number
  userId: number
  eventId: number
  platform: Platform
  style: Style
  title: string
  content: string
  contentEdited: string | null
  outline: OutlineItem[]
  coverSuggestion: string | null
  tagsSuggestion: string[]
  wordCount: number
  extraParams: Record<string, unknown>
  modelAlias: string | null
  promptVersion: number | null
  costUsd: number
  status: DraftStatus
  errorMessage: string | null
  regenerateCount: number
  createdAt: string
  updatedAt: string
}

// ---------- 事件 payload ----------

export interface StreamStartEvent {
  draftId: number
  modelAlias: string | null
}

export interface StreamOutlineEvent {
  outline: OutlineItem[]
}

export interface StreamDeltaEvent {
  content: string
}

export interface StreamDoneEvent {
  draftId: number
  title: string
  wordCount: number
  coverSuggestion: string | null
  tagsSuggestion: string[]
  costUsd: number
  latencyMs: number
}

export interface StreamErrorEvent {
  errorCode: string
  detail: string
}

export type StreamEvent =
  | { event: 'start'; data: StreamStartEvent }
  | { event: 'outline'; data: StreamOutlineEvent }
  | { event: 'delta'; data: StreamDeltaEvent }
  | { event: 'done'; data: StreamDoneEvent }
  | { event: 'error'; data: StreamErrorEvent }

// ---------- API ----------

function qs(params: Record<string, unknown>): string {
  const usp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => usp.append(k, String(x)))
    else usp.append(k, String(v))
  }
  const s = usp.toString()
  return s ? `?${s}` : ''
}

export interface CreateDraftBody {
  eventId: number
  platform: Platform
  style: Style
  targetWords?: number
  audience?: string | null
  extraRequirement?: string | null
}

export interface RegenerateBody {
  style?: Style
  targetWords?: number
  audience?: string | null
  extraRequirement?: string | null
}

export const creationApi = {
  options: () =>
    http.get<OptionsResponse>('/creation/options').then((r) => r.data),

  list: (params: {
    eventId?: number
    platform?: Platform
    style?: Style
    keyword?: string
    sort?: string
    page?: number
    size?: number
  }) =>
    http
      .get<DraftListResponse>(`/creation/drafts${qs(params as Record<string, unknown>)}`)
      .then((r) => r.data),

  get: (draftId: number) =>
    http.get<DraftDetail>(`/creation/drafts/${draftId}`).then((r) => r.data),

  update: (
    draftId: number,
    body: { title?: string; contentEdited?: string | null },
  ) =>
    http
      .patch<DraftDetail>(`/creation/drafts/${draftId}`, body)
      .then((r) => r.data),

  delete: (draftId: number) =>
    http.delete(`/creation/drafts/${draftId}`).then(() => undefined),
}

// ---------- SSE 消费者 ----------

export interface StreamHandlers {
  onStart?: (data: StreamStartEvent) => void
  onOutline?: (data: StreamOutlineEvent) => void
  onDelta?: (data: StreamDeltaEvent) => void
  onDone?: (data: StreamDoneEvent) => void
  onError?: (data: StreamErrorEvent) => void
}

/** 通过 fetch + ReadableStream 手动解析 SSE（EventSource 不支持 POST body）。 */
export function consumeSSE(
  url: string,
  body: CreateDraftBody | RegenerateBody,
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
        let sep: number
        // eslint-disable-next-line no-cond-assign
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          parseFrame(frame, handlers)
        }
      }
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
      handlers.onStart?.(parsed as StreamStartEvent)
      break
    case 'outline':
      handlers.onOutline?.(parsed as StreamOutlineEvent)
      break
    case 'delta':
      handlers.onDelta?.(parsed as StreamDeltaEvent)
      break
    case 'done':
      handlers.onDone?.(parsed as StreamDoneEvent)
      break
    case 'error':
      handlers.onError?.(parsed as StreamErrorEvent)
      break
    default:
      break
  }
}

/** 下载导出文件（触发浏览器下载）。 */
export async function downloadExport(
  draftId: number,
  format: ExportFormat,
): Promise<void> {
  const resp = await fetch(`/api/v1/creation/drafts/${draftId}/export?format=${format}`, {
    credentials: 'include',
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  const blob = await resp.blob()
  const dispo = resp.headers.get('Content-Disposition') ?? ''
  const m = /filename="([^"]+)"/.exec(dispo)
  const filename = m?.[1] ?? `draft.${format.toLowerCase()}`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}