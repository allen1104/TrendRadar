import { http } from '@/lib/api/client'

// ---------- 类型 ----------

export type ReportType = 'AI' | 'TECH' | 'GITHUB' | 'AGENT'
export type ReportStatus = 'GENERATING' | 'DRAFT' | 'PUBLISHED' | 'FAILED'
export type ExportFormat = 'MARKDOWN' | 'HTML' | 'PDF' | 'WECHAT_HTML'
export type SubscriptionChannel = 'SITE' | 'EMAIL' | 'WEBHOOK'

export const REPORT_TYPE_NAMES: Record<ReportType, string> = {
  AI: 'AI 日报',
  TECH: '科技日报',
  GITHUB: 'GitHub 日报',
  AGENT: 'Agent 日报',
}

export interface ReportSummary {
  id: number
  reportType: ReportType
  reportDate: string
  title: string
  intro: string | null
  itemCount: number
  status: ReportStatus
  publishedAt: string | null
  viewCount: number
}

export interface ReportListResponse {
  items: ReportSummary[]
  total: number
  page: number
  size: number
  pages: number
}

export interface ReportLatestItem {
  reportType: ReportType
  id: number
  title: string
  reportDate: string
  itemCount: number
  publishedAt: string | null
}

export interface ReportItemEventInfo {
  id: number
  recommendIndex: number
  sourceCount: number
  categories: string[]
  primaryArticleUrl: string | null
}

export interface ReportItemWithEvent {
  id: number
  eventId: number
  section: string
  sortOrder: number
  headline: string
  brief: string
  comment: string | null
  isTop: boolean
  event: ReportItemEventInfo | null
}

export interface ReportSection {
  name: string
  items: ReportItemWithEvent[]
}

export interface ReportDetail {
  id: number
  reportType: ReportType
  reportDate: string
  title: string
  intro: string | null
  outro: string | null
  contentMd: string
  contentEdited: string | null
  itemCount: number
  status: ReportStatus
  publishedAt: string | null
  viewCount: number
  modelAlias: string | null
  costUsd: number
  sections: ReportSection[]
}

export interface Subscription {
  reportTypes: ReportType[]
  channel: SubscriptionChannel
  webhookUrl: string | null
  rssToken: string | null
  rssUrl: string | null
  enabled: boolean
}

// ---------- API ----------

export const reportApi = {
  list(params?: {
    reportType?: ReportType
    status?: string
    startDate?: string
    endDate?: string
    page?: number
    size?: number
  }) {
    return http
      .get<ReportListResponse>('/reports', { params })
      .then((r) => r.data)
  },

  latest() {
    return http.get<ReportLatestItem[]>('/reports/latest').then((r) => r.data)
  },

  detail(id: number) {
    return http.get<ReportDetail>(`/reports/${id}`).then((r) => r.data)
  },

  async export(id: number, format: ExportFormat): Promise<Blob> {
    const r = await http.get(`/reports/${id}/export`, {
      params: { format },
      responseType: 'blob',
    })
    return r.data as Blob
  },

  rssUrl(token?: string) {
    return token
      ? `/api/v1/reports/rss?token=${encodeURIComponent(token)}`
      : `/api/v1/reports/rss`
  },

  getSubscription() {
    return http
      .get<Subscription | null>('/reports/subscription')
      .then((r) => r.data)
  },

  putSubscription(payload: {
    reportTypes: ReportType[]
    channel: SubscriptionChannel
    webhookUrl?: string | null
    enabled?: boolean
  }) {
    return http
      .put<Subscription>('/reports/subscription', payload)
      .then((r) => r.data)
  },

  resetRssToken() {
    return http
      .post<{ rssToken: string; rssUrl: string }>(
        '/reports/subscription/rss-token/reset',
      )
      .then((r) => r.data)
  },

  // ----------------- admin -----------------

  generate(payload: {
    reportType: ReportType
    reportDate: string
    force?: boolean
  }) {
    return http
      .post<{
        reportId?: number
        status?: string
        skipped?: boolean
        detail?: string
      }>('/admin/reports/generate', payload)
      .then((r) => r.data)
  },

  update(id: number, payload: {
    title?: string
    intro?: string | null
    outro?: string | null
    contentEdited?: string | null
  }) {
    return http
      .patch<ReportDetail>(`/admin/reports/${id}`, payload)
      .then((r) => r.data)
  },

  publish(id: number) {
    return http
      .post<ReportDetail>(`/admin/reports/${id}/publish`)
      .then((r) => r.data)
  },

  unpublish(id: number) {
    return http
      .post<ReportDetail>(`/admin/reports/${id}/unpublish`)
      .then((r) => r.data)
  },

  updateItem(reportId: number, itemId: number, payload: {
    headline?: string
    brief?: string
    comment?: string | null
    section?: string
    sortOrder?: number
    isTop?: boolean
  }) {
    return http
      .patch<ReportItemWithEvent>(
        `/admin/reports/${reportId}/items/${itemId}`,
        payload,
      )
      .then((r) => r.data)
  },

  deleteItem(reportId: number, itemId: number) {
    return http
      .delete<void>(`/admin/reports/${reportId}/items/${itemId}`)
      .then(() => undefined)
  },

  addItem(reportId: number, payload: {
    eventId: number
    section: string
    headline?: string
    brief?: string
  }) {
    return http
      .post<ReportItemWithEvent>(
        `/admin/reports/${reportId}/items`,
        payload,
      )
      .then((r) => r.data)
  },
}