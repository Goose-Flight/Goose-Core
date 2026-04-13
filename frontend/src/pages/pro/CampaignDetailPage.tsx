import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { KPICard } from '@/components/ui/KPICard'
import { Button } from '@/components/ui/Button'
import { ProBadge } from '@/components/ui/Badge'
import { proApi } from '@/lib/proApi'
import type { Campaign, TestRun } from '@/lib/proTypes'

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-6 w-6 text-goose-accent" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function outcomeVariant(outcome: TestRun['outcome']) {
  switch (outcome) {
    case 'PASS': return 'success' as const
    case 'FAIL': return 'error' as const
    case 'MARGINAL': return 'warning' as const
    case 'PENDING': return 'default' as const
  }
}

function gradeVariant(grade: string) {
  switch (grade) {
    case 'PASS': return 'success' as const
    case 'FAIL': return 'error' as const
    case 'MARGINAL': return 'warning' as const
    default: return 'default' as const
  }
}

function campaignStatusVariant(status: Campaign['status']) {
  switch (status) {
    case 'ACTIVE': return 'accent' as const
    case 'COMPLETE': return 'success' as const
    case 'PLANNING': return 'warning' as const
    case 'ARCHIVED': return 'default' as const
  }
}

interface TestCaseResult {
  test_case_id: string
  runs: number
  passed: number
  cep: number | null
  grade: string
}

function buildTestCaseMatrix(runs: TestRun[]): TestCaseResult[] {
  const map = new Map<string, TestCaseResult>()
  for (const run of runs) {
    const existing = map.get(run.test_case_id) ?? {
      test_case_id: run.test_case_id,
      runs: 0,
      passed: 0,
      cep: null,
      grade: 'PENDING',
    }
    existing.runs++
    if (run.outcome === 'PASS') existing.passed++
    const cep = run.metrics_json?.cep_m as number | undefined
    if (cep !== undefined && cep !== null) {
      existing.cep = existing.cep === null ? cep : Math.min(existing.cep, cep)
    }
    map.set(run.test_case_id, existing)
  }
  for (const result of map.values()) {
    const pct = result.runs > 0 ? result.passed / result.runs : 0
    result.grade = pct >= 0.9 ? 'PASS' : pct >= 0.5 ? 'MARGINAL' : result.runs === 0 ? 'PENDING' : 'FAIL'
  }
  return Array.from(map.values())
}

