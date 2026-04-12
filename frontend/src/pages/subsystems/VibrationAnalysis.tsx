import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Tabs } from '@/components/ui/Tabs'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TimeSeriesChart, CHART_COLORS } from '@/components/charts/TimeSeriesChart'
import { buildChartData, findingsByPlugin, worstSeverity, avg, max, stdDev } from '@/lib/streams'

export function VibrationAnalysis() {
  const navigate = useNavigate()
  const { currentAnalysis } = useAnalysisStore()

  if (!currentAnalysis) {
    return (
      <div className="p-6">
        <Button variant="secondary" onClick={() => navigate('/analyze')}>Run Analysis First</Button>
      </div>
    )
  }

  const { timeseries, findings } = currentAnalysis
  const vibFindings = findingsByPlugin(findings, 'vibration')
  const dmgFindings = findingsByPlugin(findings, 'damage_impact_classification')
  const allFindings = [...vibFindings, ...dmgFindings]
  const severity = worstSeverity(allFindings)

  const vibStream = timeseries.vibration
  const accelX = (vibStream?.accel_x as number[]) || []
  const accelY = (vibStream?.accel_y as number[]) || []
  const accelZ = (vibStream?.accel_z as number[]) || []

  // Compute magnitude: sqrt(x² + y² + z²)
  const magnitude = accelX.map((x, i) => {
    const y = accelY[i] || 0
    const z = accelZ[i] || 0
    return Math.sqrt(x * x + y * y + z * z)
  })

  const avgMag = avg(magnitude)
  const maxMag = max(magnitude)
  const stdMag = stdDev(magnitude)
  const dataPoints = magnitude.length

  // Clipping detection (>156 m/s² = 16g sensor max)
  const clippingCount = magnitude.filter(v => v > 156).length
  const clippingPct = dataPoints > 0 ? (clippingCount / dataPoints) * 100 : 0

  // Health assessment
  const vibHealth = avgMag < 15 ? 'healthy' : avgMag < 30 ? 'warning' : 'critical'
  const vibLabel = avgMag < 15 ? 'Good' : avgMag < 30 ? 'Elevated' : 'Critical'

  // Chart data
  const { data: accelData } = buildChartData(timeseries, 'vibration', ['accel_x', 'accel_y', 'accel_z'])

  // Build magnitude chart data
  const magTimestamps = vibStream?.timestamps || []
  const magData = magTimestamps.length > 0 ? [magTimestamps, magnitude] : [new Float64Array(0)]

  // Gyro data
  const { data: gyroData, fieldNames: gyroFields } = buildChartData(timeseries, 'raw_gyro')

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
            &larr; Back to Results
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            <span className="text-3xl">📳</span> Vibration Analysis
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            Accelerometer vibration magnitude: <span className="font-mono text-goose-text">√(ax² + ay² + az²)</span>
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPICard
          label="Average"
          value={`${avgMag.toFixed(1)}`}
          unit="m/s²"
          status={vibHealth}
          subtitle={vibLabel}
        />
        <KPICard
          label="Maximum"
          value={`${maxMag.toFixed(1)}`}
          unit="m/s²"
          status={maxMag > 60 ? 'critical' : maxMag > 30 ? 'warning' : 'healthy'}
          subtitle={maxMag > 60 ? 'Dangerous' : maxMag > 30 ? 'High' : 'Normal'}
        />
        <KPICard
          label="Std Deviation"
          value={`${stdMag.toFixed(2)}`}
          subtitle="Consistency measure"
        />
        <KPICard
          label="Data Points"
          value={dataPoints.toLocaleString()}
          subtitle="Accelerometer samples"
        />
        <KPICard
          label="Clipping"
          value={`${clippingPct.toFixed(1)}%`}
          status={clippingPct > 1 ? 'critical' : clippingPct > 0 ? 'warning' : 'healthy'}
          subtitle={clippingCount > 0 ? `${clippingCount} samples clipped` : 'No sensor saturation'}
        />
      </div>

      {/* Vibration Thresholds Reference */}
      <Card>
        <CardTitle className="mb-3">Vibration Reference Thresholds</CardTitle>
        <div className="grid grid-cols-4 gap-2">
          {[
            { range: '< 15 m/s²', label: 'Good', color: 'bg-goose-success', desc: 'Normal for well-balanced aircraft' },
            { range: '15-30 m/s²', label: 'Elevated', color: 'bg-goose-warning', desc: 'Check prop balance, motor bearings' },
            { range: '30-60 m/s²', label: 'High', color: 'bg-goose-error', desc: 'IMU data degraded, fix immediately' },
            { range: '> 60 m/s²', label: 'Dangerous', color: 'bg-red-700', desc: 'Attitude estimation unreliable' },
          ].map((t) => (
            <div key={t.label} className="flex items-start gap-2 p-2 rounded-lg bg-goose-bg">
              <span className={`w-3 h-3 rounded-full ${t.color} shrink-0 mt-0.5`} />
              <div>
                <div className="text-xs font-medium text-goose-text">{t.range}</div>
                <div className="text-[10px] text-goose-text-muted">{t.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'magnitude', label: 'Magnitude' },
          { id: 'acceleration', label: 'Acceleration (XYZ)' },
          { id: 'gyro', label: 'Gyro' },
          { id: 'impact', label: 'Impact Analysis' },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'magnitude' && (
              <TimeSeriesChart
                data={magData as any}
                series={[{ label: '√(ax²+ay²+az²) m/s²', color: CHART_COLORS.vibration, width: 1 }]}
                title="Vibration Magnitude Over Time"
                height={300}
                thresholds={[
                  { value: 15, color: CHART_COLORS.gps, label: 'Good (15)', dash: [6, 4] },
                  { value: 30, color: CHART_COLORS.voltage, label: 'Warning (30)', dash: [6, 4] },
                  { value: 60, color: CHART_COLORS.threshold, label: 'Dangerous (60)', dash: [4, 2] },
                ]}
              />
            )}
            {tab === 'acceleration' && (
              <TimeSeriesChart
                data={accelData}
                series={[
                  { label: 'Accel X', color: CHART_COLORS.roll, width: 1 },
                  { label: 'Accel Y', color: CHART_COLORS.pitch, width: 1 },
                  { label: 'Accel Z', color: CHART_COLORS.yaw, width: 1 },
                ]}
                title="Per-Axis Acceleration (m/s²)"
                height={300}
              />
            )}
            {tab === 'gyro' && (
              <div>
                {gyroData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={gyroData}
                    series={gyroFields.map((f, i) => ({
                      label: f,
                      color: [CHART_COLORS.roll, CHART_COLORS.pitch, CHART_COLORS.yaw][i % 3],
                      width: 1,
                    }))}
                    title="Raw Gyro Data (rad/s)"
                    height={300}
                  />
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">
                    No raw gyro data available in this log
                  </Card>
                )}
              </div>
            )}
            {tab === 'impact' && (
              <Card>
                <CardTitle className="mb-4">Impact / Damage Analysis</CardTitle>
                {dmgFindings.length > 0 ? (
                  <div className="space-y-3">
                    {dmgFindings.map((f) => (
                      <div key={f.finding_id} className="p-3 rounded-lg bg-goose-bg border border-goose-border">
                        <div className="flex items-center gap-2 mb-1">
                          <SeverityBadge severity={f.severity} />
                          <span className="text-sm font-medium text-goose-text">{f.title}</span>
                        </div>
                        <p className="text-xs text-goose-text-muted">{f.description}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-goose-text-muted">
                    No impact signatures detected in this flight. The damage/impact classification plugin analyzes acceleration spikes for collision patterns.
                  </p>
                )}
              </Card>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {vibFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Vibration Findings</CardTitle>
          <div className="space-y-2">
            {vibFindings.map((f) => (
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
