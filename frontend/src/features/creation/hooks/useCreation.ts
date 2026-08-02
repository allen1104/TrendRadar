import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  creationApi,
  type CreateDraftBody,
  type ExportFormat,
  type RegenerateBody,
} from '@/features/creation/api/creation'

export const creationKeys = {
  all: ['creation'] as const,
  options: () => ['creation', 'options'] as const,
  list: (params: Record<string, unknown>) => ['creation', 'list', params] as const,
  detail: (id: number) => ['creation', 'detail', id] as const,
}

export function useCreationOptions() {
  return useQuery({
    queryKey: creationKeys.options(),
    queryFn: () => creationApi.options(),
    staleTime: 5 * 60_000,
  })
}

export function useCreationDrafts(params: {
  eventId?: number
  platform?: import('@/features/creation/api/creation').Platform
  style?: import('@/features/creation/api/creation').Style
  keyword?: string
  sort?: string
  page?: number
  size?: number
}) {
  return useQuery({
    queryKey: creationKeys.list(params as Record<string, unknown>),
    queryFn: () => creationApi.list(params),
    staleTime: 30_000,
  })
}

export function useCreationDraft(draftId: number | null) {
  return useQuery({
    queryKey: creationKeys.detail(draftId ?? 0),
    queryFn: () => creationApi.get(draftId as number),
    enabled: draftId !== null && draftId > 0,
    staleTime: 10_000,
  })
}

export function useUpdateDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      draftId,
      ...body
    }: {
      draftId: number
      title?: string
      contentEdited?: string | null
    }) => creationApi.update(draftId, body),
    onSuccess: (draft) => {
      qc.setQueryData(creationKeys.detail(draft.id), draft)
      qc.invalidateQueries({ queryKey: ['creation', 'list'] })
    },
  })
}

export function useDeleteDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (draftId: number) => creationApi.delete(draftId),
    onSuccess: (_void, draftId) => {
      qc.removeQueries({ queryKey: creationKeys.detail(draftId) })
      qc.invalidateQueries({ queryKey: ['creation', 'list'] })
    },
  })
}

/** 在调用方直接用 consumeSSE；hook 只负责 invalidate。 */
export function useInvalidateAfterStream() {
  const qc = useQueryClient()
  return (draftId?: number) => {
    qc.invalidateQueries({ queryKey: ['creation', 'list'] })
    if (draftId) qc.invalidateQueries({ queryKey: creationKeys.detail(draftId) })
  }
}

/** 同步生成/重新生成的 body 类型。 */
export type { CreateDraftBody, RegenerateBody, ExportFormat }