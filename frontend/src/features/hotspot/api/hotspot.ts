import { http, type Page } from '@/lib/api/client'

export type Scope = 'TODAY' | 'WEEK' | 'MONTH' | 'ALL'
export type CategoryFilter =
  | 'ALL'
  | 'GLOBAL'
  | 'CN'
  | 'AI'
  | 'GITHUB'
  | 'PAPER'
  | 'AGENT'
  | 'LLM'
  | 'MCP'
  | 'PROGRAMMING'
  | 'OPENSOURCE'
  | 'STARTUP'
  | 'HARDWARE'
  | 'INTERNET'
  | 'BUSINESS'

export type EventStatus =
  | 'PENDING_AI'
  | 'ANALYZING'
  | 'ANALYZED'
  | 'ARCHIVED'
  | 'AI_FAILED'

export interface SourceBrief {
  id: number
  name: string
  homeUrl: string | null
  weight: number | null
}

export interface TagItem {
  id: number
  displayName: string
  type: string
  weight: number | null
  eventCount: number | null
}

export interface EventListItem {
  id: number
  title: string
  summaryOneLine: string | null
  region: 'GLOBAL' | 'CN' | 'MIXED'
  categories: string[]
  tags: TagItem[]
  sourceCount: number
  articleCount: number
  sources: SourceBrief[]
  heatScore: number
  valueScore: number | null
  originalityScore: number | null
  trendScore: number | null
  recommendIndex: number
  worthArticle: boolean
  primaryArticleUrl: string | null
  firstSeenAt: string
  lastSeenAt: string
  status: EventStatus
  isPinned: boolean
  isHidden: boolean
  isManuallyEdited: boolean
  isCollected: boolean
}

export interface EventAnalysisDetail {
  summaryOneLine: string
  summary: string
  keyPoints: string[]
  innovations: string[]
  audience: string[]
  valueScore: number
  originalityScore: number
  trendScore: number
  worthArticle: boolean
  worthArticleWhy: string | null
  worthResearch: boolean
  worthResearchWhy: string | null
  modelAlias: string
  promptVersion: number
  analyzedAt: string
}

export interface EventArticleItem {
  id: number
  title: string
  url: string
  author: string | null
  lang: string
  publishedAt: string
  summary: string | null
  metrics: Record<string, number>
  source: SourceBrief | null
  isPrimary: boolean
  matchLevel: string | null
  similarity: number | null
}

export interface EventDetail {
  id: number
  title: string
  region: 'GLOBAL' | 'CN' | 'MIXED'
  categories: string[]
  tags: TagItem[]
  sourceCount: number
  articleCount: number
  heatScore: number
  recommendIndex: number
  valueScore: number | null
  originalityScore: number | null
  trendScore: number | null
  status: EventStatus
  isPinned: boolean
  isHidden: boolean
  isManuallyEdited: boolean
  manualLockedFields: string[]
  firstSeenAt: string
  lastSeenAt: string
  analysis: EventAnalysisDetail | null
  articles: EventArticleItem[]
  isCollected: boolean
}

export interface EventTrendPoint {
  date: string
  heatScore: number
  sourceCount: number
  articleCount: number
}

export interface EventTrendResponse {
  eventId: number
  points: EventTrendPoint[]
}

export interface RelatedEventItem {
  id: number
  title: string
  summaryOneLine: string | null
  recommendIndex: number
  lastSeenAt: string
  similarity: number | null
}

export interface EventListParams {
  scope?: Scope
  category?: CategoryFilter
  sort?: string
  keyword?: string
  tagIds?: number[]
  sourceIds?: number[]
  minRecommend?: number
  startDate?: string
  endDate?: string
  includeHidden?: boolean
  page?: number
  size?: number
}

export interface EventUpdatePayload {
  title?: string
  summaryOneLine?: string
  categories?: string[]
  isPinned?: boolean
  isHidden?: boolean
}

export const hotspotApi = {
  list: (params: EventListParams): Promise<Page<EventListItem>> =>
    http.get<Page<EventListItem>>('/events', { params }).then((r) => r.data),

  detail: (id: number): Promise<EventDetail> =>
    http.get<EventDetail>(`/events/${id}`).then((r) => r.data),

  trend: (id: number): Promise<EventTrendResponse> =>
    http.get<EventTrendResponse>(`/events/${id}/trend`).then((r) => r.data),

  related: (id: number, limit = 5): Promise<RelatedEventItem[]> =>
    http.get<RelatedEventItem[]>(`/events/${id}/related`, { params: { limit } }).then((r) => r.data),

  tags: (params?: { keyword?: string; type?: string; limit?: number }): Promise<TagItem[]> =>
    http.get<TagItem[]>('/tags', { params }).then((r) => r.data),

  update: (id: number, payload: EventUpdatePayload): Promise<EventDetail> =>
    http.patch<EventDetail>(`/events/${id}`, payload).then((r) => r.data),

  unlockField: (id: number, field: string): Promise<void> =>
    http.delete(`/events/${id}/manual-lock/${field}`).then(() => undefined),
}
