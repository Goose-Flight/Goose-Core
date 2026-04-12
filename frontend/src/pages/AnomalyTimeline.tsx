import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle } from '@/components/ui/Card'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { KPICard } from '@/components/ui/KPICard'
import { formatDuration } from '@/lib/streams'
import type { Finding, TimelineEvent } from '@/lib/types'

export function AnomalyTimeline() {
  const navigate = useNavigate()
  const { currentAnalysis } = useAnalysisStore()
  const [severityFilter, setSeverityFilter] = useState<string | null>(null)
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (!currentAnalysis) {
    return (
      <div className="p-6">
        <Button variant="secondary" onClick={() => navigate('/analyze')}>Run Analysis First</Button>
      </div>
    )
  }

  const { findings, timeline, phases, metadata } = currentAnalysis

  // Build unified timeline from findings + events
  const allEvents = [
    ...findings.map((f) => ({
      id: f.finding_id,
      time: f.start_time || 0,
      endTime: f.end_time,
      severity: f.severity,
      category: f.plugin_id.replace(/_/g, ' '),
      title: f.title,
      description: f.description,
      confidence: f.confidence,
      confidenceBand: f.confidence_band,
      type: 'finding' as const,
      plugin: f.plugin_id,
      evidence: f.supporting_metrics,
    })),
    ...timeline.map((t, i) => ({
      id: `evt-${i}`,
      time: t.timestamp,
      endTime: null as number | null,
      severity: t.severity,
      category: t.category || 'system',
      title: t.message,
      description: '',
      confidence: null as number | null,
      confidenceBand: null as string | null,
      type: 'event' as const,
      plugin: t.plugin_id || '',
      evidence: {} as Record<string, unknown>,
    })),
  ].sort((a, b) => a.time - b.time)

  // Category counts
  const categories = [...new Set(allEvents.map(e => e.category))]
  const severities = ['critical', 'warning', 'info', 'pass'] as const
  const severityCounts = Object.fromEntries(severities.map(s => [s, allEvents.filter(e => e.severity === s).length]))

  // Apply filters
  const filtered = allEvents.filter((e) => {
    if (severityFilter && e.severity !== severityFilter) return false
    if (categoryFilter && e.category !== categoryFilter) return false
    return true
  })

  // Phase lookup
  const getPhaseAt = (time: number) => {
    return phases.find(p => time >= p.start_time && time <= p.end_time)
  }

  // Severity dot colors
  const sevDot: Record<string, string> = {
    critical: 'bg-goose-severity-critical',
    warning: 'bg-goose-severity-warning',
    info: 'bg-goose-severity-info',
    pass: 'bg-goose-severity-pass',
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
            &larr; Back to Results
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            <span className="text-3xl">📊</span> Anomaly Timeline
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            {allEvents.length} events across {formatDuration(metadata.duration_sec)} flight
          </p>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KPICard label="Total Events" value={allEvents.length} status="neutral" />
        <KPICard label="Critical" value={severityCounts.critical} status={severityCounts.critical > 0 ? 'critical' : 'healthy'} />
        <KPICard label="Warnings" value={severityCounts.warning} status={severityCounts.warning > 0 ? 'warning' : 'healthy'} />
        <KPICard label="Info" value={severityCounts.info} status="neutral" />
        <KPICard label="Categories" value={categories.length} subtitle="Unique sources" />
      </div>

      {/* Phase Bar with event markers */}
      {phases.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Event Distribution by Phase</CardTitle>
          <div className="relative">
            {/* Phase bar */}
            <div className="flex gap-0.5 h-10 rounded-lg overflow-hidden">
              {phases.map((phase, i) => {
                const total = phases.reduce((s, p) => s + p.duration, 0)
                const pct = (phase.duration / total) * 100
                const eventsInPhase = allEvents.filter(e => e.time >= phase.start_time && e.time <= phase.end_time)
                const hasCritical = eventsInPhase.some(e => e.severity === 'critical')
                const hasWarning = eventsInPhase.some(e => e.severity === 'warning')
                const phaseColors: Record<string, string> = {
                  'pre-arm': 'bg-gray-600', takeoff: 'bg-blue-500', climb: 'bg-blue-500',
                  cruise: 'bg-green-500', mission: 'bg-green-500', descent: 'bg-amber-500',
                  landing: 'bg-red-400', hover: 'bg-cyan-500',
                }
                return (
                  <div
                    key={i}
                    className={`${phaseColors[phase.name] || 'bg-goose-accent'} relative flex items-center justify-center ${hasCritical ? 'ring-2 ring-goose-error ring-inset' : hasWarning ? 'ring-1 ring-goose-warning ring-inset' : ''}`}
                    style={{ width: `${pct}%` }}
                    title={`${phase.name}: ${eventsInPhase.length} events`}
                  >
                    {pct > 8 && (
                      <div className="text-center">
                        <div className="text-[10px] font-medium text-white truncate px-1">{phase.name}</div>
                        {eventsInPhase.length > 0 && (
                          <div className="text-[9px] text-white/70">{eventsInPhase.length} events</div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </Card>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {/* Severity filters */}
        <button
          onClick={() => setSeverityFilter(null)}
          className={`px-3 py-1.5 rounded-full text-xs font-medium border cursor-pointer transition-colors ${!severityFilter ? 'bg-goose-accent text-white border-goose-accent' : 'border-goose-border text-goose-text-muted hover:text-goose-text'}`}
        >
          All ({allEvents.length})
        </button>
        {severities.filter(s => severityCounts[s] > 0).map((sev) => (
          <button
            key={sev}
            onClick={() => setSeverityFilter(severityFilter === sev ? null : sev)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border cursor-pointer transition-colors ${severityFilter === sev ? 'bg-goose-accent text-white border-goose-accent' : 'border-goose-border text-goose-text-muted hover:text-goose-text'}`}
          >
            <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${sevDot[sev]}`} />
            {sev.charAt(0).toUpperCase() + sev.slice(1)} ({severityCounts[sev]})
          </button>
        ))}

        <span className="w-px h-6 bg-goose-border self-center mx-1" />

        {/* Category filters */}
        {categories.slice(0, 8).map((cat) => {
          const count = allEvents.filter(e => e.category === cat).length
          return (
            <button
              key={cat}
              onClick={() => setCategoryFilter(categoryFilter === cat ? null : cat)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border cursor-pointer transition-colors ${categoryFilter === cat ? 'bg-goose-info text-white border-goose-info' : 'border-goose-border text-goose-text-muted hover:text-goose-text'}`}
            >
              {cat} ({count})
            </button>
          )
        })}
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-6 top-0 bottom-0 w-px bg-goose-border" />

        <div className="space-y-1">
          {filtered.map((event) => {
            const phase = getPhaseAt(event.time)
            const isExpanded = expandedId === event.id

            return (
              <div
                key={event.id}
                className="relative pl-14 group"
              >
                {/* Timeline dot */}
                <div className={`absolute left-[18px] top-3.5 w-3.5 h-3.5 rounded-full border-2 border-goose-surface ${sevDot[event.severity]} z-10`} />

                {/* Event card */}
                <div
                  onClick={() => setExpandedId(isExpanded ? null : event.id)}
                  className={`
                    p-3 rounded-lg border transition-all cursor-pointer
                    ${isExpanded ? 'bg-goose-surface border-goose-border-subtle' : 'bg-goose-bg border-goose-border hover:border-goose-border-subtle'}
                  `}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-mono text-goose-text-muted">
                          {formatDuration(event.time)}
                        </span>
                        <SeverityBadge severity={event.severity} />
                        <Badge variant="info">{event.category}</Badge>
                        {phase && <Badge>{phase.name}</Badge>}
                      </div>
                      <p className="text-sm text-goose-text mt-1.5">{event.title}</p>
                    </div>
                    {event.confidence != null && (
                      <ConfidenceBadge band={event.confidenceBand as any} score={event.confidence} />
                    )}
                  </div>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-goose-border space-y-2">
                      {event.description && (
                        <p className="text-xs text-goose-text-muted">{event.description}</p>
                      )}
                      {event.plugin && (
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-goose-text-muted">Plugin:</span>
                          <Badge>{event.plugin}</Badge>
                        </div>
                      )}
                      {event.endTime && (
                        <div className="text-[10px] text-goose-text-muted">
                          Duration: {formatDuration(event.endTime - event.time)} ({formatDuration(event.time)} — {formatDuration(event.endTime)})
                        </div>
                      )}
                      {Object.keys(event.evidence).length > 0 && (
                        <div className="mt-2">
                          <span className="text-[10px] text-goose-text-muted font-semibold">Evidence:</span>
                          <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] font-mono bg-goose-bg rounded-lg p-2 border border-goose-border">
                            {Object.entries(event.evidence).slice(0, 10).map(([k, v]) => (
                              <div key={k} className="flex justify-between gap-2">
                                <span className="text-goose-text-muted truncate">{k}:</span>
                                <span className="text-goose-text">{typeof v === 'number' ? (v as number).toFixed(2) : String(v)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {filtered.length === 0 && (
          <Card className="ml-14 py-8 text-center text-goose-text-muted text-sm">
            No events match the selected filters
          </Card>
        )}
      </div>
    </div>
  )
}
