/** trend API：关键词趋势 / 实体趋势 / 词云 / 总览 / 关键词下钻。*/

import { http } from '@/lib/api/client'

export type TrendWindow = '7D' | '30D' | '1Y'
export type TrendMetric = 'GROWTH' | 'HOT'
export type EntityType = 'COMPANY' | 'PRODUCT' | 'TECH' | 'PERSON' | 'ALL'

export interface KeywordPoint {
  date: string
  eventCount: number
  articleCount: number | null
  heatSum: number | null
}

export interface KeywordTrendItem {
  keyword: string
  displayName: string
  current: number
  previous: number
  growthRate: number
  growthAbs: number
  growthScore: number
  heatSum: number
  isNew: boolean
  series: KeywordPoint[]
}

export interface KeywordTrendResponse {
  window: TrendWindow
  metric: TrendMetric
  items: KeywordTrendItem[]
  newcomers: KeywordTrendItem[]
}

export interface EntityTrendItem {
  tagId: number
  displayName: string
  entityType: EntityType
  current: number
  previous: number
  growthRate: number
  growthAbs: number
  growthScore: number
  heatSum: number
  avgValueScore: number | null
  series: KeywordPoint[]
}

export interface EntityTrendResponse {
  window: TrendWindow
  entityType: EntityType
  items: EntityTrendItem[]
}

export interface WordCloudItem {
  text: string
  value: number
  type: string
  growthRate: number | null
  tagId: number | null
}

export interface WordCloudResponse {
  window: TrendWindow
  items: WordCloudItem[]
}

export interface TrendSummary {
  totalEvents: number
  totalArticles: number
  avgEventsPerDay: number
  eventGrowthRate: number
}

export interface DailySeriesPoint {
  date: string
  eventCount: number
  articleCount: number
  avgRecommend: number | null
}

export interface CategoryDistribution {
  category: string
  count: number
  growthRate: number
}

export interface RegionDistribution {
  region: string
  count: number
}

export interface RisingItem {
  displayName: string
  growthRate: number
  current: number | null
}

export interface OverviewResponse {
  window: TrendWindow
  summary: TrendSummary
  dailySeries: DailySeriesPoint[]
  categoryDistribution: CategoryDistribution[]
  regionDistribution: RegionDistribution[]
  topRisingKeywords: RisingItem[]
  topCompanies: RisingItem[]
  topProjects: RisingItem[]
}

export interface RelatedEvent {
  id: number
  title: string
  recommendIndex: number
  lastSeenAt: string | null
}

export interface RelatedKeyword {
  displayName: string
  coOccurrence: number
}

export interface KeywordDetailResponse {
  keyword: string
  displayName: string
  window: TrendWindow
  series: KeywordPoint[]
  growthRate: number
  relatedKeywords: RelatedKeyword[]
  topEvents: RelatedEvent[]
}

function qs(params: Record<string, unknown>): string {
  const parts: string[] = []
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

export const trendApi = {
  keywords: (params: {
    window?: TrendWindow
    metric?: TrendMetric
    limit?: number
    includeNew?: boolean
  } = {}) => http.get<KeywordTrendResponse>(`/api/v1/trends/keywords${qs(params)}`).then(r => r.data),

  entities: (params: {
    window?: TrendWindow
    entityType?: EntityType
    limit?: number
  } = {}) => http.get<EntityTrendResponse>(`/api/v1/trends/entities${qs(params)}`).then(r => r.data),

  wordcloud: (params: {
    window?: TrendWindow
    limit?: number
    type?: string
  } = {}) => http.get<WordCloudResponse>(`/api/v1/trends/wordcloud${qs(params)}`).then(r => r.data),

  overview: (params: { window?: TrendWindow } = {}) =>
    http.get<OverviewResponse>(`/api/v1/trends/overview${qs(params)}`).then(r => r.data),

  keywordDetail: (keyword: string, params: { window?: TrendWindow } = {}) =>
    http.get<KeywordDetailResponse>(`/api/v1/trends/keywords/${encodeURIComponent(keyword)}${qs(params)}`).then(r => r.data),
}
