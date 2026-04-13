import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { KPICard } from '@/components/ui/KPICard'
import { Button } from '@/components/ui/Button'
import { ProBadge } from '@/components/ui/Badge'
import { proApi } from '@/lib/proApi'
import type { Campaign } from '@/lib/proTypes'

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-6 w-6 text-goose-accent" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function campaignStatusVariant(status: Campaign['status']) {
  switch (status) {
    case 'ACTIVE': return 'accent' as const
    case 'COMPLETE': return 'success' as const
    case 'PLANNING': return 'warning' as const
    case 'ARCHIVED': return 'default' as const
  }
}

export function CampaignsPage() {
  const navigate = useNavigate()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newPlatform, setNewPlatform] = useState('')

  const fetchCampaigns = async () => {
    try {
      setError(null)
      const data = await proApi.get<Campaign[]>('/api/campaigns')
      setCampaigns(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load campaigns')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCampaigns()
  }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      await proApi.post('/api/campaigns', { name: newName.trim(), platform_name: newPlatform.trim() })
      setNewName('')
      setNewPlatform('')
      setShowForm(false)
      setLoading(true)
      await fetchCampaigns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create campaign')
    } finally {
      setCreating(false)
    }
  }

  const total = campaigns.length
  const active = campaigns.filter(c => c.status === 'ACTIVE').length
  const totalRuns = campaigns.reduce((s, c) => s + c.total_runs, 0)
  const totalPassed = campaigns.reduce((s, c) => s + c.passed_runs, 0)
  const passRate = totalRuns > 0 ? Math.round((totalPassed / totalRuns) * 100) : 0

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            Test Campaigns <ProBadge />
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            Manage GPS-denied navigation validation test campaigns
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>+ New Campaign</Button>
      </div>

      {/* Inline create form */}
      {showForm && (
        <Card className="border-goose-accent/30 bg-goose-accent/5">
          <CardTitle className="mb-4">New Campaign</CardTitle>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Campaign Name *</label>
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="e.g. Q2 VIO Validation"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Platform Name</label>
              <input
                value={newPlatform}
                onChange={e => setNewPlatform(e.target.value)}
                placeholder="e.g. Holybro X500 V2"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button variant="secondary" onClick={() => { setShowForm(false); setNewName(''); setNewPlatform('') }}>
              Cancel
            </Button>
            <Button onClick={handleCreate} loading={creating} disabled={!newName.trim()}>
              Create Campaign
            </Button>
          </div>
        </Card>
      )}

      {/* Error */}
      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">
          {error}
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard label="Total Campaigns" value={total} />
        <KPICard label="Active" value={active} status={active > 0 ? 'healthy' : 'neutral'} />
        <KPICard label="Total Runs" value={totalRuns} />
        <KPICard label="Overall Pass Rate" value={`${passRate}%`} status={passRate >= 80 ? 'healthy' : passRate >= 50 ? 'warning' : 'critical'} />
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner />
        </div>
      )}

      {/* Empty state */}
      {!loading && campaigns.length === 0 && (
        <div className="text-center py-16 text-goose-text-muted">
          <p className="text-lg font-medium text-goose-text">No Campaigns Yet</p>
          <p className="text-sm mt-2">Create a test campaign to begin GPS-denied validation.</p>
          <Button className="mt-6" onClick={() => setShowForm(true)}>Create First Campaign</Button>
        </div>
      )}

      {/* Campaigns table */}
      {!loading && campaigns.length > 0 && (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-goose-border">
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Name</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Platform</th>
                  <th className="text-right px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Runs</th>
                  <th className="text-right px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Pass %</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Created</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {campaigns.map(c => {
                  const pct = c.total_runs > 0 ? Math.round((c.passed_runs / c.total_runs) * 100) : 0
                  return (
                    <tr key={c.id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover transition-colors">
                      <td className="px-4 py-3 font-medium text-goose-text">{c.name}</td>
                      <td className="px-4 py-3">
                        <Badge variant={campaignStatusVariant(c.status)}>{c.status}</Badge>
                      </td>
                      <td className="px-4 py-3 text-goose-text-secondary">{c.platform_name || '—'}</td>
                      <td className="px-4 py-3 text-right font-mono text-goose-text">{c.total_runs}</td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono font-medium ${pct >= 80 ? 'text-goose-success' : pct >= 50 ? 'text-goose-warning' : 'text-goose-error'}`}>
                          {c.total_runs > 0 ? `${pct}%` : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-goose-text-muted text-xs">
                        {new Date(c.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3">
                        <Button size="sm" variant="secondary" onClick={() => navigate(`/pro/campaigns/${c.id}`)}>
                          View
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
