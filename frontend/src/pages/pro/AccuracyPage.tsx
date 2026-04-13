import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import Plot from 'react-plotly.js'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { KPICard } from '@/components/ui/KPICard'
import { Button } from '@/components/ui/Button'
import { ProBadge } from '@/components/ui/Badge'
import { proApi } from '@/lib/proApi'
import type { TestRun } from '@/lib/proTypes'

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-6 w-6 text-goose-accent" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function gradeVariant(grade: string) {
  switch (grade) {
    case 'PASS': return 'success' as const
    case 'FAIL': return 'error' as const
    case 'MARGINAL': return 'warning' as const
    default: return 'default' as const
  }
}

function gradeFromCep(cep: number | null): string {
  if (cep === null) return 'PENDING'
  if (cep <= 5) return 'PASS'
  if (cep <= 15) return 'MARGINAL'
  return 'FAIL'
}

interface RunMetrics {
  run: TestRun
  cep: number | null
  r95: number | null
  drift: number | null
  grade: string
}

function extractMetrics(runs: TestRun[]): RunMetrics[] {
  return runs.map(run => {
    const m = run.metrics_json ?? {}
    const cep = (m.cep_m as number) ?? null
    const r95 = (m.r95_m as number) ?? null
    const drift = (m.drift_rate_ms as number) ?? null
    return { run, cep, r95, drift, grade: gradeFromCep(cep) }
  })
}

const GRADE_COLORS: Record<string, string> = {
  PASS: '#22C55E',
  MARGINAL: '#F59E0B',
  FAIL: '#EF4444',
  PENDING: '#64748B',
}

export function AccuracyPage() {
  const { campaignId } = useParams<{ campaignId: string }>()
  const navigate = useNavigate()
  const [runs, setRuns] = useState<TestRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    proApi.get<TestRun[]>(`/api/campaigns/${campaignId}/runs`)
      .then(data => { if (!cancelled) setRuns(data) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load runs') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [campaignId])

  const metrics = extractMetrics(runs)
  const cepValues = metrics.map(m => m.cep).filter((v): v is number => v !== null)
  const r95Values = metrics.map(m => m.r95).filter((v): v is number => v !== null)
  const driftValues = metrics.map(m => m.drift).filter((v): v is number => v !== null)

  const meanCep = cepValues.length ? (cepValues.reduce((a, b) => a + b, 0) / cepValues.length) : null
  const meanR95 = r95Values.length ? (r95Values.reduce((a, b) => a + b, 0) / r95Values.length) : null
  const bestCep = cepValues.length ? Math.min(...cepValues) : null
  const meanDrift = driftValues.length ? (driftValues.reduce((a, b) => a + b, 0) / driftValues.length) : null

  const hasMetrics = cepValues.length > 0

  const plotData: Plotly.Data[] = metrics.map((m, i) => ({
    x: [`Run #${m.run.run_number}`],
    y: [m.cep ?? 0],
    type: 'bar' as const,
    name: `Run #${m.run.run_number}`,
    marker: { color: GRADE_COLORS[m.grade] },
    showlegend: false,
    hovertemplate: `Run #${m.run.run_number}<br>CEP: ${m.cep !== null ? m.cep.toFixed(2) + ' m' : 'N/A'}<br>Grade: ${m.grade}<extra></extra>`,
  }))

  const plotLayout: Partial<Plotly.Layout> = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#94A3B8', size: 11 },
    margin: { t: 20, r: 20, b: 40, l: 50 },
    xaxis: { gridcolor: '#1E293B', tickfont: { color: '#64748B', size: 10 } },
    yaxis: { gridcolor: '#1E293B', title: { text: 'CEP (m)' }, tickfont: { color: '#64748B', size: 10 } },
    bargap: 0.2,
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(`/pro/campaigns/${campaignId}`)} className="mb-2">
            &larr; Back to Campaign
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            Accuracy Analysis <ProBadge />
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">CEP, R95, and drift metrics across all runs</p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner />
        </div>
      )}

      {!loading && (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              label="Mean CEP"
              value={meanCep !== null ? meanCep.toFixed(2) : '—'}
              unit={meanCep !== null ? 'm' : ''}
              status={meanCep === null ? 'neutral' : meanCep <= 5 ? 'healthy' : meanCep <= 15 ? 'warning' : 'critical'}
            />
            <KPICard
              label="Mean R95"
              value={meanR95 !== null ? meanR95.toFixed(2) : '—'}
              unit={meanR95 !== null ? 'm' : ''}
            />
            <KPICard
              label="Best Run CEP"
              value={bestCep !== null ? bestCep.toFixed(2) : '—'}
              unit={bestCep !== null ? 'm' : ''}
              status={bestCep === null ? 'neutral' : bestCep <= 5 ? 'healthy' : 'warning'}
            />
            <KPICard
              label="Mean Drift Rate"
              value={meanDrift !== null ? meanDrift.toFixed(3) : '—'}
              unit={meanDrift !== null ? 'm/s' : ''}
              status={meanDrift === null ? 'neutral' : meanDrift < 0.5 ? 'healthy' : meanDrift < 2 ? 'warning' : 'critical'}
            />
          </div>

          {/* Empty state */}
          {!hasMetrics && (
            <div className="text-center py-16 text-goose-text-muted">
              <p className="text-lg font-medium text-goose-text">No Accuracy Metrics Yet</p>
              <p className="text-sm mt-2">Run analysis to see accuracy metrics.</p>
            </div>
          )}

          {/* CEP chart */}
          {hasMetrics && (
            <Card>
              <CardTitle className="mb-1">CEP Over Runs</CardTitle>
              <CardDescription className="mb-4">Circular Error Probable per run — green = pass, amber = marginal, red = fail</CardDescription>
              <Plot
                data={plotData}
                layout={plotLayout}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%', height: '280px' }}
              />
            </Card>
          )}

          {/* Per-run table */}
          {runs.length > 0 && (
            <Card>
              <CardTitle className="mb-4">Per-Run Accuracy Table</CardTitle>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-goose-border">
                      <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Run #</th>
                      <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Test Case</th>
                      <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">CEP (m)</th>
                      <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">R95 (m)</th>
                      <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Drift (m/s)</th>
                      <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Grade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.map(({ run, cep, r95, drift, grade }) => (
                      <tr key={run.run_id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                        <td className="px-3 py-2 font-mono text-goose-text">#{run.run_number}</td>
                        <td className="px-3 py-2 text-goose-text-secondary text-xs font-mono">{run.test_case_id}</td>
                        <td className="px-3 py-2 text-right font-mono text-goose-text">{cep !== null ? cep.toFixed(2) : '—'}</td>
                        <td className="px-3 py-2 text-right font-mono text-goose-text">{r95 !== null ? r95.toFixed(2) : '—'}</td>
                        <td className="px-3 py-2 text-right font-mono text-goose-text">{drift !== null ? drift.toFixed(3) : '—'}</td>
                        <td className="px-3 py-2">
                          <Badge variant={gradeVariant(grade)}>{grade}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
