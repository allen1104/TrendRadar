import { Star } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { toast } from '@/components/ui/toast'
import { ApiError } from '@/lib/api/client'
import {
  useCreateItem,
} from '@/features/collection/hooks/useCollection'
import { useCurrentRole } from '@/stores/authStore'

interface Props {
  eventId: number
  isCollected: boolean
  /** 'icon' = 卡片紧凑星标；'full' = 详情页文字按钮 */
  variant?: 'icon' | 'full'
}

/**
 * 列表/详情页上的 ⭐ 按钮。
 * - 未登录：禁用并提示
 * - 未收藏：点击 → 写入默认收藏夹（乐观更新）
 * - 已收藏：点击 → 跳到 /collections 让用户找到该事件
 */
export function CollectionStarButton({
  eventId,
  isCollected,
  variant = 'icon',
}: Props) {
  const navigate = useNavigate()
  const role = useCurrentRole()
  const isLoggedIn = role !== 'GUEST'
  const createMut = useCreateItem()

  const handleClick = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!isLoggedIn) {
      toast.error('请先登录后再收藏')
      return
    }
    if (isCollected) {
      navigate('/collections')
      return
    }
    try {
      await createMut.mutateAsync({ eventId, readStatus: 'UNREAD' })
      toast.success('已收藏到「我的收藏」')
    } catch (err) {
      if (err instanceof ApiError && err.errorCode === 'ALREADY_COLLECTED') {
        // 已被收藏，跳过去看
        navigate('/collections')
      } else if (err instanceof ApiError && err.errorCode === 'QUOTA_EXCEEDED') {
        toast.error('收藏已达上限（10000 条）')
      } else {
        toast.error('收藏失败，请稍后重试')
      }
    }
  }

  if (!isLoggedIn) {
    return (
      <button
        type="button"
        disabled
        title="登录后收藏"
        aria-label="登录后收藏"
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-input bg-background text-muted-foreground opacity-50"
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          toast.error('请先登录后再收藏')
        }}
      >
        <Star className="h-4 w-4" aria-hidden />
      </button>
    )
  }

  if (variant === 'full') {
    return (
      <button
        type="button"
        onClick={handleClick}
        className={
          'inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium ' +
          'border transition-colors ' +
          (isCollected
            ? 'border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100 dark:bg-amber-950/30 dark:text-amber-300'
            : 'border-input bg-background hover:bg-accent hover:text-foreground')
        }
        aria-label={isCollected ? '已收藏' : '收藏'}
      >
        <Star className={isCollected ? 'h-4 w-4 fill-current' : 'h-4 w-4'} aria-hidden />
        {isCollected ? '已收藏' : '收藏'}
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={createMut.isPending}
      title={isCollected ? '已收藏' : '收藏'}
      aria-label={isCollected ? '已收藏' : '收藏'}
      className={
        'inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background transition-colors ' +
        'hover:bg-accent ' +
        (isCollected
          ? 'border-amber-400 text-amber-500'
          : 'border-input text-muted-foreground hover:text-foreground')
      }
    >
      <Star
        className={isCollected ? 'h-4 w-4 fill-current' : 'h-4 w-4'}
        aria-hidden
      />
    </button>
  )
}
