import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  collectionApi,
  type BatchPayload,
  type FolderCreatePayload,
  type FolderUpdatePayload,
  type ItemCreatePayload,
  type ItemListParams,
  type ItemUpdatePayload,
  type StatsResponse,
} from '@/features/collection/api/collection'

// ---------- Query keys ----------

export const collectionKeys = {
  all: ['collection'] as const,
  folders: () => ['collection', 'folders'] as const,
  items: (params: ItemListParams) => ['collection', 'items', params] as const,
  stats: () => ['collection', 'stats'] as const,
  collectedIds: (eventIds: number[]) =>
    ['collection', 'collected-ids', eventIds] as const,
}

// ---------- 文件夹 ----------

export function useFolders() {
  return useQuery({
    queryKey: collectionKeys.folders(),
    queryFn: () => collectionApi.listFolders(),
    staleTime: 30_000,
  })
}

export function useCreateFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: FolderCreatePayload) => collectionApi.createFolder(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: collectionKeys.folders() })
    },
  })
}

export function useUpdateFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: FolderUpdatePayload }) =>
      collectionApi.updateFolder(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: collectionKeys.folders() })
    },
  })
}

export function useDeleteFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => collectionApi.deleteFolder(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: collectionKeys.folders() })
      qc.invalidateQueries({ queryKey: ['collection', 'items'] })
    },
  })
}

// ---------- 条目 ----------

export function useItems(params: ItemListParams) {
  return useQuery({
    queryKey: collectionKeys.items(params),
    queryFn: () => collectionApi.listItems(params),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  })
}

export function useCreateItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ItemCreatePayload) => collectionApi.createItem(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collection', 'items'] })
      qc.invalidateQueries({ queryKey: collectionKeys.folders() })
      qc.invalidateQueries({ queryKey: collectionKeys.stats() })
      qc.invalidateQueries({ queryKey: ['events'] })
    },
  })
}

export function useUpdateItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ItemUpdatePayload }) =>
      collectionApi.updateItem(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collection', 'items'] })
      qc.invalidateQueries({ queryKey: collectionKeys.folders() })
      qc.invalidateQueries({ queryKey: collectionKeys.stats() })
    },
  })
}

export function useDeleteItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => collectionApi.deleteItem(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collection', 'items'] })
      qc.invalidateQueries({ queryKey: collectionKeys.folders() })
      qc.invalidateQueries({ queryKey: collectionKeys.stats() })
      qc.invalidateQueries({ queryKey: ['events'] })
    },
  })
}

export function useBatchItems() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: BatchPayload) => collectionApi.batchItems(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collection', 'items'] })
      qc.invalidateQueries({ queryKey: collectionKeys.folders() })
      qc.invalidateQueries({ queryKey: collectionKeys.stats() })
    },
  })
}

// ---------- 统计 ----------

export function useStats() {
  return useQuery<StatsResponse>({
    queryKey: collectionKeys.stats(),
    queryFn: () => collectionApi.getStats(),
    staleTime: 60_000,
  })
}

// ---------- 集成：当前用户已收藏 event_ids ----------

export function useCollectedEventIds(eventIds: number[]) {
  return useQuery({
    queryKey: collectionKeys.collectedIds(eventIds),
    queryFn: () => collectionApi.listCollectedEventIds(eventIds),
    enabled: eventIds.length > 0,
    staleTime: 30_000,
  })
}
