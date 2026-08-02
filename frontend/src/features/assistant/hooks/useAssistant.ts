import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  assistantApi,
  type Feedback,
} from '@/features/assistant/api/assistant'

// ---------- Query keys ----------

export const assistantKeys = {
  all: ['assistant'] as const,
  quick: () => ['assistant', 'quick'] as const,
  threads: (eventId: number) => ['assistant', 'threads', eventId] as const,
  messages: (threadId: number) => ['assistant', 'messages', threadId] as const,
}

// ---------- Hooks ----------

export function useQuickQuestions() {
  return useQuery({
    queryKey: assistantKeys.quick(),
    queryFn: () => assistantApi.quickQuestions(),
    staleTime: 60_000,
  })
}

export function useThreads(eventId: number) {
  return useQuery({
    queryKey: assistantKeys.threads(eventId),
    queryFn: () => assistantApi.listThreads(eventId),
    enabled: eventId > 0,
    staleTime: 30_000,
  })
}

export function useCreateThread(eventId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => assistantApi.createThread(eventId),
    onSuccess: (newThread) => {
      qc.setQueryData<unknown[]>(assistantKeys.threads(eventId), (prev) =>
        prev ? [newThread, ...prev] : [newThread],
      )
      qc.invalidateQueries({ queryKey: assistantKeys.threads(eventId) })
    },
  })
}

export function useMessages(threadId: number | null) {
  return useQuery({
    queryKey: assistantKeys.messages(threadId ?? 0),
    queryFn: () => assistantApi.listMessages(threadId as number),
    enabled: threadId !== null && threadId > 0,
    staleTime: 10_000,
  })
}

export function useDeleteThread(_eventId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (threadId: number) => assistantApi.deleteThread(threadId),
    onSuccess: (_void, threadId) => {
      // 不依赖 eventId 直接精确失效：drop 该 thread 的消息缓存即可
      qc.removeQueries({ queryKey: assistantKeys.messages(threadId) })
      qc.invalidateQueries({ queryKey: assistantKeys.all })
    },
  })
}

export function useSetFeedback(_eventId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ messageId, feedback }: { messageId: number; feedback: Feedback }) =>
      assistantApi.setFeedback(messageId, feedback),
    // 乐观更新：UI 立即翻转；失败回滚
    onMutate: async ({ messageId, feedback }) => {
      // 找到所有 thread 的 messages 缓存
      const queries = qc
        .getQueryCache()
        .findAll({ queryKey: ['assistant', 'messages'] })
      const snapshots: Array<[readonly unknown[], unknown]> = []
      for (const q of queries) {
        const prev = q.state.data
        if (Array.isArray(prev)) {
          snapshots.push([q.queryKey, prev])
          qc.setQueryData(
            q.queryKey,
            (prev as { id: number; feedback: Feedback }[]).map((m) =>
              m.id === messageId ? { ...m, feedback } : m,
            ),
          )
        }
      }
      return { snapshots }
    },
    onError: (_e, _vars, ctx) => {
      if (!ctx) return
      for (const [key, data] of ctx.snapshots) {
        qc.setQueryData(key, data)
      }
    },
    onSettled: () => {
      // 静默刷新（不阻塞）
      void qc.invalidateQueries({ queryKey: ['assistant', 'messages'], refetchType: 'none' })
    },
  })
}