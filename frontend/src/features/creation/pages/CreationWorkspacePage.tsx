import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import {
  consumeSSE,
  downloadExport,
  type CreateDraftBody,
  type DraftDetail,
  type ExportFormat,
  type OutlineItem,
  type RegenerateBody,
} from '@/features/creation/api/creation'
import { DraftEditor } from '@/features/creation/components/DraftEditor'
import {
  useCreationDraft,
  useInvalidateAfterStream,
  useUpdateDraft,
} from '@/features/creation/hooks/useCreation'

/** 创作工作台：流式生成 + 编辑 + 导出。 */
export function CreationWorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const draftId = id ? Number(id) : null
  const navigate = useNavigate()
  const { data: fetched, isLoading } = useCreationDraft(draftId)
  const updateDraft = useUpdateDraft()
  const invalidate = useInvalidateAfterStream()

  // 流式状态
  const [streamingDraft, setStreamingDraft] = useState<DraftDetail | null>(null)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingOutline, setStreamingOutline] = useState<OutlineItem[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // UI 状态
  const [view, setView] = useState<'edit' | 'preview' | 'wechat'>('preview')

  // 合并当前 draft（流式优先）
  const draft = streamingDraft ?? fetched ?? null

  // 进入页面若 DONE 但 outline 为空（流式生成历史数据），不重复生成
  useEffect(() => {
    return () => {
      // 离开页面：若仍在流式，中断
      abortRef.current?.abort()
    }
  }, [])

  // 直接消费 SSE；创建走 EventDetailPage 的 GenerationDialog，本页主要处理 regenerate。
  // startGenerate 留作扩展备用（如直接在该页新建草稿时使用）。
  // @ts-expect-error -- 保留函数签名供未来 inline 调用
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _startGenerateReserved = (body: CreateDraftBody): void => {
    setStreamError(null)
    setIsStreaming(true)
    setStreamingContent('')
    setStreamingOutline([])
    setStreamingDraft(null)
    abortRef.current = consumeSSE('/api/v1/creation/drafts', body, {
      onStart: (data) => {
        if (!draftId) navigate(`/creation/drafts/${data.draftId}`)
        setStreamingDraft({
          id: data.draftId,
          userId: 0,
          eventId: body.eventId,
          platform: body.platform,
          style: body.style,
          title: '',
          content: '',
          contentEdited: null,
          outline: [],
          coverSuggestion: null,
          tagsSuggestion: [],
          wordCount: 0,
          extraParams: {},
          modelAlias: data.modelAlias,
          promptVersion: null,
          costUsd: 0,
          status: 'GENERATING',
          errorMessage: null,
          regenerateCount: 0,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        })
      },
      onOutline: (data) => setStreamingOutline(data.outline),
      onDelta: (data) => setStreamingContent((c) => c + data.content),
      onDone: () => {
        setIsStreaming(false)
        invalidate(draftId ?? undefined)
      },
      onError: (data) => {
        setStreamError(`${data.errorCode}: ${data.detail}`)
        setIsStreaming(false)
        invalidate(draftId ?? undefined)
      },
    })
  }

  const handleRegenerate = (payload: RegenerateBody = {}) => {
    if (!draftId) return
    setStreamError(null)
    setIsStreaming(true)
    setStreamingContent('')
    setStreamingOutline([])
    abortRef.current = consumeSSE(
      `/api/v1/creation/drafts/${draftId}/regenerate`,
      payload,
      {
        onStart: () => {},
        onOutline: (data) => setStreamingOutline(data.outline),
        onDelta: (data) => setStreamingContent((c) => c + data.content),
        onDone: () => {
          setIsStreaming(false)
          invalidate(draftId)
        },
        onError: (data) => {
          setStreamError(`${data.errorCode}: ${data.detail}`)
          setIsStreaming(false)
          invalidate(draftId)
        },
      },
    )
  }

  const stopStreaming = () => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }

  if (isLoading && !draft) {
    return (
      <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
        加载中…
      </div>
    )
  }

  if (!draft) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-3 text-muted-foreground">
        <p>草稿不存在或已被删除</p>
        <Link to="/creation/drafts">
          <Button>返回列表</Button>
        </Link>
      </div>
    )
  }

  const regenerateRemaining = Math.max(0, 5 - draft.regenerateCount)
  const platformSupportsWechat = true // 所有平台都能预览（即使最终发布需要适配）

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* 顶部：返回 + 错误 */}
      <div className="flex items-center justify-between border-b px-6 py-2 text-sm">
        <Link to="/creation/drafts">
          <Button variant="ghost" size="sm">
            ← 返回草稿列表
          </Button>
        </Link>
        <div className="flex items-center gap-2">
          {streamError && <span className="text-xs text-destructive">{streamError}</span>}
          {isStreaming ? (
            <Button size="sm" variant="destructive" onClick={stopStreaming}>
              ■ 停止
            </Button>
          ) : draft.status === 'FAILED' ? (
            <Button
              size="sm"
              onClick={() => handleRegenerate()}
              disabled={regenerateRemaining <= 0}
            >
              ⟳ 重试
            </Button>
          ) : null}
        </div>
      </div>

      <DraftEditor
        draft={draft}
        outline={streamingOutline.length > 0 ? streamingOutline : draft.outline}
        streamingContent={streamingContent}
        isStreaming={isStreaming}
        view={view}
        onViewChange={setView}
        onTitleEdit={(title) => updateDraft.mutate({ draftId: draft.id, title })}
        onContentEdit={(content) => updateDraft.mutate({ draftId: draft.id, contentEdited: content })}
        onRegenerate={() => handleRegenerate()}
        onExport={(fmt: ExportFormat) => void downloadExport(draft.id, fmt)}
        onCopy={() => {
          const txt = draft.contentEdited ?? draft.content
          void navigator.clipboard.writeText(txt)
        }}
        regenerateRemaining={regenerateRemaining}
        platformSupportsWechat={platformSupportsWechat}
      />

      {/* 没 draftId 时（即路由是 /creation/drafts 但 draft 未建）：隐藏 editor */}
      {!draftId && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80">
          <Button onClick={() => navigate(-1)}>返回</Button>
        </div>
      )}
    </div>
  )
}