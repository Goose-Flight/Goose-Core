interface SkeletonProps {
  className?: string
  width?: string
  height?: string
}

export function Skeleton({ className = '', width, height }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse bg-goose-surface-hover rounded-lg ${className}`}
      style={{ width, height }}
    />
  )
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-goose-surface border border-goose-border rounded-xl p-4 space-y-3 ${className}`}>
      <Skeleton height="12px" width="40%" />
      <Skeleton height="28px" width="60%" />
      <Skeleton height="10px" width="80%" />
    </div>
  )
}

export function SkeletonChart({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-goose-surface border border-goose-border rounded-xl p-4 ${className}`}>
      <Skeleton height="12px" width="30%" className="mb-4" />
      <div className="flex items-end gap-1 h-[200px]">
        {Array.from({ length: 40 }).map((_, i) => (
          <Skeleton
            key={i}
            className="flex-1"
            height={`${20 + Math.random() * 80}%`}
          />
        ))}
      </div>
    </div>
  )
}

export function SkeletonPage() {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="space-y-2">
        <Skeleton height="32px" width="250px" />
        <Skeleton height="14px" width="400px" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
      <SkeletonChart />
      <SkeletonChart />
    </div>
  )
}
