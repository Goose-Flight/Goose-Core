import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
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

interface DenialEvent {
  event_number: number
  onset_time_s: number
  duration_s: number
  drift_rate_ms: number
  recovery_jump_m: number
}

interface RunDenialData {
  run: TestRun
  events: DenialEvent[]
}

function extractDenialEvents(run: TestRun): DenialEvent[] {
  const raw = run.metrics_json?.denial_events
  if (!Array.isArray(raw)) return []
  return (raw as Record<string, unknown>[]).map((e, i) => ({
    event_number: typeof e.event_number === 'number' ? e.event_number : i + 1,
    onset_time_s: typeof e.onset_time_s === 'number' ? e.onset_time_s : 0,
    duration_s: typeof e.duration_s === 'number' ? e.duration_s : 0,
    drift_rate_ms: typeof e.drift_rate_ms === 'number' ? e.drift_rate_ms : 0,
    recovery_jump_m: typeof e.recovery_jump_m === 'number' ? e.recovery_jump_m : 0,
  }))
}

function driftVariant(rate: number) {
  if (rate > 2) return 'error' as const
  if (rate >= 0.5) return 'warning' as const
  return 'success' as const
}

export function GPSDenialPage() {
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

  const runData: RunDenialData[] = runs.map(run => ({
    run,
    events: extractDenialEvents(run),
  })).filter(rd => rd.events.length > 0)

  const allEvents = runData.flatMap(rd => rd.events)
  const totalEvents = allEvents.length
  const meanDuration = totalEvents > 0
    ? allEvents.reduce((s, e) => s + e.duration_s, 0) / totalEvents
    : null
  const meanDrift = totalEvents > 0
    ? allEvents.reduce((s, e) => s + e.drift_rate_ms, 0) / totalEvents
    : null

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(`/pro/campaigns/${campaignId}`)} className="mb-2">
            &larr; Back to Campaign
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            GPS Denial Analysis <ProBadge />
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">Denial events, drift rates, and recovery behaviour</p>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner />
        </div>
      )}

      {!loading && (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KPICard label="Total Denial Events" value={totalEvents} />
            <KPICard
              label="Mean Duration"
              value={meanDuration !== null ? meanDuration.toFixed(1) : '—'}
              unit={meanDuration !== null ? 's' : ''}
            />
            <KPICard
              label="Mean Drift During Denial"
              value={meanDrift !== null ? meanDrift.toFixed(3) : '—'}
              unit={meanDrift !== null ? 'm/s' : ''}
              status={meanDrift === null ? 'neutral' : meanDrift < 0.5 ? 'healthy' : meanDrift < 2 ? 'warning' : 'critical'}
            />
          </div>

          {/* Empty state */}
          {runData.length === 0 && (
            <Card className="py-16 text-center">
              <p className="text-lg font-medium text-goose-text">No GPS Denial Data</p>
              <p className="text-sm text-goose-text-muted mt-2 max-w-md mx-auto">
                No denial events found in run metrics. Denial event data is populated when runs include
                denial scenario metrics in their metrics_json.
              </p>
            </Card>
          )}

          {/* Per-run event tables */}
          {runData.map(({ run, events }) => (
            <Card key={run.run_id}>
              <CardTitle className="mb-1">
                Run #{run.run_number}
                <span className="ml-2 text-xs font-normal text-goose-text-muted">{run.test_case_id}</span>
              </CardTitle>
              <CardDescription className="mb-4">{events.length} denial event{events.length !== 1 ? 's' : ''}</CardDescription>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-goose-border">
                      <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Event #</th>
                      <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Onset (s)</th>
                      <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Duration (s)</th>
                      <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Drift Rate (m/s)</th>
                      <th className="text-right px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Recovery Jump (m)</th>
                      <th className="text-left px-3 py-2 text-xs text-goose-text-muted uppercase tracking-wide">Severity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map(ev => (
                      <tr key={ev.event_number} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                        <td className="px-3 py-2 font-mono text-goose-text">{ev.event_number}</td>
                        <td className="px-3 py-2 text-right font-mono text-goose-text">{ev.onset_time_s.toFixed(1)}</td>
                        <td className="px-3 py-2 text-right font-mono text-goose-text">{ev.duration_s.toFixed(1)}</td>
                        <td className="px-3 py-2 text-right font-mono">
                          <span className={
                            ev.drift_rate_ms > 2 ? 'text-goose-error' :
                            ev.drift_rate_ms >= 0.5 ? 'text-goose-warning' :
                            'text-goose-success'
                          }>
                            {ev.drift_rate_ms.toFixed(3)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-goose-text">{ev.recovery_jump_m.toFixed(2)}</td>
                        <td className="px-3 py-2">
                          <Badge variant={driftVariant(ev.drift_rate_ms)}>
                            {ev.drift_rate_ms > 2 ? 'HIGH' : ev.drift_rate_ms >= 0.5 ? 'MEDIUM' : 'LOW'}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </>
      )}
    </div>
  )
}
