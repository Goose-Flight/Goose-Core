import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { KPICard } from '@/components/ui/KPICard'
import { getRecentRuns, getCases } from '@/lib/api'

interface DashboardStats {
  totalRuns: number
  openCases: number
  recentRuns: Array<{
    quick_analysis_id?: string
    filename?: string
    overall_score?: number
    crashed?: boolean
    duration_sec?: number
    created_at?: string
    [key: string]: unknown
  }>
}

export function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats>({
    totalRuns: 0,
    openCases: 0,
    recentRuns: [],
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function loadStats() {
      const result: DashboardStats = { totalRuns: 0, openCases: 0, recentRuns: [] }

      try {
        const runs = await getRecentRuns()
        if (!cancelled && Array.isArray(runs)) {
          result.totalRuns = runs.length
          result.recentRuns = runs.slice(0, 5) as DashboardStats['recentRuns']
        }
      } catch {
        // API unavailable — keep defaults
      }

      try {
        const cases = await getCases()
        if (!cancelled && Array.isArray(cases)) {
          result.openCases = cases.filter((c: any) => c.status === 'open' || c.status === 'active').length || cases.length
        }
      } catch {
        // API unavailable — keep defaults
      }

      if (!cancelled) {
        setStats(result)
        setLoading(false)
      }
    }

    loadStats()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-goose-text">Welcome to Goose</h1>
        <p className="text-sm text-goose-text-muted mt-1">
          Flight forensic analysis platform &mdash; drop a log, find the truth.
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card hover onClick={() => navigate('/analyze')} className="group bg-gradient-to-br from-goose-accent/5 to-transparent border-goose-accent/20">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-goose-accent/20 to-goose-accent/5 flex items-center justify-center shrink-0 group-hover:from-goose-accent/30 transition-colors">
              <svg className="w-7 h-7 text-goose-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <CardTitle className="text-goose-accent">Quick Analysis</CardTitle>
              <CardDescription className="mt-1">
                Drop a flight log for instant analysis. No case needed &mdash; results in seconds.
              </CardDescription>
            </div>
          </div>
        </Card>

        <Card hover onClick={() => navigate('/cases/new')} className="group bg-gradient-to-br from-goose-info/5 to-transparent border-goose-info/20">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-goose-info/20 to-goose-info/5 flex items-center justify-center shrink-0 group-hover:from-goose-info/30 transition-colors">
              <svg className="w-7 h-7 text-goose-info" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <CardTitle className="text-goose-info">New Investigation</CardTitle>
              <CardDescription className="mt-1">
                Open a forensic case with evidence chain, audit trail, and full hypothesis engine.
              </CardDescription>
            </div>
          </div>
        </Card>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Total Analyses"
          value={loading ? '...' : String(stats.totalRuns)}
          subtitle={stats.totalRuns > 0 ? `${stats.totalRuns} run${stats.totalRuns > 1 ? 's' : ''} on record` : 'Run your first analysis'}
        />
        <KPICard
          label="Open Cases"
          value={loading ? '...' : String(stats.openCases)}
          subtitle={stats.openCases > 0 ? `${stats.openCases} active investigation${stats.openCases > 1 ? 's' : ''}` : 'No active investigations'}
        />
        <KPICard label="Drone Fleet" value="0" subtitle="Add your first drone" />
        <KPICard label="Plugins" value="17" subtitle="11 Core + 6 Pro" status="healthy" />
      </div>

      {/* Recent Analyses */}
      {stats.recentRuns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Recent Analyses</CardTitle>
          </CardHeader>
          <div className="space-y-2 mt-2">
            {stats.recentRuns.map((run, i) => {
              const filename = (run.filename as string) || 'Unknown file'
              const score = typeof run.overall_score === 'number' ? run.overall_score : null
              const crashed = !!run.crashed
              const duration = typeof run.duration_sec === 'number' ? run.duration_sec : null
              return (
                <div
                  key={run.quick_analysis_id || i}
                  className="flex items-center justify-between p-3 rounded-lg bg-goose-bg border border-goose-border hover:border-goose-accent/30 transition-colors cursor-pointer"
                  onClick={() => run.quick_analysis_id && navigate(`/analyze/${run.quick_analysis_id}`)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-2 h-2 rounded-full shrink-0 ${crashed ? 'bg-goose-error' : score !== null && score < 50 ? 'bg-goose-warning' : 'bg-goose-success'}`} />
                    <div className="min-w-0">
                      <p className="text-sm text-goose-text truncate">{filename}</p>
                      <p className="text-xs text-goose-text-muted">
                        {duration !== null ? `${Math.floor(duration / 60)}m ${Math.round(duration % 60)}s flight` : 'Duration unknown'}
                        {crashed && <span className="text-goose-error ml-2">CRASH</span>}
                      </p>
                    </div>
                  </div>
                  {score !== null && (
                    <div className={`text-sm font-bold ${score >= 70 ? 'text-goose-success' : score >= 40 ? 'text-goose-warning' : 'text-goose-error'}`}>
                      {score}/100
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* How It Works */}
      <Card>
        <CardHeader>
          <CardTitle>How Goose Works</CardTitle>
        </CardHeader>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-2">
          {[
            { step: '1', title: 'Tell Us About the Flight', desc: 'Select your drone, describe what happened' },
            { step: '2', title: 'Drop the Log', desc: 'Upload .ulg, .bin, .log, or .csv files' },
            { step: '3', title: '17 Plugins Analyze', desc: 'Motors, battery, GPS, vibration, crash detection & more' },
            { step: '4', title: 'Review Findings', desc: 'Evidence-backed findings with confidence scores' },
          ].map((item) => (
            <div key={item.step} className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-goose-accent/20 flex items-center justify-center shrink-0">
                <span className="text-sm font-bold text-goose-accent">{item.step}</span>
              </div>
              <div>
                <p className="text-sm font-medium text-goose-text">{item.title}</p>
                <p className="text-xs text-goose-text-muted mt-0.5">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Forensic Differentiators */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { icon: '🔒', title: 'Evidence Integrity', desc: 'SHA-256/512 hashing on ingest. Chain of custody built in.', gradient: 'from-goose-success/8' },
          { icon: '🧠', title: 'Hypothesis Engine', desc: 'Auto-generated root-cause candidates with confidence scoring.', gradient: 'from-goose-chart-5/8' },
          { icon: '🔌', title: 'Fully Local', desc: 'No data leaves your machine. Air-gapped mode for sensitive operations.', gradient: 'from-goose-accent/8' },
        ].map((item) => (
          <Card key={item.title} className={`bg-gradient-to-br ${item.gradient} to-transparent`}>
            <div className="flex items-start gap-3">
              <span className="text-2xl">{item.icon}</span>
              <div>
                <p className="text-sm font-medium text-goose-text">{item.title}</p>
                <p className="text-xs text-goose-text-muted mt-1">{item.desc}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
