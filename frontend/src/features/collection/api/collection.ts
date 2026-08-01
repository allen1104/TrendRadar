import { ApiError, http, type Page } from '@/lib/api/client'

// ---------- 枚举 / 子类型（与后端 schema 对齐） ----------

export type ReadStatus = 'UNREAD' | 'LATER' | 'READ'

export interface CollectionFolder {
  id: number
  name: string
  description: string | null
  color: string | null
  sortOrder: number
  isDefault: boolean
  itemCount: number
  createdAt: string
  updatedAt: string
}

export interface EventBrief {
  id: number
  title: string
  summaryOneLine: string | null
  categories: string[]
  recommendIndex: number
  sourceCount: number
  lastSeenAt: string | null
}

export interface CollectionItem {
  id: number
  folderId: number
  folderName: string
  note: string | null
  userTags: string[]
  readStatus: ReadStatus
  readAt: string | null
  createdAt: string
  updatedAt: string
  event: EventBrief
}

export interface StatsResponse {
  totalItems: number
  unreadCount: number
  laterCount: number
  readCount: number
  folderCount: number
  byCategory: { category: string; count: number }[]
  recentMonths: { month: string; count: number }[]
}

// ---------- 请求体 ----------

export interface FolderCreatePayload {
  name: string
  description?: string | null
  color?: string | null
}

export interface FolderUpdatePayload {
  name?: string
  description?: string | null
  color?: string | null
  sortOrder?: number
}

export interface ItemCreatePayload {
  eventId: number
  folderId?: number | null
  note?: string | null
  userTags?: string[]
  readStatus?: ReadStatus
}

export interface ItemUpdatePayload {
  folderId?: number | null
  note?: string | null
  userTags?: string[]
  readStatus?: ReadStatus
}

export type BatchAction = 'MOVE' | 'DELETE' | 'MARK_READ' | 'ADD_TAG' | 'REMOVE_TAG'

export interface BatchPayload {
  itemIds: number[]
  action: BatchAction
  targetFolderId?: number
  tag?: string
}

// ---------- 列表参数 ----------

export interface ItemListParams {
  folderId?: number
  readStatus?: ReadStatus
  userTag?: string
  keyword?: string
  sort?: string
  page?: number
  size?: number
}

// ---------- API ----------

function qs(params: Record<string, unknown>): string {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    u.set(k, String(v))
  }
  const s = u.toString()
  return s ? `?${s}` : ''
}

export const collectionApi = {
  // -------- folders
  listFolders: async (): Promise<CollectionFolder[]> =>
    (await http.get<CollectionFolder[]>('/collections/folders')).data,

  createFolder: async (payload: FolderCreatePayload): Promise<CollectionFolder> =>
    (await http.post<CollectionFolder>('/collections/folders', payload)).data,

  updateFolder: async (
    id: number,
    payload: FolderUpdatePayload,
  ): Promise<CollectionFolder> =>
    (await http.patch<CollectionFolder>(`/collections/folders/${id}`, payload)).data,

  deleteFolder: async (id: number): Promise<void> => {
    await http.delete(`/collections/folders/${id}`)
  },

  // -------- items
  listItems: async (
    params: ItemListParams,
  ): Promise<Page<CollectionItem>> => {
    const q = qs({
      folderId: params.folderId,
      readStatus: params.readStatus,
      userTag: params.userTag,
      keyword: params.keyword,
      sort: params.sort,
      page: params.page ?? 1,
      size: params.size ?? 20,
    })
    return (await http.get<Page<CollectionItem>>(`/collections/items${q}`)).data
  },

  createItem: async (payload: ItemCreatePayload): Promise<CollectionItem> => {
    try {
      return (await http.post<CollectionItem>('/collections/items', payload)).data
    } catch (err) {
      // 重复收藏 → 后端已经把 existingItemId 透传到 err.body 里，这里原样重抛
      if (err instanceof ApiError && err.errorCode === 'ALREADY_COLLECTED') {
        throw err
      }
      throw err
    }
  },

  updateItem: async (
    id: number,
    payload: ItemUpdatePayload,
  ): Promise<CollectionItem> =>
    (await http.patch<CollectionItem>(`/collections/items/${id}`, payload)).data,

  deleteItem: async (id: number): Promise<void> => {
    await http.delete(`/collections/items/${id}`)
  },

  batchItems: async (payload: BatchPayload): Promise<{ affectedCount: number }> =>
    (await http.post<{ affectedCount: number }>(
      '/collections/items/batch',
      payload,
    )).data,

  // -------- stats
  getStats: async (): Promise<StatsResponse> =>
    (await http.get<StatsResponse>('/collections/stats')).data,

  // -------- hotspot 集成
  listCollectedEventIds: async (eventIds: number[]): Promise<number[]> => {
    const data = (
      await http.get<{ eventIds: number[] }>(
        `/collections/items/event-ids${qs({ eventIds: eventIds.join(',') })}`,
      )
    ).data
    return data.eventIds
  },
}
