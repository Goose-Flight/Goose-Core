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

  const { timeseries, findings, metadata } = currentAnalysis
  const vibFindings = findingsByPlugin(findings, 'vibration')
  const dmgFindings = findingsByPlugin(findings, 'damage_impact_classification')
  const allFindings = [...vibFindings, ...dmgFindings]
  const severity = worstSeverity(allFindings)

  const vibStream = timeseries.vibration
  const hasVibData = !!vibStream && !!vibStream.timestamps && (vibStream.timestamps as number[]).length > 0

  const accelX = (vibStream?.accel_x as number[]) || []
  const accelY = (vibStream?.accel_y as number[]) || []
  const accelZ = (vibStream?.accel_z as number[]) || []

  // Compute magnitude: sqrt(x^2 + y^2 + z^2)
  const magnitude = accelX.length > 0
    ? accelX.map((x, i) => {
        const y = accelY[i] || 0
        const z = accelZ[i] || 0
        return Math.sqrt(x * x + y * y + z * z)
      })
    : []

  const avgMag = magnitude.length > 0 ? avg(magnitude) : 0
  const maxMag = magnitude.length > 0 ? max(magnitude) : 0
  const stdMag = magnitude.length > 0 ? stdDev(magnitude) : 0
  const dataPoints = magnitude.length

  // Clipping detection (>156 m/s^2 = 16g sensor max)
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
            {metadata.vehicle_type} &middot; {metadata.autopilot.toUpperCase()}
            {metadata.duration_sec ? ` \u00b7 ${(metadata.duration_sec / 60).toFixed(1)} min` : ''}
            {' '}&middot; Magnitude: <span className="font-mono text-goose-text">&radic;(ax&sup2; + ay&sup2; + az&sup2;)</span>
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* No data warning */}
      {!hasVibData && (
        <Card className="border-goose-warning/30 bg-gradient-to-r from-goose-warning/5 to-transparent">
          <div className="flex items-start gap-3">
            <span className="text-2xl">⚠️</span>
            <div>
              <p className="text-sm font-medium text-goose-warning">No Accelerometer Data Available</p>
              <p className="text-xs text-goose-text-muted mt-1">
                This flight log does not contain vibration or accelerometer data. The IMU may not have been
                logging high-rate accelerometer samples, or the vibration stream was not included in this log format.
                Statistics below may show zero values.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Explanation Card */}
      <Card className="bg-gradient-to-br from-goose-chart-1/5 to-transparent">
        <CardTitle className="mb-2">What This Page Shows</CardTitle>
        <p className="text-xs text-goose-text-muted leading-relaxed">
          Vibration analysis measures accelerometer noise across all three axes during flight.
          <strong className="text-goose-text"> Magnitude</strong> is computed as the Euclidean norm of acceleration:
          <span className="font-mono text-goose-text"> mag = sqrt(ax&sup2; + ay&sup2; + az&sup2;)</span>.
          <strong className="text-goose-text"> Clipping</strong> occurs when acceleration exceeds 156 m/s&sup2; (16g sensor limit),
          meaning the IMU is saturated and data is lost.
          High vibration degrades the EKF's ability to estimate attitude and position, leading to poor flight
          performance and potential flyaways.
        </p>
      </Card>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPICard
          label="Average"
          value={`${avgMag.toFixed(1)}`}
          unit="m/s&sup2;"
          status={vibHealth}
          subtitle={vibLabel}
        />
        <KPICard
          label="Maximum"
          value={`${maxMag.toFixed(1)}`}
          unit="m/s&sup2;"
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
            { range: '< 15 m/s\u00b2', label: 'Good', color: 'bg-goose-success', desc: 'Normal for well-balanced aircraft' },
            { range: '15-30 m/s\u00b2', label: 'Elevated', color: 'bg-goose-warning', desc: 'Check prop balance, motor bearings' },
            { range: '30-60 m/s\u00b2', label: 'High', color: 'bg-goose-error', desc: 'IMU data degraded, fix immediately' },
            { range: '> 60 m/s\u00b2', label: 'Dangerous', color: 'bg-red-700', desc: 'Attitude estimation unreliable' },
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
              <div className="space-y-4">
                {(magData[0] as number[] | Float64Array).length > 0 ? (
                  <TimeSeriesChart
                    data={magData as any}
                    series={[{ label: '\u221a(ax\u00b2+ay\u00b2+az\u00b2) m/s\u00b2', color: CHART_COLORS.vibration, width: 1 }]}
                    title="Vibration Magnitude Over Time"
                    height={300}
                    thresholds={[
                      { value: 15, color: CHART_COLORS.gps, label: 'Good (15)', dash: [6, 4] },
                      { value: 30, color: CHART_COLORS.voltage, label: 'Warning (30)', dash: [6, 4] },
                      { value: 60, color: CHART_COLORS.threshold, label: 'Dangerous (60)', dash: [4, 2] },
                    ]}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No vibration magnitude data available in this log
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Vibration magnitude combines all three accelerometer axes into a single metric. The three threshold
                    lines mark the boundaries between good, elevated, and dangerous vibration levels. Spikes above the
                    red line indicate moments where attitude estimation becomes unreliable. Persistent elevation above
                    15 m/s&sup2; warrants investigation into propeller balance, motor bearings, and frame rigidity.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'acceleration' && (
              <div className="space-y-4">
                {accelData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={accelData}
                    series={[
                      { label: 'Accel X', color: CHART_COLORS.roll, width: 1 },
                      { label: 'Accel Y', color: CHART_COLORS.pitch, width: 1 },
                      { label: 'Accel Z', color: CHART_COLORS.yaw, width: 1 },
                    ]}
                    title="Per-Axis Acceleration (m/s\u00b2)"
                    height={300}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No per-axis acceleration data available in this log
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">Per-axis acceleration</strong> reveals which direction vibrations are
                    dominant. X and Y axes (roll/pitch plane) are most affected by propeller imbalance. The Z axis
                    includes gravity (~9.8 m/s&sup2;) plus vertical vibration. If one axis is significantly noisier than
                    the others, it can point to a specific mechanical issue — e.g., a bent motor shaft or loose mount on that side.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'gyro' && (
              <div className="space-y-4">
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
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No raw gyro data available in this log
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">Gyroscope data</strong> measures rotational rate around each axis in
                    radians per second. High-frequency noise in the gyro signal indicates vibration coupling into the
                    flight controller. Clean gyro traces with sharp, intentional movements suggest good mechanical isolation.
                    Broadband noise across all axes typically points to frame or mounting vibration issues.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'impact' && (
              <div className="space-y-4">
                <Card>
                  <CardTitle className="mb-4">Impact / Damage Analysis</CardTitle>
                  {dmgFindings.length > 0 ? (
                    <div className="space-y-3">
                      {dmgFindings.map((f) => (
                        <div key={f.finding_id} className="p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <div className="flex items-center gap-2 mb-1">
                            <SeverityBadge severity={f.severity} />
                            <span className="text-sm font-medium text-goose-text">{f.title}</span>
                            <ConfidenceBadge band={f.confidence_band} score={f.confidence} />
                          </div>
                          <p className="text-xs text-goose-text-muted">{f.description}</p>
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
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-goose-text-muted">
                      No impact signatures detected in this flight. The damage/impact classification plugin analyzes acceleration spikes for collision patterns.
                    </p>
                  )}
                </Card>
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Impact analysis looks for sudden, high-magnitude acceleration spikes that match collision signatures.
                    These differ from vibration noise by their sharp onset, short duration, and multi-axis nature. A confirmed
                    impact event suggests the aircraft struck an object during flight.
                  </p>
                </Card>
              </div>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {vibFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Vibration Findings ({vibFindings.length})</CardTitle>
          <div className="space-y-2">
            {vibFindings.map((f) => (
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

      {/* Assessment */}
      <Card className={`bg-gradient-to-r ${avgMag < 15 && clippingPct === 0 ? 'from-goose-success/5' : avgMag < 30 ? 'from-goose-warning/5' : 'from-goose-error/5'} to-transparent`}>
        <CardTitle className="mb-2">Vibration Assessment</CardTitle>
        <p className="text-sm text-goose-text">
          {!hasVibData
            ? 'No accelerometer data was available in this flight log. Vibration quality cannot be assessed. Ensure high-rate IMU logging is enabled for the next flight.'
            : avgMag < 15 && clippingPct === 0
              ? `Vibration levels are healthy with an average magnitude of ${avgMag.toFixed(1)} m/s\u00b2 and no sensor clipping. The airframe is well-balanced and mechanically sound. No action needed.`
              : avgMag < 30
                ? `Vibration is elevated (${avgMag.toFixed(1)} m/s\u00b2 average). ${clippingPct > 0 ? `Sensor clipping detected in ${clippingPct.toFixed(1)}% of samples — IMU data integrity is compromised. ` : ''}Check propeller balance, motor bearings, and mounting hardware. Soft-mounting the flight controller may help reduce vibration coupling.`
                : `Vibration is dangerously high at ${avgMag.toFixed(1)} m/s\u00b2 average (peak: ${maxMag.toFixed(1)} m/s\u00b2). ${clippingPct > 0 ? `${clippingPct.toFixed(1)}% sensor clipping detected. ` : ''}The EKF cannot reliably estimate attitude at these levels. Immediately inspect all propellers for damage, verify motor bearings, tighten all frame hardware, and ensure the flight controller is properly isolated from frame vibrations.`
          }
        </p>
      </Card>
    </div>
  )
}
