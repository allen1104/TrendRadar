import {
  Bookmark,
  CalendarRange,
  FileText,
  Folder,
  FolderPlus,
  Hash,
  Loader2,
  Plus,
  Search,
  Tag,
  Trash2,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toast'
import { ApiError } from '@/lib/api/client'
import {
  useBatchItems,
  useCreateFolder,
  useDeleteFolder,
  useDeleteItem,
  useFolders,
  useItems,
  useStats,
  useUpdateFolder,
  useUpdateItem,
} from '@/features/collection/hooks/useCollection'
import type {
  BatchPayload,
  CollectionFolder,
  CollectionItem,
  ReadStatus,
} from '@/features/collection/api/collection'
import { CollectionStarButton } from '@/features/collection/components/CollectionStarButton'
import { cn } from '@/lib/utils'

const READ_LABELS: Record<ReadStatus, string> = {
  UNREAD: '未读',
  LATER: '稍后读',
  READ: '已读',
}

// ============================================================ 子组件

function FolderSidebar({
  folders,
  activeFolderId,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: {
  folders: CollectionFolder[]
  activeFolderId: number | 'ALL' | 'UNREAD' | 'LATER' | 'READ' | null
  onSelect: (id: number | 'ALL' | 'UNREAD' | 'LATER' | 'READ') => void
  onCreate: () => void
  onRename: (folder: CollectionFolder) => void
  onDelete: (folder: CollectionFolder) => void
}) {
  return (
    <aside className="flex w-full flex-col gap-1 rounded-lg border bg-card p-3 lg:w-60 lg:shrink-0">
      <div className="mb-2 flex items-center justify-between px-1">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Bookmark className="h-4 w-4" aria-hidden />
          我的收藏
        </h2>
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onCreate} aria-label="新建收藏夹">
          <FolderPlus className="h-4 w-4" aria-hidden />
        </Button>
      </div>

      {/* 虚拟视图 */}
      <SidebarRow
        icon={<Bookmark className="h-4 w-4" aria-hidden />}
        label="全部"
        active={activeFolderId === 'ALL'}
        onClick={() => onSelect('ALL')}
      />
      <SidebarRow
        icon={<FileText className="h-4 w-4" aria-hidden />}
        label="未读"
        active={activeFolderId === 'UNREAD'}
        onClick={() => onSelect('UNREAD')}
      />
      <SidebarRow
        icon={<CalendarRange className="h-4 w-4" aria-hidden />}
        label="稍后读"
        active={activeFolderId === 'LATER'}
        onClick={() => onSelect('LATER')}
      />
      <SidebarRow
        icon={<Hash className="h-4 w-4" aria-hidden />}
        label="已读"
        active={activeFolderId === 'READ'}
        onClick={() => onSelect('READ')}
      />

      <div className="my-2 border-t" />

      {folders.map((f) => (
        <div
          key={f.id}
          className={cn(
            'group flex items-center rounded-md pr-1 transition-colors hover:bg-accent',
            activeFolderId === f.id && 'bg-accent',
          )}
        >
          <SidebarRow
            icon={
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: f.color ?? '#94a3b8' }}
                aria-hidden
              />
            }
            label={f.name}
            count={f.itemCount}
            active={activeFolderId === f.id}
            onClick={() => onSelect(f.id)}
            className="flex-1"
          />
          {!f.isDefault && (
            <div className="opacity-0 transition-opacity group-hover:opacity-100">
              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => onRename(f)}>
                <Plus className="h-3 w-3 rotate-45" aria-hidden />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6 text-red-500 hover:bg-red-100"
                onClick={() => onDelete(f)}
              >
                <Trash2 className="h-3 w-3" aria-hidden />
              </Button>
            </div>
          )}
        </div>
      ))}

      {folders.length === 0 && (
        <p className="px-3 py-6 text-center text-xs text-muted-foreground">
          还没有收藏夹
        </p>
      )}
    </aside>
  )
}

function SidebarRow({
  icon,
  label,
  count,
  active,
  onClick,
  className,
}: {
  icon: React.ReactNode
  label: string
  count?: number
  active: boolean
  onClick: () => void
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors',
        active
          ? 'bg-primary/10 font-medium text-primary'
          : 'text-foreground hover:bg-accent',
        className,
      )}
    >
      <span className="flex items-center gap-2 truncate">
        {icon}
        <span className="truncate">{label}</span>
      </span>
      {count !== undefined && (
        <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
      )}
    </button>
  )
}

