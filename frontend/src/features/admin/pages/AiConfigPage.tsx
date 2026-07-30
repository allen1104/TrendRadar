import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { Alert } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { toast } from '@/components/ui/toast'
import { aiApi, type AIProviderItem, type ProviderKey, type DryRunResult } from '@/features/admin/api/ai'
import type { ApiError } from '@/lib/api/client'
import { cn } from '@/lib/utils'

type Tab = 'providers' | 'models' | 'prompts' | 'cost'

const TABS: { key: Tab; label: string }[] = [
  { key: 'providers', label: 'Provider' },
  { key: 'models', label: '模型' },
  { key: 'prompts', label: 'Prompt' },
  { key: 'cost', label: '成本' },
]

export function AiConfigPage() {
  const [tab, setTab] = useState<Tab>('providers')

  return (
    <div className="mx-auto max-w-6xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">AI 配置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理 LLM Provider、模型、Prompt 模板与成本监控
        </p>
      </header>

      <nav className="mb-6 flex gap-1 border-b border-border" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === t.key
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'providers' && <ProvidersTab />}
      {tab === 'models' && <ModelsTab />}
      {tab === 'prompts' && <PromptsTab />}
      {tab === 'cost' && <CostTab />}
    </div>
  )
}

// ============================================================= Providers

