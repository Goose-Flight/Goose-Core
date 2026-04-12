import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Tabs } from '@/components/ui/Tabs'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TimeSeriesChart, CHART_COLORS } from '@/components/charts/TimeSeriesChart'
import { buildChartData, findingsByPlugin, worstSeverity, avg, max, stdDev } from '@/lib/streams'

const MOTOR_COLORS = [
  CHART_COLORS.motor1, CHART_COLORS.motor2, CHART_COLORS.motor3, CHART_COLORS.motor4,
  CHART_COLORS.motor5, CHART_COLORS.motor6, CHART_COLORS.motor7, CHART_COLORS.motor8,
]

export function MotorAnalysis() {
  const navigate = useNavigate()
  const { currentAnalysis } = useAnalysisStore()
  const [visibleMotors, setVisibleMotors] = useState<Set<number>>(new Set([0, 1, 2, 3, 4, 5, 6, 7]))

  if (!currentAnalysis) {
    return (
      <div className="p-6">
        <Button variant="secondary" onClick={() => navigate('/analyze')}>Run Analysis First</Button>
      </div>
    )
  }

  const { timeseries, findings, metadata } = currentAnalysis
  const motorFindings = findingsByPlugin(findings, 'motor_saturation')
  const severity = worstSeverity(motorFindings)
  const motorCount = metadata.motor_count || 4

  // Build motor data
  const motorStream = timeseries.motors || timeseries.actuator_output
  const motorKeys = motorStream
    ? Object.keys(motorStream).filter(k => k !== 'timestamps' && k.startsWith('output'))
    : []

  // Per-motor stats
  const motorStats = motorKeys.slice(0, motorCount).map((key, i) => {
    const values = motorStream?.[key] as number[] || []
    return {
      id: i,
      label: `M${i + 1}`,
      avg: avg(values),
      max: max(values),
      stdDev: stdDev(values),
      saturation: values.filter(v => v > 95).length / Math.max(values.length, 1) * 100,
      color: MOTOR_COLORS[i],
    }
  })

  // Aggregate stats
  const allAvgs = motorStats.map(m => m.avg)
  const maxSpread = allAvgs.length > 1 ? max(allAvgs) - Math.min(...allAvgs) : 0
  const avgOutput = avg(allAvgs)
  const headroom = 100 - max(motorStats.map(m => m.max))

  // Build chart data
  const { data: motorData } = buildChartData(timeseries, motorStream ? 'motors' : 'actuator_output')
  const motorSeries = motorKeys.slice(0, motorCount).map((_, i) => ({
    label: `Motor ${i + 1}`,
    color: MOTOR_COLORS[i],
    show: visibleMotors.has(i),
  }))

  const toggleMotor = (i: number) => {
    setVisibleMotors(prev => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i); else next.add(i)
      return next
    })
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
            <span className="text-3xl">⚙️</span> Motor Analysis
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">{motorCount} motors detected</p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* Per-Motor Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {motorStats.map((motor) => (
          <Card
            key={motor.id}
            hover
            onClick={() => toggleMotor(motor.id)}
            className={`relative overflow-hidden ${!visibleMotors.has(motor.id) ? 'opacity-40' : ''}`}
          >
            <div className="absolute top-0 left-0 w-1 h-full" style={{ backgroundColor: motor.color }} />
            <div className="pl-2">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold" style={{ color: motor.color }}>{motor.label}</span>
                <span className={`w-2.5 h-2.5 rounded-full ${motor.saturation > 5 ? 'bg-goose-error' : motor.avg > 80 ? 'bg-goose-warning' : 'bg-goose-success'}`} />
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Avg Output</span>
                  <span className="font-mono text-goose-text">{motor.avg.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Deviation</span>
                  <span className="font-mono text-goose-text">{motor.stdDev.toFixed(1)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Max</span>
                  <span className="font-mono text-goose-text">{motor.max.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Saturation</span>
                  <span className={`font-mono ${motor.saturation > 5 ? 'text-goose-error' : 'text-goose-success'}`}>
                    {motor.saturation.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Aggregate KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Avg Output"
          value={`${avgOutput.toFixed(1)}%`}
          status={avgOutput > 80 ? 'warning' : 'healthy'}
          subtitle="Mean across all motors"
        />
        <KPICard
          label="Motor Headroom"
          value={`${headroom.toFixed(1)}%`}
          status={headroom < 10 ? 'critical' : headroom < 25 ? 'warning' : 'healthy'}
          subtitle="Distance from saturation"
        />
        <KPICard
          label="Max Deviation"
          value={`${maxSpread.toFixed(1)}%`}
          status={maxSpread > 15 ? 'critical' : maxSpread > 8 ? 'warning' : 'healthy'}
          subtitle="Spread between motors"
        />
        <KPICard
          label="Imbalance"
          value={maxSpread < 5 ? 'Low' : maxSpread < 15 ? 'Medium' : 'High'}
          status={maxSpread < 5 ? 'healthy' : maxSpread < 15 ? 'warning' : 'critical'}
          subtitle={`${maxSpread.toFixed(1)}% inter-motor spread`}
        />
      </div>

      {/* Motor Selector Chips */}
      <div className="flex flex-wrap gap-2">
        {motorStats.map((motor) => (
          <button
            key={motor.id}
            onClick={() => toggleMotor(motor.id)}
            className={`
              px-3 py-1.5 rounded-full text-xs font-medium border transition-all cursor-pointer
              ${visibleMotors.has(motor.id)
                ? 'border-transparent text-white'
                : 'border-goose-border text-goose-text-muted bg-transparent'
              }
            `}
            style={visibleMotors.has(motor.id) ? { backgroundColor: motor.color } : {}}
          >
            {motor.label}
          </button>
        ))}
        <button
          onClick={() => setVisibleMotors(new Set(motorStats.map(m => m.id)))}
          className="px-3 py-1.5 rounded-full text-xs font-medium border border-goose-border text-goose-text-muted hover:text-goose-text cursor-pointer"
        >
          Show All
        </button>
      </div>

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'outputs', label: 'Motor Outputs' },
          { id: 'efficiency', label: 'Efficiency' },
          { id: 'balance', label: 'Balance' },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'outputs' && (
              <div className="space-y-4">
                <TimeSeriesChart
                  data={motorData}
                  series={motorSeries}
                  title="Motor Output (%) Over Time"
                  height={300}
                  thresholds={[
                    { value: 95, color: CHART_COLORS.threshold, label: '95% Saturation', dash: [6, 4] },
                  ]}
                />
              </div>
            )}
            {tab === 'efficiency' && (
              <div className="space-y-4">
                <Card>
                  <CardTitle className="mb-4">Hover Throttle Analysis</CardTitle>
                  <div className="flex items-center gap-6">
                    <div className="text-center">
                      <div className="text-4xl font-bold text-goose-accent">{avgOutput.toFixed(1)}%</div>
                      <Badge variant={avgOutput < 30 ? 'success' : avgOutput < 50 ? 'warning' : 'error'}>
                        {avgOutput < 30 ? 'Excellent' : avgOutput < 50 ? 'Normal' : 'High Load'}
                      </Badge>
                    </div>
                    <div className="flex-1">
                      <ProgressBar
                        value={avgOutput}
                        label="Average Motor Load"
                        size="lg"
                      />
                      <ProgressBar
                        value={headroom}
                        label="Motor Headroom"
                        size="lg"
                        color="accent"
                        className="mt-4"
                      />
                    </div>
                  </div>
                </Card>
              </div>
            )}
            {tab === 'balance' && (
              <div className="space-y-4">
                <Card>
                  <CardTitle className="mb-4">Motor Output Comparison</CardTitle>
                  <div className="space-y-3">
                    {motorStats.map((motor) => (
                      <div key={motor.id} className="flex items-center gap-3">
                        <span className="text-sm font-medium w-12" style={{ color: motor.color }}>{motor.label}</span>
                        <div className="flex-1">
                          <ProgressBar value={motor.avg} color="accent" showValue size="md" />
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
                <Card>
                  <CardTitle className="mb-2">Motor Balance Assessment</CardTitle>
                  <div className="flex items-center gap-2">
                    <span className={`w-3 h-3 rounded-full ${maxSpread < 5 ? 'bg-goose-success' : maxSpread < 15 ? 'bg-goose-warning' : 'bg-goose-error'}`} />
                    <span className="text-sm text-goose-text">
                      {maxSpread < 5
                        ? 'All motors are operating in balance. No significant difference detected.'
                        : maxSpread < 15
                          ? `Moderate imbalance detected (${maxSpread.toFixed(1)}% spread). Check CG and prop condition.`
                          : `Significant imbalance (${maxSpread.toFixed(1)}% spread). Inspect motors, props, and CG immediately.`
                      }
                    </span>
                  </div>
                </Card>
              </div>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {motorFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Motor Findings</CardTitle>
          <div className="space-y-2">
            {motorFindings.map((f) => (
              <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                <SeverityBadge severity={f.severity} />
                <div>
                  <p className="text-sm font-medium text-goose-text">{f.title}</p>
                  <p className="text-xs text-goose-text-muted mt-1">{f.description}</p>
                  <ConfidenceBadge band={f.confidence_band} score={f.confidence} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
