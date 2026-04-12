interface ProgressBarProps {
  value: number // 0-100
  max?: number
  label?: string
  showValue?: boolean
  size?: 'sm' | 'md' | 'lg'
  color?: 'auto' | 'accent' | 'success' | 'warning' | 'error'
  className?: string
}

function getAutoColor(value: number): string {
  if (value >= 80) return 'bg-goose-success'
  if (value >= 50) return 'bg-goose-warning'
  return 'bg-goose-error'
}

const colorMap = {
  accent: 'bg-goose-accent',
  success: 'bg-goose-success',
  warning: 'bg-goose-warning',
  error: 'bg-goose-error',
}

const sizeMap = {
  sm: 'h-1.5',
  md: 'h-2.5',
  lg: 'h-4',
}

export function ProgressBar({
  value,
  max = 100,
  label,
  showValue = true,
  size = 'md',
  color = 'auto',
  className = '',
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const barColor = color === 'auto' ? getAutoColor(pct) : colorMap[color]

  return (
    <div className={className}>
      {(label || showValue) && (
        <div className="flex items-center justify-between mb-1">
          {label && <span className="text-xs text-goose-text-muted">{label}</span>}
          {showValue && <span className="text-xs font-medium text-goose-text">{Math.round(pct)}%</span>}
        </div>
      )}
      <div className={`w-full bg-goose-border rounded-full overflow-hidden ${sizeMap[size]}`}>
        <div
          className={`${barColor} ${sizeMap[size]} rounded-full transition-all duration-500 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