function durationStr(run: TestRun): string {
  if (!run.completed_at || !run.started_at) return '—'
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
  if (ms < 0) return '—'
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export function CampaignDetailPage() {
  const { campaignId } = useParams<{ campaignId: string }>()
  const navigate = useNavigate()
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [runs, setRuns] = useState<TestRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [reportLink, setReportLink] = useState<string | null>(null)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false

    async function load() {
      try {
        setError(null)
        const [camp, runList] = await Promise.all([
          proApi.get<Campaign>(`/api/campaigns/${campaignId}`),
          proApi.get<TestRun[]>(`/api/campaigns/${campaignId}/runs`),
        ])
        if (!cancelled) {
          setCampaign(camp)
          setRuns(runList)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load campaign')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [campaignId])

  const handleGenerateReport = async () => {
    if (!campaignId) return
    setGenerating(true)
    try {
      const result = await proApi.post<{ report_id: string }>('/api/reports/validation', { campaign_id: campaignId })
      setReportLink(`/api/reports/${result.report_id}/html`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate report')
    } finally {
      setGenerating(false)
    }
  }

  const matrix = buildTestCaseMatrix(runs)
  const completionPct = runs.length > 0 ? Math.round((runs.filter(r => r.outcome !== 'PENDING').length / runs.length) * 100) : 0
  const passedCount = runs.filter(r => r.outcome === 'PASS').length
  const failedCount = runs.filter(r => r.outcome === 'FAIL').length

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
        <Button variant="ghost" className="mt-4" onClick={() => navigate('/pro/campaigns')}>&larr; Back to Campaigns</Button>
      </div>
    )
  }

  if (!campaign) return null

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate('/pro/campaigns')} className="mb-2">
            &larr; Back to Campaigns
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            {campaign.name} <ProBadge />
            <Badge variant={campaignStatusVariant(campaign.status)}>{campaign.status}</Badge>
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">{campaign.platform_name || 'No platform specified'}</p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={() => navigate(`/pro/campaigns/${campaignId}/accuracy`)}>
            Accuracy
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/pro/campaigns/${campaignId}/trajectory`)}>
            Trajectory
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/pro/campaigns/${campaignId}/gps-denial`)}>
            GPS Denial
          </Button>
          <Button loading={generating} onClick={handleGenerateReport}>
            Generate Report
          </Button>
        </div>
      </div>

      {/* Report link */}
      {reportLink && (
        <Card className="border-goose-success/30 bg-goose-success/5">
          <p className="text-sm text-goose-success font-medium">
            Report generated.{' '}
            <a href={reportLink} target="_blank" rel="noopener noreferrer" className="underline hover:text-goose-text">
              Download HTML Report
            </a>
          </p>
        </Card>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard label="Total Runs" value={runs.length} />
        <KPICard label="Passed" value={passedCount} status={passedCount > 0 ? 'healthy' : 'neutral'} />
        <KPICard label="Failed" value={failedCount} status={failedCount > 0 ? 'critical' : 'neutral'} />
        <KPICard label="Completion" value={`${completionPct}%`} status={completionPct === 100 ? 'healthy' : completionPct > 50 ? 'warning' : 'neutral'} />
      </div>

      {/* Test Case Matrix */}
      <Card>
        <CardTitle className="mb-1">Test Case Matrix</CardTitle>
        <CardDescription className="mb-4">Aggregated results per test case across all runs</CardDescription>
        {matrix.length === 0 ? (
          <div className="text-center py-8 text-goose-text-muted text-sm">No test runs recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-goose-border">
                  <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Test ID</th>
                  <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Runs</th>
                  <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Passed</th>
                  <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">CEP (m)</th>
                  <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Grade</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map(row => (
                  <tr key={row.test_case_id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                    <td className="px-3 py-2 font-mono text-goose-text text-xs">{row.test_case_id}</td>
                    <td className="px-3 py-2 text-right text-goose-text">{row.runs}</td>
                    <td className="px-3 py-2 text-right text-goose-success">{row.passed}</td>
                    <td className="px-3 py-2 text-right font-mono text-goose-text">
                      {row.cep !== null ? row.cep.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={gradeVariant(row.grade)}>{row.grade}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Recent Runs */}
      <Card>
        <CardTitle className="mb-1">Recent Runs</CardTitle>
        <CardDescription className="mb-4">Last {Math.min(runs.length, 20)} runs in this campaign</CardDescription>
        {runs.length === 0 ? (
          <div className="text-center py-8 text-goose-text-muted text-sm">No runs recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-goose-border">
                  <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Run #</th>
                  <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Test Case</th>
                  <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Outcome</th>
                  <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Operator</th>
                  <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Duration</th>
                  <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Started</th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 20).map(run => (
                  <tr key={run.run_id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                    <td className="px-3 py-2 font-mono text-goose-text">#{run.run_number}</td>
                    <td className="px-3 py-2 text-goose-text-secondary text-xs font-mono">{run.test_case_id}</td>
                    <td className="px-3 py-2">
                      <Badge variant={outcomeVariant(run.outcome)}>{run.outcome}</Badge>
                    </td>
                    <td className="px-3 py-2 text-goose-text-secondary">{run.operator || '—'}</td>
                    <td className="px-3 py-2 text-right font-mono text-goose-text-muted text-xs">{durationStr(run)}</td>
                    <td className="px-3 py-2 text-goose-text-muted text-xs">
                      {new Date(run.started_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
