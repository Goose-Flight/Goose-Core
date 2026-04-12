import type { ReactNode } from 'react'
import type { Severity, ConfidenceBand, PluginTrustState } from '@/lib/types'

// --- Severity Badge ---

const severityStyles: Record<Severity, string> = {
  critical: 'bg-goose-severity-critical/15 text-goose-severity-critical border-goose-severity-critical/30',
  warning: 'bg-goose-severity-warning/15 text-goose-severity-warning border-goose-severity-warning/30',
  info: 'bg-goose-severity-info/15 text-goose-severity-info border-goose-severity-info/30',
  pass: 'bg-goose-severity-pass/15 text-goose-severity-pass border-goose-severity-pass/30',
}

const severityLabels: Record<Severity, string> = {
  critical: 'CRITICAL',
  warning: 'WARNING',
  info: 'INFO',
  pass: 'PASS',
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border ${severityStyles[severity]}`}>
      {severityLabels[severity]}
    </span>
  )
}

// --- Confidence Badge ---

const confidenceStyles: Record<ConfidenceBand, string> = {
  HIGH: 'bg-goose-confidence-high/15 text-goose-confidence-high',
  MEDIUM: 'bg-goose-confidence-medium/15 text-goose-confidence-medium',
  LOW: 'bg-goose-confidence-low/15 text-goose-confidence-low',
  UNKNOWN: 'bg-goose-confidence-unknown/15 text-goose-confidence-unknown',
}

export function ConfidenceBadge({ band, score }: { band: ConfidenceBand; score?: number }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded ${confidenceStyles[band]}`}>
      {band}
      {score !== undefined && <span className="opacity-70">({score}%)</span>}
    </span>
  )
}

// --- Trust Badge ---

const trustStyles: Record<PluginTrustState, { bg: string; label: string }> = {
  BUILTIN_TRUSTED: { bg: 'bg-goose-success/10 text-goose-success', label: 'Trusted' },
  LOCAL_SIGNED: { bg: 'bg-goose-info/10 text-goose-info', label: 'Signed' },
  LOCAL_UNSIGNED: { bg: 'bg-goose-warning/10 text-goose-warning', label: 'Unsigned' },
  COMMUNITY: { bg: 'bg-goose-info/10 text-goose-info', label: 'Community' },
  ENTERPRISE_TRUSTED: { bg: 'bg-goose-accent/10 text-goose-accent', label: 'Enterprise' },
  BLOCKED: { bg: 'bg-goose-error/10 text-goose-error', label: 'Blocked' },
}

export function TrustBadge({ trust }: { trust: PluginTrustState }) {
  const style = trustStyles[trust]
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded ${style.bg}`}>
      {style.label}
    </span>
  )
}

// --- Pro Badge ---

export function ProBadge() {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest rounded bg-goose-accent/20 text-goose-accent border border-goose-accent/30">
      PRO
    </span>
  )
}

// --- Generic Badge ---

interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info' | 'accent'
  className?: string
}

const genericStyles = {
  default: 'bg-goose-surface-hover text-goose-text-secondary',
  success: 'bg-goose-success/15 text-goose-success',
  warning: 'bg-goose-warning/15 text-goose-warning',
  error: 'bg-goose-error/15 text-goose-error',
  info: 'bg-goose-info/15 text-goose-info',
  accent: 'bg-goose-accent/15 text-goose-accent',
}

export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded ${genericStyles[variant]} ${className}`}>
      {children}
    </span>
  )
}
