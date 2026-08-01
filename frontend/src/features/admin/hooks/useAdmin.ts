import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  adminApi,
  type AuditAction,
  type ConfigGroup,
  type TaskRunStatus,
  type TaskTriggerRequest,
  type TriggerType,
  type TargetType,
} from '@/features/admin/api/admin'

// ---------------- Dashboard

export function useDashboard() {
  return useQuery({
    queryKey: ['admin', 'dashboard'],
    queryFn: () => adminApi.getDashboard(),
    refetchInterval: 30_000,
  })
}

// ---------------- Configs

export function useConfigs(group?: ConfigGroup) {
  return useQuery({
    queryKey: ['admin', 'configs', group ?? null],
    queryFn: () => adminApi.listConfigs(group),
  })
}

export function useUpdateConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      adminApi.updateConfig(key, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'configs'] }),
  })
}

// ---------------- Tasks

export function useTaskDefinitions() {
  return useQuery({
    queryKey: ['admin', 'tasks', 'definitions'],
    queryFn: () => adminApi.listTaskDefinitions(),
    refetchInterval: 10_000,
  })
}

export interface TaskLogsQuery {
  page: number
  size: number
  taskName?: string
  status?: TaskRunStatus
  triggerType?: TriggerType
}

export function useTaskLogs(q: TaskLogsQuery) {
  return useQuery({
    queryKey: ['admin', 'tasks', 'list', q],
    queryFn: () => adminApi.listTaskLogs(q),
    refetchInterval: 5_000,
  })
}

export function useTaskLog(id: number) {
  return useQuery({
    queryKey: ['admin', 'tasks', 'detail', id],
    queryFn: () => adminApi.getTaskLog(id),
  })
}

export function useTriggerTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TaskTriggerRequest) => adminApi.triggerTask(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'tasks'] })
      qc.invalidateQueries({ queryKey: ['admin', 'dashboard'] })
    },
  })
}

export function useRetryTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runId: number) => adminApi.retryTask(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'tasks'] }),
  })
}

// ---------------- Audit

export interface AuditLogsQuery {
  page: number
  size: number
  userId?: number
  action?: AuditAction
  targetType?: TargetType
  targetId?: number
}

export function useAuditLogs(q: AuditLogsQuery) {
  return useQuery({
    queryKey: ['admin', 'audit', q],
    queryFn: () => adminApi.listAuditLogs(q),
  })
}

export function useAuditLog(id: number) {
  return useQuery({
    queryKey: ['admin', 'audit', 'detail', id],
    queryFn: () => adminApi.getAuditLog(id),
  })
}