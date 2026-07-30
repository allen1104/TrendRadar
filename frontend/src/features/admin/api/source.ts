import { http, type Page } from '@/lib/api/client'

export type Region = 'GLOBAL' | 'CN'
export type SourceCategory = 'NEWS' | 'CODE' | 'PAPER' | 'PRODUCT' | 'BLOG' | 'MODEL'
export type RunStatus = 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED'

export interface SourceItem {
  id: number
  pluginKey: string
  name: string
  region: Region
  category: SourceCategory
  cron: string
  weight: number
  enabled: boolean
  lastRunAt: string | null
  lastRunStatus: RunStatus | null
  consecutiveFails: number
  todayCount: number
  createdAt: string
}

export interface SourceDetail extends Omit<SourceItem, 'todayCount'> {
  homeUrl: string | null
  config: Record<string, unknown>
  nextRunPreview: string | null
  updatedAt: string
}

export interface RegisteredPlugin {
  pluginKey: string
  displayName: string
  region: Region
  category: SourceCategory
  defaultCron: string
  defaultWeight: number
  configSchema: Record<string, unknown>
  implemented: boolean
}

export interface SourceTestResult {
  success: boolean
  fetchedCount: number
  durationMs: number
  preview: Array<{
    externalId: string
    title: string
    url: string
    author: string | null
    publishedAt: string | null
    lang: string
    metrics: Record<string, number>
  }>
  errorMessage: string | null
}

export interface RunLog {
  id: number
  sourceId: number
  taskId: string | null
  triggerType: 'SCHEDULED' | 'MANUAL'
  status: RunStatus
  fetchedCount: number
  newCount: number
  durationMs: number | null
  errorMessage: string | null
  startedAt: string
  finishedAt: string | null
  createdAt: string
}

export const sourceApi = {
  listPlugins: (): Promise<RegisteredPlugin[]> =>
    http.get<RegisteredPlugin[]>('/admin/sources/plugins').then(r => r.data),
  list: (params?: {
    page?: number
    size?: number
    region?: Region
    category?: SourceCategory
    enabled_only?: boolean
    keyword?: string
  }): Promise<Page<SourceItem>> =>
    http.get<Page<SourceItem>>('/admin/sources', { params }).then(r => r.data),
  get: (id: number): Promise<SourceDetail> =>
    http.get<SourceDetail>(`/admin/sources/${id}`).then(r => r.data),
  create: (payload: {
    pluginKey: string
    name: string
    region: Region
    category: SourceCategory
    homeUrl?: string
    config?: Record<string, unknown>
    cron: string
    weight: number
    enabled?: boolean
  }): Promise<SourceDetail> =>
    http.post<SourceDetail>('/admin/sources', payload).then(r => r.data),
  update: (id: number, payload: Partial<{
    name: string
    region: Region
    category: SourceCategory
    homeUrl: string
    config: Record<string, unknown>
    cron: string
    weight: number
    enabled: boolean
  }>): Promise<SourceDetail> =>
    http.patch<SourceDetail>(`/admin/sources/${id}`, payload).then(r => r.data),
  delete: (id: number): Promise<void> =>
    http.delete<void>(`/admin/sources/${id}`).then(() => undefined),
  test: (id: number): Promise<SourceTestResult> =>
    http.post<SourceTestResult>(`/admin/sources/${id}/test`).then(r => r.data),
  runNow: (id: number): Promise<{ taskId: string | null; runLogId: number | null; status: string }> =>
    http.post(`/admin/sources/${id}/run`).then(r => r.data),
  listLogs: (id: number, params?: { page?: number; size?: number; status?: RunStatus }): Promise<Page<RunLog>> =>
    http.get<Page<RunLog>>(`/admin/sources/${id}/logs`, { params }).then(r => r.data),
}