function ProvidersTab() {
  const queryClient = useQueryClient()
  const { data: providers, isLoading } = useQuery({
    queryKey: ['ai', 'providers'],
    queryFn: aiApi.listProviders,
  })
  const { data: plugins } = useQuery({
    queryKey: ['ai', 'plugins'],
    queryFn: aiApi.listRegisteredPlugins,
  })

  const deleteMut = useMutation({
    mutationFn: aiApi.deleteProvider,
    onSuccess: () => {
      toast.success('已删除')
      void queryClient.invalidateQueries({ queryKey: ['ai'] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  const testMut = useMutation({
    mutationFn: aiApi.testProvider,
    onSuccess: (result) => {
      if (result.success) toast.success(`连接正常 (${result.latencyMs}ms)`)
      else toast.error(result.message)
    },
  })

  return (
    <div className="space-y-4">
      <CreateProviderForm
        plugins={plugins ?? []}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ['ai', 'providers'] })}
      />

      {isLoading ? (
        <div className="h-32 animate-pulse rounded-xl bg-muted" />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {(providers ?? []).map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              testing={testMut.isPending}
              onTest={() => testMut.mutate(p.id)}
              onDelete={() => {
                if (window.confirm(`确定删除 Provider「${p.name}」？`)) {
                  deleteMut.mutate(p.id)
                }
              }}
            />
          ))}
          {providers?.length === 0 && (
            <Card>
              <CardContent className="p-12 text-center text-muted-foreground">
                还没有 Provider，点击上方"新建 Provider"开始
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function ProviderCard({
  provider,
  testing,
  onTest,
  onDelete,
}: {
  provider: AIProviderItem
  testing: boolean
  onTest: () => void
  onDelete: () => void
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base">{provider.name}</CardTitle>
            <Badge variant={provider.enabled ? 'success' : 'outline'}>
              {provider.enabled ? '启用' : '禁用'}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {provider.providerKey} · {provider.modelCount} 个模型
          </p>
        </div>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        {provider.baseUrl && (
          <p className="truncate text-muted-foreground" title={provider.baseUrl}>
            URL: <code className="text-xs">{provider.baseUrl}</code>
          </p>
        )}
        {provider.apiKey && (
          <p className="text-muted-foreground">Key: <code className="text-xs">{provider.apiKey}</code></p>
        )}
        <div className="flex gap-2 pt-2">
          <Button size="sm" variant="outline" loading={testing} onClick={onTest}>
            测试连接
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={provider.modelCount > 0}
            onClick={onDelete}
          >
            删除
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function CreateProviderForm({
  plugins,
  onCreated,
}: {
  plugins: { providerKey: string; displayName: string }[]
  onCreated: () => void
}) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    providerKey: 'openai_compatible' as ProviderKey,
    name: '',
    baseUrl: 'https://api.deepseek.com/v1',
    apiKey: '',
  })

  const create = useMutation({
    mutationFn: aiApi.createProvider,
    onSuccess: () => {
      toast.success('已创建')
      setOpen(false)
      setForm({ providerKey: 'openai_compatible', name: '', baseUrl: '', apiKey: '' })
      onCreated()
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  if (!open) return <Button onClick={() => setOpen(true)}>+ 新建 Provider</Button>

  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>插件类型</Label>
            <Select
              value={form.providerKey}
              onChange={(e) =>
                setForm((f) => ({ ...f, providerKey: e.target.value as ProviderKey }))
              }
            >
              {plugins.map((p) => (
                <option key={p.providerKey} value={p.providerKey}>
                  {p.displayName}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>名称</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="DeepSeek 官方"
            />
          </div>
        </div>
        {form.providerKey === 'openai_compatible' && (
          <>
            <div className="space-y-1.5">
              <Label>Base URL</Label>
              <Input
                value={form.baseUrl}
                onChange={(e) => setForm((f) => ({ ...f, baseUrl: e.target.value }))}
                placeholder="https://api.deepseek.com/v1"
              />
            </div>
            <div className="space-y-1.5">
              <Label>API Key</Label>
              <Input
                type="password"
                value={form.apiKey}
                onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))}
                placeholder="sk-..."
              />
            </div>
          </>
        )}
        <div className="flex gap-2">
          <Button
            loading={create.isPending}
            disabled={!form.name}
            onClick={() => create.mutate(form)}
          >
            创建
          </Button>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            取消
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================= Models

function ModelsTab() {
  const queryClient = useQueryClient()
  const { data: models, isLoading } = useQuery({
    queryKey: ['ai', 'models'],
    queryFn: aiApi.listModels,
  })
  const { data: providers } = useQuery({
    queryKey: ['ai', 'providers'],
    queryFn: aiApi.listProviders,
  })

  const del = useMutation({
    mutationFn: aiApi.deleteModel,
    onSuccess: () => {
      toast.success('已删除')
      void queryClient.invalidateQueries({ queryKey: ['ai'] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  return (
    <div className="space-y-4">
      <CreateModelForm
        providers={providers ?? []}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ['ai', 'models'] })}
      />
      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">别名</th>
                <th className="px-4 py-3 font-medium">模型名</th>
                <th className="px-4 py-3 font-medium">Provider</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">价格 ($/1M)</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td colSpan={7} className="px-4 py-3">
                      <div className="h-5 animate-pulse rounded bg-muted" />
                    </td>
                  </tr>
                ))}
              {models?.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">
                    还没有模型
                  </td>
                </tr>
              )}
              {models?.map((m) => (
                <tr key={m.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-mono text-xs">{m.alias}</td>
                  <td className="px-4 py-3">{m.modelName}</td>
                  <td className="px-4 py-3">{m.providerName}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">{m.modelType}</Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    ${m.priceInputPer1M} / ${m.priceOutputPer1M}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={m.enabled ? 'success' : 'outline'}>
                      {m.enabled ? '启用' : '禁用'}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="destructive" onClick={() => del.mutate(m.id)}>
                      删除
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

function CreateModelForm({
  providers,
  onCreated,
}: {
  providers: AIProviderItem[]
  onCreated: () => void
}) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    providerId: providers[0]?.id ?? 0,
    modelName: '',
    alias: '',
    modelType: 'CHAT' as 'CHAT' | 'EMBEDDING',
    contextWindow: 128000,
    maxOutputTokens: 4096,
    supportsJsonSchema: true,
    priceInputPer1M: 0,
    priceOutputPer1M: 0,
    embeddingDim: 1024 as number | null,
    enabled: true,
  })

  const create = useMutation({
    mutationFn: aiApi.createModel,
    onSuccess: () => {
      toast.success('已创建')
      setOpen(false)
      onCreated()
    },
    onError: (e) => toast.error((e as ApiError).message),
  })

  if (!open) return <Button onClick={() => setOpen(true)}>+ 新建模型</Button>

  return (
    <Card>
      <CardContent className="space-y-3 pt-6">
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label>Provider</Label>
            <Select
              value={form.providerId}
              onChange={(e) => setForm((f) => ({ ...f, providerId: Number(e.target.value) }))}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>模型名（API 真实名）</Label>
            <Input
              value={form.modelName}
              onChange={(e) => setForm((f) => ({ ...f, modelName: e.target.value }))}
              placeholder="deepseek-chat"
            />
          </div>
          <div className="space-y-1.5">
            <Label>别名（系统引用）</Label>
            <Input
              value={form.alias}
              onChange={(e) => setForm((f) => ({ ...f, alias: e.target.value }))}
              placeholder="default-chat"
            />
          </div>
        </div>
        <div className="grid grid-cols-4 gap-3">
          <div className="space-y-1.5">
            <Label>类型</Label>
            <Select
              value={form.modelType}
              onChange={(e) => setForm((f) => ({ ...f, modelType: e.target.value as 'CHAT' | 'EMBEDDING' }))}
            >
              <option value="CHAT">CHAT</option>
              <option value="EMBEDDING">EMBEDDING</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>上下文</Label>
            <Input
              type="number"
              value={form.contextWindow}
              onChange={(e) => setForm((f) => ({ ...f, contextWindow: Number(e.target.value) }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label>输入价格 $/1M</Label>
            <Input
              type="number"
              step="0.01"
              value={form.priceInputPer1M}
              onChange={(e) => setForm((f) => ({ ...f, priceInputPer1M: Number(e.target.value) }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label>输出价格 $/1M</Label>
            <Input
              type="number"
              step="0.01"
              value={form.priceOutputPer1M}
              onChange={(e) => setForm((f) => ({ ...f, priceOutputPer1M: Number(e.target.value) }))}
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            loading={create.isPending}
            disabled={!form.alias || !form.modelName}
            onClick={() => create.mutate(form)}
          >
            创建
          </Button>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            取消
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================= Prompts

function PromptsTab() {
  const { data: prompts } = useQuery({
    queryKey: ['ai', 'prompts'],
    queryFn: () => aiApi.listPrompts(),
  })
  const [selectedId, setSelectedId] = useState<number | null>(null)

  // 默认选最新一个
  const selected =
    prompts?.find((p) => p.id === selectedId) ?? prompts?.[0] ?? null

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px,1fr]">
      <PromptList
        prompts={prompts ?? []}
        selectedId={selected?.id ?? null}
        onSelect={setSelectedId}
      />
      {selected ? (
        <PromptDetail promptId={selected.id} />
      ) : (
        <Card>
          <CardContent className="p-12 text-center text-muted-foreground">
            选择左侧 Prompt 查看详情
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function PromptList({
  prompts,
  selectedId,
  onSelect,
}: {
  prompts: { id: number; taskKey: string; version: number; isActive: boolean; note: string | null; createdAt: string }[]
  selectedId: number | null
  onSelect: (id: number) => void
}) {
  const byTask = prompts.reduce<Record<string, typeof prompts>>((acc, p) => {
    (acc[p.taskKey] ??= []).push(p)
    return acc
  }, {})

  return (
    <Card>
      <CardContent className="p-2">
        {Object.entries(byTask).map(([task, ps]) => (
          <div key={task} className="mb-2">
            <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
              {task}
            </div>
            {ps.map((p) => (
              <button
                key={p.id}
                onClick={() => onSelect(p.id)}
                className={cn(
                  'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted',
                  selectedId === p.id && 'bg-muted font-medium',
                )}
              >
                <span className="flex items-center gap-1.5">
                  <span className="font-mono text-xs">v{p.version}</span>
                  {p.isActive && (
                    <Badge variant="success" className="px-1 py-0 text-[10px]">
                      active
                    </Badge>
                  )}
                </span>
                {p.note && <span className="truncate text-xs text-muted-foreground">{p.note}</span>}
              </button>
            ))}
          </div>
        ))}
        {prompts.length === 0 && (
          <div className="p-6 text-center text-sm text-muted-foreground">还没有 Prompt</div>
        )}
      </CardContent>
    </Card>
  )
}

function PromptDetail({ promptId }: { promptId: number }) {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['ai', 'prompt', promptId],
    queryFn: () => aiApi.getPrompt(promptId),
  })
  const [varsText, setVarsText] = useState('')
  const [dryResult, setDryResult] = useState<DryRunResult | null>(null)
  const [dryError, setDryError] = useState<string | null>(null)
  const [mode, setMode] = useState<'view' | 'edit' | 'new'>('view')

  const activate = useMutation({
    mutationFn: aiApi.activatePrompt,
    onSuccess: () => {
      toast.success('已激活')
      void queryClient.invalidateQueries({ queryKey: ['ai', 'prompts'] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })
  const update = useMutation({
    mutationFn: (payload: Parameters<typeof aiApi.updatePrompt>[1]) =>
      aiApi.updatePrompt(promptId, payload),
    onSuccess: () => {
      toast.success('已保存')
      setMode('view')
      void queryClient.invalidateQueries({ queryKey: ['ai', 'prompts'] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })
  const createNew = useMutation({
    mutationFn: aiApi.createPrompt,
    onSuccess: (newPrompt) => {
      toast.success(`已创建 v${newPrompt.version}`)
      setMode('view')
      // 切到新版本
      void queryClient.invalidateQueries({ queryKey: ['ai', 'prompts'] })
      void queryClient.invalidateQueries({ queryKey: ['ai', 'prompt', newPrompt.id] })
    },
    onError: (e) => toast.error((e as ApiError).message),
  })
  const dryRun = useMutation({
    mutationFn: () => {
      let variables: Record<string, unknown> = {}
      if (varsText.trim()) {
        try {
          variables = JSON.parse(varsText)
        } catch {
          throw new Error('变量 JSON 格式错误')
        }
      }
      return aiApi.dryRunPrompt(promptId, { variables })
    },
    onSuccess: (r) => {
      setDryResult(r)
      setDryError(null)
    },
    onError: (e) => {
      setDryError((e as Error).message)
      setDryResult(null)
    },
  })

  if (isLoading || !data) {
    return <div className="h-64 animate-pulse rounded-xl bg-muted" />
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-3">
        <div>
          <CardTitle className="text-base">
            {data.taskKey} <span className="text-muted-foreground">v{data.version}</span>
          </CardTitle>
          {data.note && <p className="mt-1 text-xs text-muted-foreground">{data.note}</p>}
        </div>
        <div className="flex gap-2">
          {data.isActive ? (
            <Badge variant="success">当前生效</Badge>
          ) : mode === 'view' ? (
            <Button size="sm" loading={activate.isPending} onClick={() => activate.mutate(data.id)}>
              激活此版本
            </Button>
          ) : null}
          {mode === 'view' && !data.isActive && (
            <Button size="sm" variant="outline" onClick={() => setMode('edit')}>
              编辑
            </Button>
          )}
          {mode === 'view' && (
            <Button size="sm" variant="outline" onClick={() => setMode('new')}>
              + 新建版本
            </Button>
          )}
          {mode !== 'view' && (
            <Button size="sm" variant="ghost" onClick={() => setMode('view')}>
              取消
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {mode === 'view' ? (
          <>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-muted-foreground">模型</div>
                <div className="font-mono text-xs">{data.modelAlias || '(default)'}</div>
              </div>
              <div>
                <div className="text-muted-foreground">温度</div>
                <div>{data.temperature}</div>
              </div>
              <div className="col-span-2">
                <div className="text-muted-foreground">变量</div>
                <div className="flex flex-wrap gap-1">
                  {data.variables.map((v) => (
                    <code key={v} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {v}
                    </code>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <Label>System Prompt</Label>
              <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                {data.systemPrompt}
              </pre>
            </div>
            <div>
              <Label>User Prompt</Label>
              <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                {data.userPrompt}
              </pre>
            </div>
          </>
        ) : (
          <PromptForm
            initial={{
              systemPrompt: data.systemPrompt,
              userPrompt: data.userPrompt,
              variables: data.variables,
              modelAlias: data.modelAlias,
              temperature: data.temperature,
              maxTokens: data.maxTokens,
              note: data.note,
            }}
            isNew={mode === 'new'}
            taskKey={data.taskKey}
            saving={update.isPending || createNew.isPending}
            onSubmit={(values) => {
              if (mode === 'edit') {
                // 只送用户改过的字段
                const dirty: Parameters<typeof aiApi.updatePrompt>[1] = {}
                if (values.systemPrompt !== data.systemPrompt) dirty.systemPrompt = values.systemPrompt
                if (values.userPrompt !== data.userPrompt) dirty.userPrompt = values.userPrompt
                if (JSON.stringify(values.variables) !== JSON.stringify(data.variables)) {
                  dirty.variables = values.variables
                }
                if ((values.modelAlias ?? null) !== data.modelAlias) dirty.modelAlias = values.modelAlias ?? ''
                if (values.temperature !== data.temperature) dirty.temperature = values.temperature
                if ((values.maxTokens ?? null) !== data.maxTokens)
                  dirty.maxTokens = values.maxTokens ?? undefined
                if ((values.note ?? null) !== data.note) dirty.note = values.note ?? ''
                if (Object.keys(dirty).length === 0) {
                  toast.info('没有改动')
                  setMode('view')
                  return
                }
                update.mutate(dirty)
              } else {
                // 新建版本：基于当前填的值 + 当前 taskKey
                createNew.mutate({
                  taskKey: data.taskKey,
                  systemPrompt: values.systemPrompt,
                  userPrompt: values.userPrompt,
                  variables: values.variables,
                  modelAlias: values.modelAlias || undefined,
                  temperature: values.temperature,
                  maxTokens: values.maxTokens ?? undefined,
                  note: values.note || undefined,
                })
              }
            }}
          />
        )}

        <div className="border-t border-border pt-4">
          <Label>试运行（传入变量 JSON）</Label>
          <textarea
            value={varsText}
            onChange={(e) => setVarsText(e.target.value)}
            placeholder='{"eventTitle": "测试", "articles": []}'
            className="mt-1 w-full rounded-md border border-border bg-transparent p-2 font-mono text-xs"
            rows={4}
          />
          <div className="mt-2 flex gap-2">
            <Button size="sm" loading={dryRun.isPending} onClick={() => dryRun.mutate()}>
              运行
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setVarsText('')
                setDryResult(null)
                setDryError(null)
              }}
            >
              清空
            </Button>
          </div>
          {dryError && <Alert variant="error" className="mt-2">{dryError}</Alert>}
          {dryResult && (
            <div className="mt-3 space-y-2 text-xs">
              <div>
                <div className="font-medium">输出</div>
                <pre className="max-h-32 overflow-auto rounded bg-muted p-2">
                  {JSON.stringify(dryResult, null, 2)}
                </pre>
              </div>
              <div className="text-muted-foreground">
                {dryResult.promptTokens} → {dryResult.completionTokens} tokens ·{' '}
                {dryResult.latencyMs}ms · parseSuccess={String(dryResult.parseSuccess)}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================= Cost

function CostTab() {
  const [start, setStart] = useState(
    new Date(Date.now() - 7 * 86400_000).toISOString().slice(0, 10),
  )
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10))

  const { data, isLoading, error } = useQuery({
    queryKey: ['ai', 'cost', start, end],
    queryFn: () => aiApi.getCost({ start_date: `${start}T00:00:00`, end_date: `${end}T00:00:00` }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="space-y-1.5">
          <Label>起始日期</Label>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>结束日期</Label>
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>

      {error && <Alert variant="error">{(error as ApiError).message}</Alert>}

      {isLoading ? (
        <div className="h-32 animate-pulse rounded-xl bg-muted" />
      ) : data ? (
        <>
          <div className="grid grid-cols-4 gap-4">
            <Stat label="总费用" value={`$${data.totalCostUsd.toFixed(4)}`} />
            <Stat label="总调用" value={data.totalCalls.toString()} />
            <Stat
              label="总 Token"
              value={(data.totalPromptTokens + data.totalCompletionTokens).toLocaleString()}
            />
            <Stat label="成功率" value={`${(data.successRate * 100).toFixed(1)}%`} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">按模型</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-border text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">模型</th>
                    <th className="px-4 py-2 font-medium">费用</th>
                    <th className="px-4 py-2 font-medium">调用数</th>
                    <th className="px-4 py-2 font-medium">Token</th>
                  </tr>
                </thead>
                <tbody>
                  {data.byModel.map((row) => (
                    <tr key={row.key} className="border-b border-border last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">{row.key}</td>
                      <td className="px-4 py-2">${row.costUsd.toFixed(4)}</td>
                      <td className="px-4 py-2">{row.calls}</td>
                      <td className="px-4 py-2">
                        {(row.promptTokens + row.completionTokens).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                  {data.byModel.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-6 text-center text-muted-foreground">
                        该时间段无调用记录
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">按任务</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-border text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">任务</th>
                    <th className="px-4 py-2 font-medium">费用</th>
                    <th className="px-4 py-2 font-medium">调用数</th>
                  </tr>
                </thead>
                <tbody>
                  {data.byTask.map((row) => (
                    <tr key={row.key} className="border-b border-border last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">{row.key}</td>
                      <td className="px-4 py-2">${row.costUsd.toFixed(4)}</td>
                      <td className="px-4 py-2">{row.calls}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  )
}

function PromptForm({
  initial,
  isNew,
  taskKey,
  saving,
  onSubmit,
}: {
  initial: {
    systemPrompt: string
    userPrompt: string
    variables: string[]
    modelAlias: string | null
    temperature: number
    maxTokens: number | null
    note: string | null
  }
  isNew: boolean
  taskKey: string
  saving: boolean
  onSubmit: (values: {
    systemPrompt: string
    userPrompt: string
    variables: string[]
    modelAlias: string | null
    temperature: number
    maxTokens: number | null
    note: string | null
  }) => void
}) {
  const [systemPrompt, setSystemPrompt] = useState(initial.systemPrompt)
  const [userPrompt, setUserPrompt] = useState(initial.userPrompt)
  const [varsText, setVarsText] = useState(initial.variables.join(', '))
  const [modelAlias, setModelAlias] = useState(initial.modelAlias ?? '')
  const [temperature, setTemperature] = useState(initial.temperature)
  const [maxTokens, setMaxTokens] = useState(initial.maxTokens?.toString() ?? '')
  const [note, setNote] = useState(initial.note ?? '')

  // 切换 isNew 时重置
  useEffect(() => {
    setSystemPrompt(initial.systemPrompt)
    setUserPrompt(initial.userPrompt)
    setVarsText(initial.variables.join(', '))
    setModelAlias(initial.modelAlias ?? '')
    setTemperature(initial.temperature)
    setMaxTokens(initial.maxTokens?.toString() ?? '')
    setNote(initial.note ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew])

  const parsedVars = varsText
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({
          systemPrompt,
          userPrompt,
          variables: parsedVars,
          modelAlias: modelAlias.trim() || null,
          temperature,
          maxTokens: maxTokens ? Number(maxTokens) : null,
          note: note.trim() || null,
        })
      }}
      className="space-y-4"
    >
      <Alert variant="info">
        {isNew
          ? `创建新版本（taskKey = ${taskKey}，version 自动 +1，默认非激活）`
          : '修改当前版本。已激活的版本不可编辑。'}
      </Alert>

      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="modelAlias">模型别名</Label>
          <Input
            id="modelAlias"
            value={modelAlias}
            onChange={(e) => setModelAlias(e.target.value)}
            placeholder="default-chat"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="temp">温度</Label>
          <Input
            id="temp"
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="maxTokens">最大输出 tokens</Label>
          <Input
            id="maxTokens"
            type="number"
            value={maxTokens}
            onChange={(e) => setMaxTokens(e.target.value)}
            placeholder="留空 = 不限"
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="vars">变量（英文逗号分隔）</Label>
        <Input id="vars" value={varsText} onChange={(e) => setVarsText(e.target.value)} />
        {parsedVars.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {parsedVars.map((v) => (
              <code key={v} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                {v}
              </code>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="system">System Prompt</Label>
        <textarea
          id="system"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={5}
          required
          className="w-full rounded-md border border-border bg-transparent p-2 font-mono text-xs"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="user">User Prompt</Label>
        <textarea
          id="user"
          value={userPrompt}
          onChange={(e) => setUserPrompt(e.target.value)}
          rows={10}
          required
          className="w-full rounded-md border border-border bg-transparent p-2 font-mono text-xs"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="note">备注</Label>
        <Input id="note" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>

      <div className="flex justify-end gap-2">
        <Button type="submit" loading={saving} disabled={!systemPrompt || !userPrompt}>
          {isNew ? '创建新版本' : '保存修改'}
        </Button>
      </div>
    </form>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  )
}
