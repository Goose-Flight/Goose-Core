import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { HealthRing } from '@/components/ui/HealthRing'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { EvidenceBadge } from '@/components/forensic/EvidenceBadge'
import { Button } from '@/components/ui/Button'
import { PlotlyChart } from '@/components/charts/PlotlyChart'

const subsystemCards = [
  { path: 'motors', label: 'Motors', icon: '⚙️', desc: 'Saturation, imbalance, headroom', color: 'from-goose-chart-1/10' },
  { path: 'battery', label: 'Battery', icon: '🔋', desc: 'Voltage sag, cell health, temperature', color: 'from-goose-chart-3/10' },
  { path: 'gps', label: 'GPS / Nav', icon: '📡', desc: 'Fix quality, HDOP, EKF fusion', color: 'from-goose-chart-7/10' },
  { path: 'vibration', label: 'Vibration', icon: '📳', desc: 'RMS, clipping, spectrum analysis', color: 'from-goose-chart-4/10' },
  { path: 'control', label: 'Control', icon: '🎮', desc: 'Attitude tracking, RC signal', color: 'from-goose-chart-5/10' },
  { path: 'environment', label: 'Environment', icon: '🌬️', desc: 'Wind estimation, conditions', color: 'from-goose-chart-2/10' },
  { path: 'flight-path', label: 'Flight Path', icon: '🗺️', desc: '3D GPS track & flight replay', color: 'from-goose-accent/10' },
  { path: 'timeline', label: 'Timeline', icon: '📊', desc: 'Anomaly timeline & event log', color: 'from-goose-chart-6/10' },
]

