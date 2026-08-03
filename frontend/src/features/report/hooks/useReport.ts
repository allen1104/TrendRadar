import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import { reportApi, type ExportFormat, type ReportType } from '../api/reports'

// ---------- 列表 / 详情 / 最新 ----------

export function useReportsList(params?: {
  reportType?: ReportType
  status?: string
  page?: number
  size?: number
}) {
  return useQuery({
    queryKey: ['reports', 'list', params],
    queryFn: () => reportApi.list(params),
  })
}

export function useReportLatest() {
  return useQuery({
    queryKey: ['reports', 'latest'],
    queryFn: () => reportApi.latest(),
  })
}

export function useReportDetail(id: number) {
  return useQuery({
    queryKey: ['reports', 'detail', id],
    queryFn: () => reportApi.detail(id),
    enabled: id > 0,
  })
}

// ---------- 订阅 ----------

export function useSubscription() {
  return useQuery({
    queryKey: ['reports', 'subscription'],
    queryFn: () => reportApi.getSubscription(),
  })
}

export function usePutSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Parameters<typeof reportApi.putSubscription>[0]) =>
      reportApi.putSubscription(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'subscription'] })
    },
  })
}

export function useResetRssToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => reportApi.resetRssToken(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'subscription'] })
    },
  })
}

// ---------- 管理操作 ----------

export function useAdminGenerate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: reportApi.generate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports'] })
    },
  })
}

export function useAdminUpdateReport(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Parameters<typeof reportApi.update>[1]) =>
      reportApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'detail', id] })
      qc.invalidateQueries({ queryKey: ['reports', 'list'] })
    },
  })
}

export function useAdminPublish(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => reportApi.publish(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'detail', id] })
      qc.invalidateQueries({ queryKey: ['reports', 'list'] })
    },
  })
}

export function useAdminUnpublish(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => reportApi.unpublish(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'detail', id] })
      qc.invalidateQueries({ queryKey: ['reports', 'list'] })
    },
  })
}

export function useAdminUpdateItem(reportId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      itemId,
      payload,
    }: {
      itemId: number
      payload: Parameters<typeof reportApi.updateItem>[2]
    }) => reportApi.updateItem(reportId, itemId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'detail', reportId] })
    },
  })
}

export function useAdminDeleteItem(reportId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (itemId: number) => reportApi.deleteItem(reportId, itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'detail', reportId] })
    },
  })
}

export function useAdminAddItem(reportId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: reportApi.addItem.bind(null, reportId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports', 'detail', reportId] })
    },
  })
}

// ---------- 导出 ----------

export async function downloadReportExport(
  id: number,
  format: ExportFormat,
): Promise<void> {
  const blob = await reportApi.export(id, format)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `report-${id}.${format.toLowerCase()}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}