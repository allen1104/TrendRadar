import { http, type Page } from '@/lib/api/client'

export type ModelType = 'CHAT' | 'EMBEDDING'

export interface AIProviderItem {
  id: number
  providerKey: ProviderKey
  name: string
  baseUrl: string | null
  apiKey: string | null
  extraConfig: Record<string, unknown>
  enabled: boolean
  modelCount: number
  createdAt: string
  updatedAt: string
}

export interface RegisteredPlugin {
  providerKey: string
  displayName: string
  region: string
  configSchema: Record<string, unknown>
}

export interface AIModelItem {
  id: number
  providerId: number
  providerName: string
  modelName: string
  alias: string
  modelType: ModelType
  contextWindow: number
  maxOutputTokens: number
  supportsJsonSchema: boolean
  priceInputPer1M: number
  priceOutputPer1M: number
  embeddingDim: number | null
  enabled: boolean
  createdAt: string
  updatedAt: string
}

export type ProviderKey = 'openai_compatible' | 'anthropic' | 'gemini' | 'local_embedding'

export interface AIPromptItem {
  id: number
  taskKey: string
  version: number
  modelAlias: string | null
  temperature: number
  isActive: boolean
  note: string | null
  variables: string[]
  createdAt: string
  updatedAt: string
}

export interface AIPromptDetail extends AIPromptItem {
  systemPrompt: string
  userPrompt: string
  maxTokens: number | null
  createdBy: number | null
}

export interface CostStats {
  totalCostUsd: number
  totalCalls: number
  totalPromptTokens: number
  totalCompletionTokens: number
  successRate: number
  series: { key: string; costUsd: number; calls: number; promptTokens: number; completionTokens: number }[]
  byModel: { key: string; costUsd: number; calls: number; promptTokens: number; completionTokens: number }[]
  byTask: { key: string; costUsd: number; calls: number; promptTokens: number; completionTokens: number }[]
}

export interface CallLogItem {
  id: number
  traceId: string
  taskKey: string
  modelAlias: string
  promptVersion: number | null
  targetType: string | null
  targetId: number | null
  userId: number | null
  promptTokens: number
  completionTokens: number
  costUsd: number
  latencyMs: number | null
  status: 'SUCCESS' | 'FAILED' | 'FALLBACK'
  retryCount: number
  errorMessage: string | null
  createdAt: string
}

export const aiApi = {
  listProviders: (): Promise<AIProviderItem[]> =>
    http.get<AIProviderItem[]>('/admin/ai/providers').then(r => r.data),
  listRegisteredPlugins: (): Promise<RegisteredPlugin[]> =>
    http.get<RegisteredPlugin[]>('/admin/ai/plugins').then(r => r.data),
  createProvider: (data: ProviderCreatePayload): Promise<AIProviderItem> =>
    http.post<AIProviderItem>('/admin/ai/providers', data).then(r => r.data),
  updateProvider: (id: number, data: ProviderCreatePayload): Promise<AIProviderItem> =>
    http.patch<AIProviderItem>(`/admin/ai/providers/${id}`, data).then(r => r.data),
  deleteProvider: (id: number): Promise<void> =>
    http.delete<void>(`/admin/ai/providers/${id}`).then(() => undefined),
  testProvider: (id: number): Promise<ProviderTestResult> =>
    http.post<ProviderTestResult>(`/admin/ai/providers/${id}/test`).then(r => r.data),

  listModels: (): Promise<AIModelItem[]> =>
    http.get<AIModelItem[]>('/admin/ai/models').then(r => r.data),
  createModel: (data: ModelCreatePayload): Promise<AIModelItem> =>
    http.post<AIModelItem>('/admin/ai/models', data).then(r => r.data),
  deleteModel: (id: number): Promise<void> =>
    http.delete<void>(`/admin/ai/models/${id}`).then(() => undefined),

  listPrompts: (params?: { taskKey?: string; onlyActive?: boolean }): Promise<AIPromptItem[]> =>
    http.get<AIPromptItem[]>('/admin/ai/prompts', { params }).then(r => r.data),
  getPrompt: (id: number): Promise<AIPromptDetail> =>
    http.get<AIPromptDetail>(`/admin/ai/prompts/${id}`).then(r => r.data),
  createPrompt: (data: PromptCreatePayload): Promise<AIPromptDetail> =>
    http.post<AIPromptDetail>('/admin/ai/prompts', data).then(r => r.data),
  updatePrompt: (
    id: number,
    data: Partial<Omit<PromptCreatePayload, 'taskKey'>>,
  ): Promise<AIPromptDetail> =>
    http.patch<AIPromptDetail>(`/admin/ai/prompts/${id}`, data).then(r => r.data),
  activatePrompt: (id: number): Promise<AIPromptDetail> =>
    http.post<AIPromptDetail>(`/admin/ai/prompts/${id}/activate`).then(r => r.data),
  dryRunPrompt: (
    id: number,
    data: { variables?: Record<string, unknown>; targetType?: string; targetId?: number },
  ): Promise<DryRunResult> =>
    http.post<DryRunResult>(`/admin/ai/prompts/${id}/dry-run`, data).then(r => r.data),

  getCost: (params: { start_date: string; end_date: string; group_by?: 'DAY' | 'WEEK' | 'MONTH' }): Promise<CostStats> =>
    http.get<CostStats>('/admin/ai/cost', { params }).then(r => r.data),

  listLogs: (params: {
    page?: number
    size?: number
    taskKey?: string
    modelAlias?: string
    status?: string
  }): Promise<Page<CallLogItem>> =>
    http.get<Page<CallLogItem>>('/admin/ai/logs', { params }).then(r => r.data),
}

export interface ProviderCreatePayload {
  providerKey: ProviderKey
  name: string
  baseUrl?: string
  apiKey?: string
  extraConfig?: Record<string, unknown>
  enabled?: boolean
}

export interface ProviderTestResult {
  success: boolean
  latencyMs: number | null
  message: string
  availableModels: string[]
}

export interface ModelCreatePayload {
  providerId: number
  modelName: string
  alias: string
  modelType: 'CHAT' | 'EMBEDDING'
  contextWindow: number
  maxOutputTokens: number
  supportsJsonSchema: boolean
  priceInputPer1M: number
  priceOutputPer1M: number
  embeddingDim: number | null
  enabled: boolean
}

export interface PromptCreatePayload {
  taskKey: string
  systemPrompt: string
  userPrompt: string
  variables?: string[]
  modelAlias?: string
  temperature?: number
  maxTokens?: number
  note?: string
}

export interface DryRunResult {
  renderedSystemPrompt: string
  renderedUserPrompt: string
  output: unknown
  modelAlias: string
  promptTokens: number
  completionTokens: number
  costUsd: number
  latencyMs: number
  parseSuccess: boolean
}
