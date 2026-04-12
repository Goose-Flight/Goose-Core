import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Tabs } from '@/components/ui/Tabs'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TimeSeriesChart, CHART_COLORS } from '@/components/charts/TimeSeriesChart'
import { findingsByPlugin, worstSeverity, avg, max, min, stdDev } from '@/lib/streams'
import type uPlot from 'uplot'

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

  // Find motor stream — could be 'motors' or 'actuator_output'
  const motorStream = timeseries.motors || timeseries.actuator_output

  // Detect motor field naming: output_0, output_1 OR output0, output1 OR motor_0, motor_1
  const motorKeys: string[] = []
  if (motorStream) {
    const allKeys = Object.keys(motorStream).filter(k => k !== 'timestamps')
    // Try output_N format first (most common from PX4)
    for (let i = 0; i < motorCount; i++) {
      const candidates = [`output_${i}`, `output${i}`, `motor_${i}`, `motor${i}`, `m${i+1}`]
      const found = candidates.find(c => allKeys.includes(c))
      if (found) motorKeys.push(found)
    }
    // Fallback: just take first N numeric-looking keys
    if (motorKeys.length === 0) {
      motorKeys.push(...allKeys.slice(0, motorCount))
    }
  }

  // Per-motor stats
  const motorStats = motorKeys.map((key, i) => {
    const rawValues = (motorStream?.[key] as number[]) || []
    // Normalize: if values are in -1 to 1 range, convert to 0-100%
    // If values are in 0-2000 range (PWM), convert to 0-100%
    let values = rawValues
    const maxRaw = max(rawValues)
    const minRaw = min(rawValues)
    if (maxRaw <= 1.0 && minRaw >= -1.0) {
      // Normalized -1 to 1 → 0 to 100%
      values = rawValues.map(v => Math.max(0, (v + 1) / 2 * 100))
    } else if (maxRaw > 1000) {
      // PWM (typically 1000-2000) → 0 to 100%
      values = rawValues.map(v => Math.max(0, (v - 1000) / 10))
    }

    const validValues = values.filter(v => v > 0) // Filter out zeros/negatives

    return {
      id: i,
      label: `M${i + 1}`,
      key,
      avg: validValues.length > 0 ? avg(validValues) : 0,
      max: validValues.length > 0 ? max(validValues) : 0,
      min: validValues.length > 0 ? min(validValues) : 0,
      stdDev: validValues.length > 0 ? stdDev(validValues) : 0,
      saturation: validValues.length > 0 ? validValues.filter(v => v > 95).length / validValues.length * 100 : 0,
      dataPoints: validValues.length,
      color: MOTOR_COLORS[i],
      hasData: validValues.length > 0,
    }
  })

  const motorsWithData = motorStats.filter(m => m.hasData)
  const allAvgs = motorsWithData.map(m => m.avg)
  const maxSpread = allAvgs.length > 1 ? max(allAvgs) - min(allAvgs) : 0
  const avgOutput = allAvgs.length > 0 ? avg(allAvgs) : 0
  const headroom = motorsWithData.length > 0 ? 100 - max(motorsWithData.map(m => m.max)) : 100

  // Build chart data from raw motor stream
  const chartData: uPlot.AlignedData = motorStream && motorStream.timestamps
    ? [motorStream.timestamps as number[], ...motorKeys.map(k => (motorStream[k] as number[]) || [])] as uPlot.AlignedData
    : [new Float64Array(0)]

  const motorSeries = motorKeys.map((_, i) => ({
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

  const noMotorData = motorsWithData.length === 0

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
          <p className="text-sm text-goose-text-muted mt-1">
            {motorCount} motors &middot; {metadata.vehicle_type} &middot; {metadata.autopilot.toUpperCase()}
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* No data warning */}
      {noMotorData && (
        <Card className="border-goose-warning/30 bg-gradient-to-r from-goose-warning/5 to-transparent">
          <div className="flex items-start gap-3">
            <span className="text-2xl">⚠️</span>
            <div>
              <p className="text-sm font-medium text-goose-warning">Limited Motor Data</p>
              <p className="text-xs text-goose-text-muted mt-1">
                This flight log has no usable motor output data. Motor outputs may not have been logged,
                or the aircraft was not armed during this recording. Statistics below may show zero values.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Explanation Card */}
      <Card className="bg-gradient-to-br from-goose-chart-1/5 to-transparent">
        <CardTitle className="mb-2">What This Page Shows</CardTitle>
        <p className="text-xs text-goose-text-muted leading-relaxed">
          Motor analysis examines the PWM/throttle output signals sent to each motor during flight.
          <strong className="text-goose-text"> Saturation</strong> occurs when a motor hits its maximum output (95%+), meaning the flight controller has no more authority on that axis.
          <strong className="text-goose-text"> Imbalance</strong> between motors indicates asymmetric load — caused by off-center CG, damaged props, or weak motors.
          <strong className="text-goose-text"> Headroom</strong> is the gap between peak motor output and 100% — more headroom = safer flight with reserve thrust.
        </p>
      </Card>

      {/* Per-Motor Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {motorStats.slice(0, motorCount).map((motor) => (
          <Card
            key={motor.id}
            hover
            onClick={() => toggleMotor(motor.id)}
            className={`relative overflow-hidden ${!visibleMotors.has(motor.id) ? 'opacity-40' : ''} ${!motor.hasData ? 'opacity-30' : ''}`}
          >
            <div className="absolute top-0 left-0 w-1 h-full" style={{ backgroundColor: motor.color }} />
            <div className="pl-2">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold" style={{ color: motor.color }}>{motor.label}</span>
                {motor.hasData ? (
                  <span className={`w-2.5 h-2.5 rounded-full ${motor.saturation > 5 ? 'bg-goose-error' : motor.avg > 80 ? 'bg-goose-warning' : 'bg-goose-success'}`} />
                ) : (
                  <span className="text-[10px] text-goose-text-muted">No data</span>
                )}
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Avg Output</span>
                  <span className="font-mono text-goose-text">{motor.avg.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Deviation</span>
                  <span className="font-mono text-goose-text">&sigma; {motor.stdDev.toFixed(1)}</span>
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
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Samples</span>
                  <span className="font-mono text-goose-text">{motor.dataPoints.toLocaleString()}</span>
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
          status={avgOutput > 80 ? 'warning' : avgOutput > 0 ? 'healthy' : 'neutral'}
          subtitle={avgOutput < 30 ? 'Efficient — low hover throttle' : avgOutput < 50 ? 'Normal load' : 'High load — check weight'}
        />
        <KPICard
          label="Motor Headroom"
          value={`${headroom.toFixed(1)}%`}
          status={headroom < 10 ? 'critical' : headroom < 25 ? 'warning' : 'healthy'}
          subtitle={headroom < 10 ? 'Dangerously low!' : headroom < 25 ? 'Limited reserve thrust' : 'Good reserve available'}
        />
        <KPICard
          label="Max Deviation"
          value={`${maxSpread.toFixed(1)}%`}
          status={maxSpread > 15 ? 'critical' : maxSpread > 8 ? 'warning' : 'healthy'}
          subtitle={maxSpread > 15 ? 'Check CG and props!' : maxSpread > 8 ? 'Slight imbalance' : 'Well balanced'}
        />
        <KPICard
          label="Balance Score"
          value={maxSpread < 5 ? '100' : maxSpread < 10 ? `${(100 - maxSpread * 2).toFixed(0)}` : `${Math.max(0, 100 - maxSpread * 3).toFixed(0)}`}
          unit="/100"
          status={maxSpread < 5 ? 'healthy' : maxSpread < 15 ? 'warning' : 'critical'}
          subtitle="1 - (spread / avg output)"
        />
      </div>

      {/* Motor Selector Chips */}
      {motorsWithData.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {motorStats.slice(0, motorCount).map((motor) => (
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
              {motor.label} {motor.hasData ? '' : '(no data)'}
            </button>
          ))}
          <button
            onClick={() => setVisibleMotors(new Set(motorStats.map(m => m.id)))}
            className="px-3 py-1.5 rounded-full text-xs font-medium border border-goose-border text-goose-text-muted hover:text-goose-text cursor-pointer"
          >
            Show All
          </button>
        </div>
      )}

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'outputs', label: 'Motor Outputs' },
          { id: 'efficiency', label: 'Efficiency' },
          { id: 'balance', label: 'Balance' },
          { id: 'health', label: 'Health Assessment' },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'outputs' && (
              <div className="space-y-4">
                {chartData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={chartData}
                    series={motorSeries}
                    title="Motor Output Over Time"
                    height={300}
                    thresholds={[
                      { value: 95, color: CHART_COLORS.threshold, label: '95% Saturation', dash: [6, 4] },
                    ]}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No motor output time-series data available in this log
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Motor output represents the throttle command sent to each ESC. Values above 95% (red dashed line)
                    indicate saturation — the flight controller is demanding maximum thrust. Sustained saturation means
                    the drone cannot maintain attitude control and may become unstable.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'efficiency' && (
              <div className="space-y-4">
                <Card>
                  <CardTitle className="mb-4">Hover Throttle Analysis</CardTitle>
                  <div className="flex items-center gap-8">
                    <div className="text-center">
                      <div className="text-5xl font-bold text-goose-accent">{avgOutput.toFixed(1)}%</div>
                      <Badge variant={avgOutput < 30 ? 'success' : avgOutput < 50 ? 'warning' : 'error'} className="mt-2">
                        {avgOutput < 30 ? 'Excellent' : avgOutput < 50 ? 'Normal' : 'High Load'}
                      </Badge>
                    </div>
                    <div className="flex-1 space-y-4">
                      <ProgressBar
                        value={avgOutput}
                        label="Average Motor Load"
                        size="lg"
                      />
                      <ProgressBar
                        value={headroom}
                        label="Motor Headroom (reserve thrust)"
                        size="lg"
                        color="accent"
                      />
                      <ProgressBar
                        value={Math.max(0, 100 - maxSpread * 5)}
                        label="Motor Balance"
                        size="lg"
                        color={maxSpread < 5 ? 'success' : maxSpread < 15 ? 'warning' : 'error'}
                      />
                    </div>
                  </div>
                </Card>
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">Hover throttle</strong> is the average motor output needed to maintain altitude.
                    Lower is better — it means the drone has plenty of excess thrust for maneuvers and wind gusts.
                    Values below 30% are excellent. Above 50% means the drone is overweight or underpowered.
                    <strong className="text-goose-text"> Headroom</strong> is the gap between your peak motor output and 100%.
                    At least 20% headroom is recommended for safe flight.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'balance' && (
              <div className="space-y-4">
                <Card>
                  <CardTitle className="mb-4">Motor Output Comparison</CardTitle>
                  <div className="space-y-3">
                    {motorStats.slice(0, motorCount).map((motor) => (
                      <div key={motor.id} className="flex items-center gap-3">
                        <span className="text-sm font-medium w-12" style={{ color: motor.color }}>{motor.label}</span>
                        <div className="flex-1">
                          <ProgressBar value={motor.avg} color="accent" showValue size="md" />
                        </div>
                        <span className="text-xs font-mono text-goose-text-muted w-16 text-right">&sigma; {motor.stdDev.toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                </Card>
                <Card>
                  <CardTitle className="mb-2">Motor Balance Assessment</CardTitle>
                  <div className="flex items-center gap-2 mt-3">
                    <span className={`w-3 h-3 rounded-full ${maxSpread < 5 ? 'bg-goose-success' : maxSpread < 15 ? 'bg-goose-warning' : 'bg-goose-error'}`} />
                    <span className="text-sm text-goose-text">
                      {maxSpread < 5
                        ? 'All motors are operating in balance. No significant inter-motor deviation detected. CG appears well-centered.'
                        : maxSpread < 15
                          ? `Moderate imbalance detected (${maxSpread.toFixed(1)}% spread between highest and lowest motor). Check center of gravity position and propeller condition. One motor is working harder than the others to compensate.`
                          : `Significant motor imbalance detected (${maxSpread.toFixed(1)}% spread). This indicates a shifted CG, damaged propeller, or weak motor. Inspect all props for damage, verify CG position, and check each motor for bearing wear.`
                      }
                    </span>
                  </div>
                </Card>
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Motor balance compares the average output of each motor. On a perfectly balanced multirotor,
                    all motors should produce roughly equal output. A spread greater than 15% is concerning and
                    indicates mechanical issues. Common causes: off-center battery placement, bent motor mount,
                    damaged prop, or failing motor bearing.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'health' && (
              <div className="space-y-4">
                <Card>
                  <CardTitle className="mb-4">Motor Health Summary</CardTitle>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {motorStats.slice(0, motorCount).map((motor) => {
                      const health = motor.saturation > 10 ? 'critical' : motor.saturation > 2 ? 'warning' : motor.avg > 80 ? 'warning' : 'healthy'
                      const healthPct = health === 'healthy' ? 100 : health === 'warning' ? 70 : 30
                      return (
                        <Card key={motor.id} padding="sm" className="text-center">
                          <span className="text-lg font-bold" style={{ color: motor.color }}>{motor.label}</span>
                          <div className="mt-2">
                            <div className={`text-2xl font-bold ${health === 'healthy' ? 'text-goose-success' : health === 'warning' ? 'text-goose-warning' : 'text-goose-error'}`}>
                              {healthPct}%
                            </div>
                            <ProgressBar value={healthPct} size="sm" showValue={false} className="mt-1" />
                          </div>
                          <div className="mt-2 text-[10px] text-goose-text-muted space-y-0.5">
                            <div>Avg: {motor.avg.toFixed(1)}%</div>
                            <div>Sat: {motor.saturation.toFixed(1)}%</div>
                            <div>&sigma;: {motor.stdDev.toFixed(1)}</div>
                          </div>
                        </Card>
                      )
                    })}
                  </div>
                </Card>

                {/* Overall assessment */}
                <Card className={`bg-gradient-to-r ${maxSpread < 5 && avgOutput < 50 ? 'from-goose-success/5' : maxSpread < 15 ? 'from-goose-warning/5' : 'from-goose-error/5'} to-transparent`}>
                  <CardTitle className="mb-2">Overall Motor Assessment</CardTitle>
                  <p className="text-sm text-goose-text">
                    {maxSpread < 5 && avgOutput < 50 && headroom > 25
                      ? 'Motors are healthy and well-balanced. Good headroom available for maneuvers. No action needed.'
                      : maxSpread < 15 && avgOutput < 70
                        ? `Motors show moderate load (${avgOutput.toFixed(0)}% avg) with ${headroom.toFixed(0)}% headroom. ${maxSpread > 8 ? 'Some imbalance detected — check CG and prop condition.' : 'Balance looks acceptable.'}`
                        : `Motor system needs attention. ${avgOutput > 70 ? 'High motor load detected — consider reducing weight or upgrading motors. ' : ''}${maxSpread > 15 ? 'Significant imbalance — inspect props, motors, and CG. ' : ''}${headroom < 10 ? 'Critically low headroom — risk of loss of control in wind or aggressive maneuvers.' : ''}`
                    }
                  </p>
                </Card>
              </div>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {motorFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Motor Findings ({motorFindings.length})</CardTitle>
          <div className="space-y-2">
            {motorFindings.map((f) => (
              <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                <SeverityBadge severity={f.severity} />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-goose-text">{f.title}</p>
                    <ConfidenceBadge band={f.confidence_band} score={f.confidence} />
                  </div>
                  <p className="text-xs text-goose-text-muted mt-1">{f.description}</p>
                  {Object.keys(f.supporting_metrics).length > 0 && (
                    <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10px] font-mono text-goose-text-muted">
                      {Object.entries(f.supporting_metrics).slice(0, 6).map(([k, v]) => (
                        <div key={k}>
                          <span className="text-goose-text-muted">{k}:</span>{' '}
                          <span className="text-goose-text">{typeof v === 'number' ? (v as number).toFixed(2) : String(v)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