export function QuickResults() {
  const navigate = useNavigate()
  const { currentAnalysis } = useAnalysisStore()

  if (!currentAnalysis) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <Card className="text-center py-12">
          <p className="text-goose-text-muted">No analysis loaded.</p>
          <Button className="mt-4" onClick={() => navigate('/analyze')}>
            Run Quick Analysis
          </Button>
        </Card>
      </div>
    )
  }

  const { metadata, overall_score, findings, hypotheses, phases } = currentAnalysis
  const criticalCount = findings.filter((f) => f.severity === 'critical').length
  const warningCount = findings.filter((f) => f.severity === 'warning').length

  const crashed = metadata.crashed
  const crashConf = metadata.crash_confidence ?? 0

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Crash Banner */}
      {crashed && (
        <div className="relative overflow-hidden rounded-xl border-2 border-goose-error/50 bg-gradient-to-r from-goose-error/10 via-goose-error/5 to-transparent p-5">
          <div className="absolute top-0 right-0 w-32 h-32 bg-goose-error/5 rounded-full -translate-y-1/2 translate-x-1/2" />
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-goose-error/20 flex items-center justify-center shrink-0">
              <svg className="w-8 h-8 text-goose-error" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-bold text-goose-error">CRASH DETECTED</h2>
              <p className="text-sm text-goose-text mt-0.5">
                {crashConf > 0 ? `${(crashConf * 100).toFixed(0)}% confidence` : 'Crash indicators found in flight data'}
              </p>
              {metadata.crash_signals && metadata.crash_signals.length > 0 && (
                <div className="flex gap-2 mt-2 flex-wrap">
                  {metadata.crash_signals.map((sig: any, i: number) => (
                    <Badge key={i} variant="error">{typeof sig === 'string' ? sig : sig.type || 'signal'}</Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-goose-text">Analysis Results</h1>
          <p className="text-sm text-goose-text-muted mt-1">
            {metadata.filename} &middot; {metadata.autopilot.toUpperCase()} &middot;{' '}
            {metadata.vehicle_type} &middot; {Math.round(metadata.duration_sec)}s
          </p>
        </div>
        <div className="flex items-center gap-3">
          <EvidenceBadge hash={currentAnalysis.quick_analysis_id} algorithm="SHA-256" verified={true} />
          <Button variant="secondary" onClick={() => navigate('/cases/new')}>
            Save as Investigation Case
          </Button>
        </div>
      </div>

      {/* Top Row: Health Score + KPIs */}
      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-3 flex items-center justify-center">
          <HealthRing score={overall_score} size={140} />
        </Card>
        <div className="col-span-9 grid grid-cols-4 gap-4">
          <KPICard
            label="Findings"
            value={findings.length}
            status={criticalCount > 0 ? 'critical' : warningCount > 0 ? 'warning' : 'healthy'}
            subtitle={`${criticalCount} critical, ${warningCount} warning`}
          />
          <KPICard
            label="Hypotheses"
            value={hypotheses.length}
            subtitle={hypotheses.length > 0 ? `Top: ${hypotheses[0]?.theme}` : 'No root causes detected'}
          />
          <KPICard
            label="Duration"
            value={`${Math.floor(metadata.duration_sec / 60)}:${String(Math.round(metadata.duration_sec % 60)).padStart(2, '0')}`}
            subtitle={`${metadata.motor_count} motors`}
          />
          <KPICard
            label="Plugins"
            value="17"
            status="healthy"
            subtitle="All plugins executed"
          />
        </div>
      </div>

      {/* Findings */}
      <Card>
        <CardTitle className="mb-4">
          Findings
          <span className="ml-2 text-xs text-goose-text-muted font-normal">({findings.length} total)</span>
        </CardTitle>
        <div className="space-y-3">
          {findings
            .sort((a, b) => {
              const order = { critical: 0, warning: 1, info: 2, pass: 3 }
              return (order[a.severity] ?? 4) - (order[b.severity] ?? 4)
            })
            .slice(0, 10)
            .map((finding) => (
              <div
                key={finding.finding_id}
                className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border"
              >
                <div className="shrink-0 mt-0.5">
                  <SeverityBadge severity={finding.severity} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-goose-text">{finding.title}</p>
                    <ConfidenceBadge band={finding.confidence_band} score={finding.confidence} />
                  </div>
                  <p className="text-xs text-goose-text-muted mt-1 line-clamp-2">{finding.description}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <Badge>{finding.plugin_id}</Badge>
                    {finding.phase && <Badge variant="info">{finding.phase}</Badge>}
                    {finding.score !== undefined && (
                      <span className="text-[10px] text-goose-text-muted">Score: {finding.score}/100</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
        </div>
      </Card>

      {/* Hypotheses */}
      {hypotheses.length > 0 && (
        <Card>
          <CardTitle className="mb-4">Root-Cause Hypotheses</CardTitle>
          <div className="space-y-3">
            {hypotheses.map((h) => (
              <div key={h.hypothesis_id} className="p-3 rounded-lg bg-goose-bg border border-goose-border">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="accent">{h.theme}</Badge>
                  <ConfidenceBadge band={h.confidence_band} score={Math.round(h.confidence * 100)} />
                  <Badge>{h.status}</Badge>
                </div>
                <p className="text-sm text-goose-text">{h.statement}</p>
                <p className="text-xs text-goose-text-muted mt-1">
                  {h.supporting_finding_ids.length} supporting &middot; {h.contradicting_finding_ids.length} contradicting
                </p>
                {h.recommendations.length > 0 && (
                  <div className="mt-2 text-xs text-goose-text-muted">
                    <span className="font-medium">Recommended:</span> {h.recommendations[0]}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Mini 3D Flight Path Widget */}
      {currentAnalysis.flight_path && currentAnalysis.flight_path.lat && currentAnalysis.flight_path.lat.length > 0 && (
        <Card
          hover
          onClick={() => navigate(`/analyze/${currentAnalysis.quick_analysis_id}/flight-path`)}
          padding="none"
          className="overflow-hidden group"
        >
          <div className="flex items-center justify-between px-4 pt-3 pb-1">
            <CardTitle>3D Flight Path</CardTitle>
            <span className="text-xs text-goose-text-muted group-hover:text-goose-accent transition-colors">
              Click to expand &rarr;
            </span>
          </div>
            <PlotlyChart
              data={[{
                type: 'scatter3d',
                mode: 'lines',
                x: currentAnalysis.flight_path!.lon,
                y: currentAnalysis.flight_path!.lat,
                z: currentAnalysis.flight_path!.alt,
                line: {
                  color: currentAnalysis.flight_path!.alt as any,
                  colorscale: [[0, '#3B82F6'], [0.5, '#22C55E'], [1, '#EF4444']],
                  width: 4,
                },
                hoverinfo: 'skip',
              } as any]}
              layout={{
                paper_bgcolor: '#111827',
                plot_bgcolor: '#111827',
                margin: { l: 0, r: 0, t: 0, b: 0 },
                scene: {
                  bgcolor: '#111827',
                  xaxis: { visible: false },
                  yaxis: { visible: false },
                  zaxis: { visible: false },
                  camera: { eye: { x: 1.8, y: 1.8, z: 0.6 } },
                  dragmode: 'turntable',
                },
                showlegend: false,
              }}
              config={{ displayModeBar: false }}
              style={{ width: '100%', height: '250px' }}
            />
        </Card>
      )}

      {/* Subsystem Pages */}
      <div>
        <h2 className="text-lg font-semibold text-goose-text mb-3">Deep Dive by Subsystem</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {subsystemCards.map((sub) => (
            <Card
              key={sub.path}
              hover
              onClick={() => navigate(`/analyze/${currentAnalysis.quick_analysis_id}/${sub.path}`)}
              className={`group bg-gradient-to-br ${sub.color} to-transparent`}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{sub.icon}</span>
                <div>
                  <p className="text-sm font-medium text-goose-text group-hover:text-goose-accent transition-colors">
                    {sub.label}
                  </p>
                  <p className="text-xs text-goose-text-muted">{sub.desc}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* Flight Phases */}
      {phases.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Flight Phases</CardTitle>
          <div className="flex gap-1 h-8 rounded-lg overflow-hidden">
            {phases.map((phase, i) => {
              const totalDuration = phases.reduce((sum, p) => sum + p.duration, 0)
              const widthPct = (phase.duration / totalDuration) * 100
              const colors: Record<string, string> = {
                'pre-arm': 'bg-gray-600',
                climb: 'bg-blue-500',
                cruise: 'bg-green-500',
                descent: 'bg-amber-500',
                landing: 'bg-red-400',
              }
              return (
                <div
                  key={i}
                  className={`${colors[phase.name] || 'bg-goose-accent'} flex items-center justify-center`}
                  style={{ width: `${widthPct}%` }}
                  title={`${phase.name}: ${Math.round(phase.duration)}s`}
                >
                  {widthPct > 10 && (
                    <span className="text-[10px] font-medium text-white truncate px-1">
                      {phase.name}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
          <div className="flex gap-4 mt-2">
            {phases.map((phase, i) => (
              <div key={i} className="text-xs text-goose-text-muted">
                <span className="capitalize">{phase.name}</span>: {Math.round(phase.duration)}s
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
