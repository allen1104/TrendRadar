import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  hotspotApi,
  type EventListParams,
  type EventUpdatePayload,
} from '@/features/hotspot/api/hotspot'

export const hotspotKeys = {
  all: ['events'] as const,
  list: (params: EventListParams) => ['events', 'list', params] as const,
  detail: (id: number) => ['events', 'detail', id] as const,
  trend: (id: number) => ['events', 'trend', id] as const,
  related: (id: number) => ['events', 'related', id] as const,
  tags: (params?: { keyword?: string; type?: string; limit?: number }) =>
    ['tags', params ?? {}] as const,
}

export function useEventList(params: EventListParams) {
  return useQuery({
    queryKey: hotspotKeys.list(params),
    queryFn: () => hotspotApi.list(params),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  })
}

export function useEventDetail(id: number, options?: { pollWhilePending?: boolean }) {
  return useQuery({
    queryKey: hotspotKeys.detail(id),
    queryFn: () => hotspotApi.detail(id),
    enabled: Number.isFinite(id) && id > 0,
    // AI 分析中时轮询，最多 10 次（30s × 10 = 5 分钟）
    refetchInterval: (query) => {
      if (!options?.pollWhilePending) return false
      const data = query.state.data
      if (!data) return false
      const pending = data.status === 'PENDING_AI' || data.status === 'ANALYZING'
      return pending && query.state.dataUpdateCount < 10 ? 30_000 : false
    },
  })
}

export function useEventTrend(id: number) {
  return useQuery({
    queryKey: hotspotKeys.trend(id),
    queryFn: () => hotspotApi.trend(id),
    enabled: Number.isFinite(id) && id > 0,
    staleTime: 5 * 60_000,
  })
}

export function useRelatedEvents(id: number, limit = 5) {
  return useQuery({
    queryKey: hotspotKeys.related(id),
    queryFn: () => hotspotApi.related(id, limit),
    enabled: Number.isFinite(id) && id > 0,
    staleTime: 5 * 60_000,
  })
}

export function useTags(params?: { keyword?: string; type?: string; limit?: number }) {
  return useQuery({
    queryKey: hotspotKeys.tags(params),
    queryFn: () => hotspotApi.tags(params),
    staleTime: 5 * 60_000,
  })
}

export function useUpdateEvent(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: EventUpdatePayload) => hotspotApi.update(id, payload),
    onSuccess: (data) => {
      qc.setQueryData(hotspotKeys.detail(id), data)
      void qc.invalidateQueries({ queryKey: ['events', 'list'] })
    },
  })
}

export function useUnlockField(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (field: string) => hotspotApi.unlockField(id, field),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: hotspotKeys.detail(id) })
    },
  })
}
