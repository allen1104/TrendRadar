/** trend Query hooks。*/

import { useQuery } from '@tanstack/react-query'

import { trendApi, type TrendWindow } from '@/features/trend/api/trend'

export const trendKeys = {
  all: ['trends'] as const,
  keywords: (params: { window: TrendWindow; metric?: string; limit?: number }) =>
    ['trends', 'keywords', params] as const,
  entities: (params: {
    window: TrendWindow
    entityType?: string
    limit?: number
  }) => ['trends', 'entities', params] as const,
  wordcloud: (params: { window: TrendWindow; limit?: number; type?: string }) =>
    ['trends', 'wordcloud', params] as const,
  overview: (window: TrendWindow) => ['trends', 'overview', window] as const,
  keywordDetail: (kw: string, window: TrendWindow) =>
    ['trends', 'keyword-detail', kw, window] as const,
}

export function useKeywordTrends(
  window: TrendWindow,
  metric?: 'GROWTH' | 'HOT',
  limit?: number,
) {
  return useQuery({
    queryKey: trendKeys.keywords({ window, metric, limit }),
    queryFn: () => trendApi.keywords({ window, metric, limit }),
    placeholderData: (prev) => prev,
    staleTime: 5 * 60_000,
  })
}

export function useEntityTrends(
  window: TrendWindow,
  entityType?: 'COMPANY' | 'PRODUCT' | 'TECH' | 'PERSON' | 'ALL',
  limit?: number,
) {
  return useQuery({
    queryKey: trendKeys.entities({ window, entityType, limit }),
    queryFn: () => trendApi.entities({ window, entityType, limit }),
    placeholderData: (prev) => prev,
    staleTime: 5 * 60_000,
  })
}

export function useWordCloud(window: TrendWindow, limit?: number, type?: string) {
  return useQuery({
    queryKey: trendKeys.wordcloud({ window, limit, type }),
    queryFn: () => trendApi.wordcloud({ window, limit, type }),
    staleTime: 5 * 60_000,
  })
}

export function useOverview(window: TrendWindow) {
  return useQuery({
    queryKey: trendKeys.overview(window),
    queryFn: () => trendApi.overview({ window }),
    staleTime: 5 * 60_000,
  })
}

export function useKeywordDetail(keyword: string, window: TrendWindow) {
  return useQuery({
    queryKey: trendKeys.keywordDetail(keyword, window),
    queryFn: () => trendApi.keywordDetail(keyword, { window }),
    enabled: !!keyword,
    staleTime: 5 * 60_000,
  })
}