function ItemCard({
  item,
  onEdit,
  onDelete,
  onMarkRead,
  onToggleReadLater,
}: {
  item: CollectionItem
  onEdit: (item: CollectionItem) => void
  onDelete: (item: CollectionItem) => void
  onMarkRead: (item: CollectionItem) => void | Promise<void>
  onToggleReadLater: (item: CollectionItem) => void | Promise<void>
}) {
  const ev = item.event
  return (
    <Card className="group p-4">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-2">
          <Folder className="h-3.5 w-3.5" aria-hidden />
          {item.folderName}
        </span>
        <span className="flex items-center gap-2">
          {item.userTags.map((t) => (
            <Badge key={t} variant="outline">
              <Tag className="mr-1 h-3 w-3" aria-hidden /> {t}
            </Badge>
          ))}
          <Badge
            variant={
              item.readStatus === 'READ'
                ? 'outline'
                : item.readStatus === 'LATER'
                ? 'warning'
                : 'default'
            }
          >
            {READ_LABELS[item.readStatus]}
          </Badge>
        </span>
      </div>

      <a
        href={`/events/${ev.id}`}
        className="line-clamp-2 text-base font-semibold leading-snug hover:text-primary"
      >
        {ev.title}
      </a>
      {ev.summaryOneLine && (
        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{ev.summaryOneLine}</p>
      )}

      {item.note && (
        <pre className="mt-3 max-h-20 overflow-hidden whitespace-pre-wrap rounded border border-dashed bg-muted/30 p-2 text-xs text-muted-foreground">
          📝 {item.note}
        </pre>
      )}

      <div className="mt-3 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          推荐 {ev.recommendIndex.toFixed(1)} · {ev.sourceCount} 个来源 · 收藏于{' '}
          {new Date(item.createdAt).toLocaleString('zh-CN')}
        </span>
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {item.readStatus !== 'READ' && (
            <Button size="sm" variant="ghost" onClick={() => onMarkRead(item)}>
              标已读
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => onToggleReadLater(item)}>
            {item.readStatus === 'LATER' ? '取消稍后' : '稍后读'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onEdit(item)}>
            编辑
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-red-500 hover:bg-red-100 hover:text-red-600"
            onClick={() => onDelete(item)}
          >
            移除
          </Button>
          <CollectionStarButton eventId={ev.id} isCollected />
        </div>
      </div>
    </Card>
  )
}

function EditDialog({
  open,
  item,
  folders,
  onClose,
  onSave,
}: {
  open: boolean
  item: CollectionItem | null
  folders: CollectionFolder[]
  onClose: () => void
  onSave: (
    payload: {
      folderId?: number
      note?: string | null
      userTags?: string[]
      readStatus?: ReadStatus
    },
  ) => Promise<void>
}) {
  const [folderId, setFolderId] = useState<number | undefined>(item?.folderId)
  const [note, setNote] = useState(item?.note ?? '')
  const [tagInput, setTagInput] = useState('')
  const [tags, setTags] = useState<string[]>(item?.userTags ?? [])
  const [readStatus, setReadStatus] = useState<ReadStatus>(item?.readStatus ?? 'UNREAD')
  const [saving, setSaving] = useState(false)

  // item 改变时 reset
  useMemo(() => {
    if (item) {
      setFolderId(item.folderId)
      setNote(item.note ?? '')
      setTags(item.userTags ?? [])
      setReadStatus(item.readStatus)
    }
  }, [item])

  if (!open || !item) return null

  function addTag() {
    const t = tagInput.trim()
    if (!t || t.length > 20) return
    if (!tags.includes(t)) setTags([...tags, t].slice(0, 10))
    setTagInput('')
  }

  async function handleSave() {
    setSaving(true)
    try {
      await onSave({
        folderId,
        note: note || null,
        userTags: tags,
        readStatus,
      })
      toast.success('已保存')
      onClose()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-background p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <h3 className="text-lg font-semibold">编辑收藏</h3>
          <Button size="icon" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>

        <div className="mb-2 text-sm font-medium text-muted-foreground">{item.event.title}</div>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs">收藏夹</label>
            <select
              value={folderId ?? ''}
              onChange={(e) =>
                setFolderId(e.target.value ? Number(e.target.value) : undefined)
              }
              className="w-full rounded border bg-background px-2 py-1.5 text-sm"
            >
              {folders.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs">阅读状态</label>
            <div className="flex gap-2">
              {(['UNREAD', 'LATER', 'READ'] as ReadStatus[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setReadStatus(s)}
                  className={cn(
                    'flex-1 rounded border px-2 py-1.5 text-sm transition-colors',
                    readStatus === s
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-input hover:bg-accent',
                  )}
                >
                  {READ_LABELS[s]}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs">标签（最多 10 个）</label>
            <div className="mb-1 flex flex-wrap gap-1">
              {tags.map((t) => (
                <Badge key={t} variant="outline" className="gap-1">
                  {t}
                  <button
                    type="button"
                    onClick={() => setTags(tags.filter((x) => x !== t))}
                  >
                    <X className="h-3 w-3" aria-hidden />
                  </button>
                </Badge>
              ))}
            </div>
            <div className="flex gap-1">
              <Input
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addTag()
                  }
                }}
                placeholder="输入标签后回车"
                maxLength={20}
              />
              <Button size="sm" onClick={addTag} disabled={!tagInput.trim()}>
                添加
              </Button>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs">笔记</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value.slice(0, 20000))}
              maxLength={20000}
              rows={5}
              placeholder="Markdown 文本（20000 字内）"
              className="w-full rounded border bg-background px-2 py-1.5 font-mono text-xs"
            />
            <div className="mt-1 text-right text-xs text-muted-foreground tabular-nums">
              {note.length}/20000
            </div>
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden />} 保存
          </Button>
        </div>
      </div>
    </div>
  )
}

function FolderDialog({
  open,
  mode,
  folder,
  onClose,
  onSave,
}: {
  open: boolean
  mode: 'create' | 'rename'
  folder: CollectionFolder | null
  onClose: () => void
  onSave: (payload: { name: string; color?: string }) => Promise<void>
}) {
  const [name, setName] = useState(folder?.name ?? '')
  const [color, setColor] = useState(folder?.color ?? '#3b82f6')
  const [saving, setSaving] = useState(false)
  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']

  useMemo(() => {
    if (folder) {
      setName(folder.name)
      setColor(folder.color ?? '#3b82f6')
    } else {
      setName('')
      setColor('#3b82f6')
    }
  }, [folder])

  if (!open) return null

  async function handleSave() {
    if (!name.trim()) {
      toast.error('名称不能为空')
      return
    }
    setSaving(true)
    try {
      await onSave({ name: name.trim(), color })
      toast.success(mode === 'create' ? '已创建' : '已保存')
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.errorCode === 'FOLDER_NAME_EXISTS') {
        toast.error('同名收藏夹已存在')
      } else if (err instanceof ApiError && err.errorCode === 'QUOTA_EXCEEDED') {
        toast.error('收藏夹已达上限（50）')
      } else {
        toast.error('操作失败')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div className="w-full max-w-sm rounded-lg border bg-background p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-lg font-semibold">
          {mode === 'create' ? '新建收藏夹' : '重命名收藏夹'}
        </h3>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs">名称</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
          </div>
          <div>
            <label className="mb-1 block text-xs">颜色</label>
            <div className="flex gap-2">
              {COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={cn(
                    'h-7 w-7 rounded-full border-2 transition-transform',
                    color === c ? 'scale-110 border-foreground' : 'border-transparent',
                  )}
                  style={{ backgroundColor: c }}
                  aria-label={c}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={saving || !name.trim()}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden />} 保存
          </Button>
        </div>
      </div>
    </div>
  )
}

// ============================================================ 主页面

type ActiveFolder = number | 'ALL' | 'UNREAD' | 'LATER' | 'READ'

export function CollectionPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const folderParam = searchParams.get('folder')
  const statusParam = searchParams.get('status')
  const tagParam = searchParams.get('tag')
  const keywordParam = searchParams.get('kw') ?? ''

  const [active, setActive] = useState<ActiveFolder>(
    statusParam
      ? (statusParam.toUpperCase() as ActiveFolder)
      : folderParam === 'all' || !folderParam
      ? 'ALL'
      : (Number(folderParam) as ActiveFolder),
  )
  const [keyword, setKeyword] = useState(keywordParam)
  const [tagFilter, setTagFilter] = useState<string | null>(tagParam)
  const [page, setPage] = useState(1)
  const [size] = useState(20)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [editItem, setEditItem] = useState<CollectionItem | null>(null)
  const [folderDialog, setFolderDialog] = useState<
    { mode: 'create' } | { mode: 'rename'; folder: CollectionFolder } | null
  >(null)

  // ---- queries
  const foldersQ = useFolders()
  const itemParams = useMemo(() => {
    const p: Parameters<typeof useItems>[0] = {
      keyword: keyword.trim() || undefined,
      userTag: tagFilter ?? undefined,
      sort: '-createdAt',
      page,
      size,
    }
    if (typeof active === 'number') p.folderId = active
    else if (['UNREAD', 'LATER', 'READ'].includes(active))
      p.readStatus = active as ReadStatus
    return p
  }, [active, keyword, tagFilter, page, size])
  const itemsQ = useItems(itemParams)
  const statsQ = useStats()

  // ---- mutations
  const createFolderMut = useCreateFolder()
  const updateFolderMut = useUpdateFolder()
  const deleteFolderMut = useDeleteFolder()
  const updateItemMut = useUpdateItem()
  const deleteItemMut = useDeleteItem()
  const batchMut = useBatchItems()

  // ---- side effects
  const items = itemsQ.data?.items ?? []
  const total = itemsQ.data?.total ?? 0

  function handleSelectChange(folder: ActiveFolder) {
    setActive(folder)
    setPage(1)
    setSelected(new Set())
    if (typeof folder === 'number') {
      setSearchParams({ folder: String(folder) })
    } else if (['UNREAD', 'LATER', 'READ'].includes(folder as string)) {
      setSearchParams({ status: (folder as string).toLowerCase() })
    } else {
      setSearchParams({})
    }
  }

  function handleDeleteItem(item: CollectionItem) {
    if (!confirm(`确定要取消收藏「${item.event.title}」吗？`)) return
    deleteItemMut.mutate(item.id, {
      onSuccess: () => toast.success('已取消收藏'),
      onError: () => toast.error('操作失败'),
    })
  }

  async function handleMarkRead(item: CollectionItem) {
    try {
      await updateItemMut.mutateAsync({ id: item.id, payload: { readStatus: 'READ' } })
      toast.success('已标为已读')
    } catch {
      toast.error('操作失败')
    }
  }

  async function handleToggleReadLater(item: CollectionItem) {
    const next = item.readStatus === 'LATER' ? 'UNREAD' : 'LATER'
    try {
      await updateItemMut.mutateAsync({ id: item.id, payload: { readStatus: next } })
      toast.success(next === 'LATER' ? '加入稍后读' : '已移出稍后读')
    } catch {
      toast.error('操作失败')
    }
  }

  async function handleSaveItem(payload: {
    folderId?: number
    note?: string | null
    userTags?: string[]
    readStatus?: ReadStatus
  }) {
    if (!editItem) return
    await updateItemMut.mutateAsync({ id: editItem.id, payload })
  }

  async function handleBatch(action: BatchPayload['action'], extra: Partial<BatchPayload> = {}) {
    if (selected.size === 0) return
    const itemIds = Array.from(selected)
    try {
      const res = await batchMut.mutateAsync({
        itemIds,
        action,
        ...extra,
      } as BatchPayload)
      toast.success(`已影响 ${res.affectedCount} 条`)
      setSelected(new Set())
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : '批量操作失败')
    }
  }

  function toggleSelect(id: number) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-4 lg:flex-row lg:p-6">
      <FolderSidebar
        folders={foldersQ.data ?? []}
        activeFolderId={active}
        onSelect={handleSelectChange}
        onCreate={() => setFolderDialog({ mode: 'create' })}
        onRename={(folder) =>
          setFolderDialog({ mode: 'rename', folder })
        }
        onDelete={(folder) => {
          if (!confirm(`删除收藏夹「${folder.name}」？条目会迁回「我的收藏」。`)) return
          deleteFolderMut.mutate(folder.id, {
            onSuccess: () => toast.success('已删除'),
            onError: () => toast.error('操作失败'),
          })
        }}
      />

      <main className="flex min-w-0 flex-1 flex-col gap-3">
        {/* 顶部筛选 */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
            <Input
              value={keyword}
              onChange={(e) => {
                setKeyword(e.target.value)
                setPage(1)
              }}
              placeholder="搜索笔记 / 标题"
              className="pl-8"
            />
          </div>
          {tagFilter && (
            <Badge variant="outline" className="gap-1">
              <Tag className="h-3 w-3" aria-hidden />
              {tagFilter}
              <button type="button" onClick={() => setTagFilter(null)}>
                <X className="h-3 w-3" aria-hidden />
              </button>
            </Badge>
          )}
          {(keyword || tagFilter) && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setKeyword('')
                setTagFilter(null)
                setPage(1)
              }}
            >
              重置筛选
            </Button>
          )}
        </div>

        {/* 统计 */}
        {statsQ.data && (
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <Stat label="总计" value={statsQ.data.totalItems} />
            <Stat label="未读" value={statsQ.data.unreadCount} />
            <Stat label="稍后读" value={statsQ.data.laterCount} />
            <Stat label="已读" value={statsQ.data.readCount} />
          </div>
        )}

        {/* 批量操作条 */}
        {selected.size > 0 && (
          <Card className="flex flex-wrap items-center gap-2 border-amber-400 bg-amber-50 p-3 dark:bg-amber-950/30">
            <span className="text-sm">已选 {selected.size} 条</span>
            <Button size="sm" variant="outline" onClick={() => handleBatch('MARK_READ')}>
              标已读
            </Button>
            <Button size="sm" variant="outline" onClick={() => handleBatch('DELETE')}>
              批量删除
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelected(new Set())}
            >
              取消选择
            </Button>
          </Card>
        )}

        {/* 列表 */}
        {itemsQ.isPending ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : itemsQ.isError ? (
          <div className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700">
            加载失败：{itemsQ.error instanceof ApiError ? itemsQ.error.message : '未知错误'}
          </div>
        ) : items.length === 0 ? (
          <Card className="flex flex-col items-center justify-center gap-2 p-12 text-center">
            <Bookmark className="h-10 w-10 text-muted-foreground/40" aria-hidden />
            <p className="text-sm text-muted-foreground">
              {keyword || tagFilter ? '当前筛选条件下暂无收藏' : '还没有收藏，去热点中心逛逛'}
            </p>
          </Card>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <div key={item.id} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-5"
                  checked={selected.has(item.id)}
                  onChange={() => toggleSelect(item.id)}
                  aria-label={`选择 ${item.event.title}`}
                />
                <div className="min-w-0 flex-1">
                  <ItemCard
                    item={item}
                    onEdit={setEditItem}
                    onDelete={handleDeleteItem}
                    onMarkRead={handleMarkRead}
                    onToggleReadLater={handleToggleReadLater}
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 分页 */}
        {total > size && (
          <div className="flex items-center justify-center gap-2 py-2 text-sm">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              上一页
            </Button>
            <span>
              第 {page} 页 / 共 {Math.ceil(total / size)} 页（{total} 条）
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= Math.ceil(total / size)}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </Button>
          </div>
        )}
      </main>

      {/* Dialogs */}
      <EditDialog
        open={!!editItem}
        item={editItem}
        folders={foldersQ.data ?? []}
        onClose={() => setEditItem(null)}
        onSave={handleSaveItem}
      />
      <FolderDialog
        open={folderDialog !== null}
        mode={folderDialog?.mode ?? 'create'}
        folder={folderDialog && folderDialog.mode === 'rename' ? folderDialog.folder : null}
        onClose={() => setFolderDialog(null)}
        onSave={async (payload) => {
          if (folderDialog?.mode === 'create') {
            await createFolderMut.mutateAsync(payload)
          } else if (folderDialog?.mode === 'rename') {
            await updateFolderMut.mutateAsync({
              id: folderDialog.folder.id,
              payload,
            })
          }
        }}
      />
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border bg-card px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
    </div>
  )
}
