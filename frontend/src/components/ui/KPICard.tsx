import type { ReactNode } from 'react'

interface KPICardProps {
  label: string
  value: string | number
  unit?: string
  subtitle?: string
  icon?: ReactNode
  status?: 'healthy' | 'warning' | 'critical' | 'neutral'
  trend?: 'up' | 'down' | 'flat'
  className?: string
}

const statusColors = {
  healthy: 'text-goose-success',
  warning: 'text-goose-warning',
  critical: 'text-goose-error',
  neutral: 'text-goose-text',
}

const statusDots = {
  healthy: 'bg-goose-success',
  warning: 'bg-goose-warning',
  critical: 'bg-goose-error',
  neutral: 'bg-goose-text-muted',
}

export function KPICard({ label, value, unit, subtitle, icon, status = 'neutral', className = '' }: KPICardProps) {
  return (
    <div className={`bg-goose-surface border border-goose-border rounded-xl p-4 ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-goose-text-muted uppercase tracking-wide">{label}</span>
        {icon && <span className="text-goose-text-muted">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-1.5">
        {status !== 'neutral' && (
          <span className={`w-2 h-2 rounded-full ${statusDots[status]} shrink-0 mt-1`} />
        )}
        <span className={`text-2xl font-bold ${statusColors[status]}`}>{value}</span>
        {unit && <span className="text-sm text-goose-text-muted">{unit}</span>}
      </div>
      {subtitle && <p className="text-xs text-goose-text-muted mt-1">{subtitle}</p>}
    </div>
  )
}
