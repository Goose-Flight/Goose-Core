import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import Plot from 'react-plotly.js'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
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

interface TrajectoryPoint { x: number; y: number; z: number }

function extractTrajectory(key: string, metrics: Record<string, unknown>): TrajectoryPoint[] | null {
  const raw = metrics[key]
  if (!Array.isArray(raw)) return null
  return (raw as { x: number; y: number; z: number }[]).filter(
    p => typeof p.x === 'number' && typeof p.y === 'number' && typeof p.z === 'number'
  )
}

export function TrajectoryPage() {
  const { campaignId } = useParams<{ campaignId: string }>()
  const navigate = useNavigate()
  const [runs, setRuns] = useState<TestRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string>('')

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    proApi.get<TestRun[]>(`/api/campaigns/${campaignId}/runs`)
      .then(data => {
        if (!cancelled) {
          setRuns(data)
          if (data.length > 0) setSelectedRunId(data[0].run_id)
        }
      })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load runs') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [campaignId])

  const selectedRun = runs.find(r => r.run_id === selectedRunId) ?? null
  const metrics = selectedRun?.metrics_json ?? {}

  const navTraj = extractTrajectory('nav_trajectory', metrics)
  const gtTraj = extractTrajectory('ground_truth_trajectory', metrics)
  const hasGroundTruth = gtTraj !== null && gtTraj.length > 0
  const hasNav = navTraj !== null && navTraj.length > 0

  const crossTrackError = metrics.cross_track_error_m as number | undefined
  const alongTrackError = metrics.along_track_error_m as number | undefined
  const maxDeviation = metrics.max_deviation_m as number | undefined
  const rmsError = metrics.rms_error_m as number | undefined

  const plotData: Plotly.Data[] = []

  if (hasNav) {
    const errorMag = (navTraj as TrajectoryPoint[]).map((_, i) => {
      if (!hasGroundTruth || !gtTraj![i]) return 0
      const gt = gtTraj![i]
      const nav = (navTraj as TrajectoryPoint[])[i]
      return Math.sqrt((nav.x - gt.x) ** 2 + (nav.y - gt.y) ** 2 + (nav.z - gt.z) ** 2)
    })
    const maxErr = Math.max(...errorMag, 1)

    plotData.push({
      type: 'scatter3d' as const,
      name: 'Nav Solution',
      x: (navTraj as TrajectoryPoint[]).map(p => p.x),
      y: (navTraj as TrajectoryPoint[]).map(p => p.y),
      z: (navTraj as TrajectoryPoint[]).map(p => p.z),
      mode: 'lines',
      line: {
        color: hasGroundTruth ? errorMag : '#14B8A6',
        colorscale: hasGroundTruth ? 'RdYlGn' : undefined,
        reversescale: true,
        cmin: 0,
        cmax: maxErr,
        width: 3,
      },
    } as Plotly.Data)
  }

  if (hasGroundTruth) {
    plotData.push({
      type: 'scatter3d' as const,
      name: 'Ground Truth',
      x: (gtTraj as TrajectoryPoint[]).map(p => p.x),
      y: (gtTraj as TrajectoryPoint[]).map(p => p.y),
      z: (gtTraj as TrajectoryPoint[]).map(p => p.z),
      mode: 'lines',
      line: { color: '#22C55E', width: 2, dash: 'dash' },
    } as Plotly.Data)
  }

  const plotLayout: Partial<Plotly.Layout> = {
    paper_bgcolor: 'transparent',
    scene: {
      bgcolor: '#0B1120',
      xaxis: { gridcolor: '#1E293B', title: { text: 'X (m)' }, color: '#64748B' },
      yaxis: { gridcolor: '#1E293B', title: { text: 'Y (m)' }, color: '#64748B' },
      zaxis: { gridcolor: '#1E293B', title: { text: 'Z (m)' }, color: '#64748B' },
    },
    font: { color: '#94A3B8', size: 11 },
    margin: { t: 20, r: 20, b: 20, l: 20 },
    legend: { font: { color: '#94A3B8', size: 11 }, bgcolor: 'transparent' },
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
            Trajectory Comparison <ProBadge />
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">Nav solution vs ground truth — 3D track overlay</p>
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
          {/* Run selector */}
          {runs.length > 0 && (
            <Card>
              <label className="text-xs text-goose-text-muted block mb-2">Select Run</label>
              <select
                value={selectedRunId}
                onChange={e => setSelectedRunId(e.target.value)}
                className="w-full md:w-64 bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text focus:outline-none focus:border-goose-accent"
              >
                {runs.map(r => (
                  <option key={r.run_id} value={r.run_id}>
                    Run #{r.run_number} — {r.test_case_id} ({r.outcome})
                  </option>
                ))}
              </select>
            </Card>
          )}

          {/* Empty — no runs */}
          {runs.length === 0 && (
            <div className="text-center py-16 text-goose-text-muted">
              <p className="text-lg font-medium text-goose-text">No Runs Available</p>
              <p className="text-sm mt-2">Add test runs to this campaign first.</p>
            </div>
          )}

          {/* No ground truth info card */}
          {runs.length > 0 && !hasGroundTruth && (
            <Card className="border-goose-info/30 bg-goose-info/5">
              <div className="flex items-start gap-3">
                <svg className="w-5 h-5 text-goose-info shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <p className="text-sm font-medium text-goose-info">No Ground Truth Data</p>
                  <p className="text-xs text-goose-text-muted mt-1">
                    Upload ground truth data to enable trajectory comparison. Ground truth can be loaded via the
                    goose-pro-server ground truth API.
                  </p>
                </div>
              </div>
            </Card>
          )}

          {/* 3D Plot */}
          {(hasNav || hasGroundTruth) && (
            <Card>
              <CardTitle className="mb-1">3D Trajectory</CardTitle>
              <CardDescription className="mb-4">
                {hasGroundTruth
                  ? 'Nav solution colored by error magnitude vs ground truth (green = low error, red = high error)'
                  : 'Nav solution trajectory (no ground truth loaded for comparison)'}
              </CardDescription>
              <Plot
                data={plotData}
                layout={plotLayout}
                config={{ displayModeBar: true, responsive: true }}
                style={{ width: '100%', height: '480px' }}
              />
            </Card>
          )}

          {/* Error stats */}
          {selectedRun && (crossTrackError !== undefined || alongTrackError !== undefined) && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <KPICard
                  label="Cross-Track Error"
                  value={crossTrackError !== undefined ? crossTrackError.toFixed(2) : '—'}
                  unit={crossTrackError !== undefined ? 'm' : ''}
                  status={crossTrackError === undefined ? 'neutral' : crossTrackError <= 5 ? 'healthy' : crossTrackError <= 15 ? 'warning' : 'critical'}
                />
                <KPICard
                  label="Along-Track Error"
                  value={alongTrackError !== undefined ? alongTrackError.toFixed(2) : '—'}
                  unit={alongTrackError !== undefined ? 'm' : ''}
                />
                <KPICard
                  label="Max Deviation"
                  value={maxDeviation !== undefined ? maxDeviation.toFixed(2) : '—'}
                  unit={maxDeviation !== undefined ? 'm' : ''}
                  status={maxDeviation === undefined ? 'neutral' : maxDeviation <= 10 ? 'healthy' : 'warning'}
                />
                <KPICard
                  label="RMS Error"
                  value={rmsError !== undefined ? rmsError.toFixed(2) : '—'}
                  unit={rmsError !== undefined ? 'm' : ''}
                />
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
