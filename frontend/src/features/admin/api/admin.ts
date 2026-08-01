import { http, type Page } from '@/lib/api/client'

// ---------------- 通用枚举

export type ConfigGroup = 'DEDUPE' | 'RANK' | 'AI' | 'SCHEDULE' | 'SEARCH' | 'GENERAL'
export type ValueType = 'INT' | 'FLOAT' | 'BOOL' | 'STRING' | 'JSON'
export type TaskRunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'SUCCESS'
  | 'FAILED'
  | 'RETRYING'
  | 'SKIPPED'
export type TriggerType = 'SCHEDULED' | 'MANUAL' | 'CHAINED'
export type AlertLevel = 'INFO' | 'WARN' | 'ERROR'

// ---------------- Dashboard

export interface OverviewCard {
  totalEvents: number
  totalArticles: number
  todayNewEvents: number
  todayNewArticles: number
  activeSources: number
  totalUsers: number
}

export interface PipelineHealth {
  articleByStatus: Record<string, number>
  eventByStatus: Record<string, number>
  todayFailedArticles: number
  pendingClean: number
  pendingEmbed: number
  pendingAi: number
  avgSourcePerEvent: number
  dedupeRate: number
}

export interface AiCostCard {
  todayUsd: number
  monthUsd: number
  dailyLimitUsd: number
  limitReached: boolean
}

export interface SourceStatusItem {
  id: number
  name: string
  enabled: boolean
  lastRunStatus: string | null
  lastRunAt: string | null
  todayCount: number
  consecutiveFails: number
}

export interface AlertItem {
  id: number
  level: AlertLevel
  message: string
  createdAt: string
}

export interface TrendPoint {
  date: string
  articles: number
  events: number
  aiCostUsd: number
}

export interface DashboardResponse {
  overview: OverviewCard
  pipelineHealth: PipelineHealth
  aiCost: AiCostCard
  sourceStatus: SourceStatusItem[]
  recentAlerts: AlertItem[]
  trend7d: TrendPoint[]
}

// ---------------- Configs

export interface ConfigItem {
  id: number
  configKey: string
  configValue: unknown
  valueType: ValueType
  groupName: ConfigGroup
  displayName: string
  description: string | null
  minValue: number | null
  maxValue: number | null
  isEditable: boolean
  requiresRerun: boolean
  updatedAt: string
}

// ---------------- Tasks

export interface TaskDefinitionItem {
  taskName: string
  displayName: string
  cron: string | null
  enabled: boolean
  nextRunAt: string | null
  lastRunAt: string | null
  lastRunStatus: TaskRunStatus | null
  manualTriggerable: boolean
  isRunning: boolean
}

export interface TaskRunLogItem {
  id: number
  taskName: string
  taskId: string | null
  triggerType: TriggerType
  triggeredBy: number | null
  status: TaskRunStatus
  durationMs: number | null
  retryCount: number
  errorMessage: string | null
  startedAt: string | null
  finishedAt: string | null
  createdAt: string
}

export interface TaskRunLogDetail extends TaskRunLogItem {
  argsSummary: Record<string, unknown>
  resultSummary: Record<string, unknown> | null
  traceback: string | null
}

export interface TaskTriggerRequest {
  taskName: string
  args?: unknown[]
  kwargs?: Record<string, unknown>
}

export interface TaskTriggerResponse {
  taskId: string
  runLogId: number
}

// ---------------- Audit

export type AuditAction =
  | 'EVENT_PIN'
  | 'EVENT_HIDE'
  | 'EVENT_EDIT'
  | 'EVENT_SPLIT'
  | 'EVENT_MERGE'
  | 'EVENT_REANALYZE'
  | 'SOURCE_CREATE'
  | 'SOURCE_UPDATE'
  | 'SOURCE_DELETE'
  | 'SOURCE_MANUAL_RUN'
  | 'SOURCE_AUTO_DISABLED'
  | 'PROVIDER_CREATE'
  | 'PROVIDER_UPDATE'
  | 'PROVIDER_DELETE'
  | 'MODEL_CREATE'
  | 'MODEL_UPDATE'
  | 'MODEL_DELETE'
  | 'PROMPT_CREATE'
  | 'PROMPT_ACTIVATE'
  | 'USER_ROLE_CHANGE'
  | 'USER_STATUS_CHANGE'
  | 'CONFIG_UPDATE'
  | 'SYSTEM_ALERT'
  | 'AI_DAILY_LIMIT_REACHED'
  | 'SYSTEM_TASK_PAUSED'

export type TargetType =
  | 'EVENT'
  | 'SOURCE'
  | 'USER'
  | 'PROMPT'
  | 'MODEL'
  | 'PROVIDER'
  | 'CONFIG'
  | 'SYSTEM'

export interface AuditLogItem {
  id: number
  userId: number | null
  username: string | null
  action: AuditAction
  targetType: TargetType
  targetId: number | null
  ip: string | null
  traceId: string | null
  note: string | null
  createdAt: string
}

export interface AuditLogDetail extends AuditLogItem {
  beforeValue: Record<string, unknown> | null
  afterValue: Record<string, unknown> | null
  userAgent: string | null
}

// ---------------- API

export const adminApi = {
  // dashboard
  getDashboard: () => http.get<DashboardResponse>('/admin/dashboard').then((r) => r.data),

  // configs
  listConfigs: (group?: ConfigGroup) =>
    http
      .get<ConfigItem[]>('/admin/configs', { params: group ? { group } : {} })
      .then((r) => r.data),
  updateConfig: (configKey: string, configValue: unknown) =>
    http
      .put<ConfigItem>(`/admin/configs/${configKey}`, { configValue })
      .then((r) => r.data),

  // tasks
  listTaskDefinitions: () =>
    http.get<TaskDefinitionItem[]>('/admin/tasks/definitions').then((r) => r.data),
  listTaskLogs: (params: {
    page: number
    size: number
    taskName?: string
    status?: TaskRunStatus
    triggerType?: TriggerType
  }) => http.get<Page<TaskRunLogItem>>('/admin/tasks', { params }).then((r) => r.data),
  getTaskLog: (id: number) =>
    http.get<TaskRunLogDetail>(`/admin/tasks/${id}`).then((r) => r.data),
  triggerTask: (body: TaskTriggerRequest) =>
    http.post<TaskTriggerResponse>('/admin/tasks/trigger', body).then((r) => r.data),
  retryTask: (runId: number) =>
    http
      .post<TaskTriggerResponse>(`/admin/tasks/${runId}/retry`)
      .then((r) => r.data),

  // audit
  listAuditLogs: (params: {
    page: number
    size: number
    userId?: number
    action?: AuditAction
    targetType?: TargetType
    targetId?: number
  }) =>
    http.get<Page<AuditLogItem>>('/admin/audit-logs', { params }).then((r) => r.data),
  getAuditLog: (id: number) =>
    http.get<AuditLogDetail>(`/admin/audit-logs/${id}`).then((r) => r.data),
}