import { Card } from '@/components/ui/card'

export function EventCardSkeleton() {
  return (
    <Card className="p-5">
      <div className="animate-pulse">
        <div className="mb-3 flex gap-2">
          <div className="h-4 w-12 rounded bg-muted" />
          <div className="h-4 w-16 rounded bg-muted" />
        </div>
        <div className="h-5 w-4/5 rounded bg-muted" />
        <div className="mt-2 h-4 w-3/5 rounded bg-muted" />
        <div className="mt-5 flex gap-3 border-t border-border pt-3">
          <div className="h-3 w-24 rounded bg-muted" />
          <div className="h-3 w-16 rounded bg-muted" />
          <div className="ml-auto h-3 w-14 rounded bg-muted" />
        </div>
      </div>
    </Card>
  )
}

export function EventListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }, (_, i) => (
        <EventCardSkeleton key={i} />
      ))}
    </div>
  )
}
