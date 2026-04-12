interface HealthRingProps {
  score: number // 0-100
  size?: number // px
  strokeWidth?: number
  label?: string
  className?: string
}

function getColor(score: number): string {
  if (score >= 80) return '#22C55E'
  if (score >= 50) return '#F59E0B'
  return '#EF4444'
}

function getLabel(score: number): string {
  if (score >= 80) return 'Healthy'
  if (score >= 50) return 'Warning'
  return 'Critical'
}

export function HealthRing({ score, size = 120, strokeWidth = 8, label, className = '' }: HealthRingProps) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference
  const color = getColor(score)

  return (
    <div className={`relative inline-flex items-center justify-center ${className}`}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#1E293B"
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* Score ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold text-goose-text">{score}</span>
        <span className="text-[10px] text-goose-text-muted uppercase tracking-wide">
          {label || getLabel(score)}
        </span>
      </div>
    </div>
  )
}
