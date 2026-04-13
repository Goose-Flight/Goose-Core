import { useState, useEffect } from 'react'
import { Card, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { ProBadge } from '@/components/ui/Badge'
import { proApi } from '@/lib/proApi'
import type { AuditEntry } from '@/lib/proTypes'

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-6 w-6 text-goose-accent" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function actionVariant(action: string) {
  const a = action.toLowerCase()
  if (a.includes('login') || a.includes('auth')) return 'accent' as const
  if (a.includes('create') || a.includes('add')) return 'success' as const
  if (a.includes('delete') || a.includes('remove')) return 'error' as const
  if (a.includes('update') || a.includes('edit') || a.includes('modify')) return 'warning' as const
  return 'default' as const
}

export function AuditTrailPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    proApi.get<AuditEntry[]>('/api/auth/audit')
      .then(data => { if (!cancelled) setEntries(data.slice(0, 100)) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load audit trail') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const hasToken = !!localStorage.getItem('goose_pro_token')

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
          Audit Trail <ProBadge />
        </h1>
        <p className="text-sm text-goose-text-muted mt-1">
          Most recent 100 entries — all Pro server actions are logged here
        </p>
      </div>

      {/* Not logged in */}
      {!hasToken && (
        <Card className="border-goose-warning/30 bg-goose-warning/5">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-goose-warning shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <div>
              <p className="text-sm font-medium text-goose-warning">Pro Authentication Required</p>
              <p className="text-xs text-goose-text-muted mt-1">
                A <code className="font-mono text-goose-text">goose_pro_token</code> is required to view the audit trail.
              </p>
            </div>
          </div>
        </Card>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-64"><LoadingSpinner /></div>
      )}

      {!loading && entries.length === 0 && !error && (
        <div className="text-center py-16 text-goose-text-muted">
          <p className="text-lg font-medium text-goose-text">No Audit Entries</p>
          <p className="text-sm mt-2">Actions on the Pro server will appear here.</p>
        </div>
      )}

      {!loading && entries.length > 0 && (
        <Card padding="none">
          <div className="px-4 py-3 border-b border-goose-border">
            <CardTitle>{entries.length} entries</CardTitle>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-goose-border">
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Timestamp</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">User</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Action</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Target</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Details</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(entry => (
                  <tr key={entry.entry_id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                    <td className="px-4 py-2.5 text-xs font-mono text-goose-text-muted whitespace-nowrap">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-xs font-mono text-goose-text whitespace-nowrap">
                      {entry.username}
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <Badge variant={actionVariant(entry.action)}>
                        {entry.action.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-goose-text-secondary max-w-[200px] truncate">
                      {entry.target || '—'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-goose-text-muted max-w-[300px] truncate">
                      {/* intentionally blank — target is the main identifier */}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
