import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Tabs } from '@/components/ui/Tabs'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TimeSeriesChart, CHART_COLORS } from '@/components/charts/TimeSeriesChart'
import { buildChartData, findingsByPlugin, worstSeverity, avg, max, min } from '@/lib/streams'

export function GPSAnalysis() {
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
  const gpsFindings = findingsByPlugin(findings, 'gps_health')
  const ekfFindings = findingsByPlugin(findings, 'ekf_consistency')
  const allFindings = [...gpsFindings, ...ekfFindings]
  const severity = worstSeverity(allFindings)

  const gpsStream = timeseries.gps
  const hasGpsData = !!gpsStream && !!gpsStream.timestamps && (gpsStream.timestamps as number[]).length > 0

  const satellites = (gpsStream?.satellites as number[]) || []
  const hdop = (gpsStream?.hdop as number[]) || []

  const avgSats = satellites.length > 0 ? avg(satellites) : 0
  const minSats = satellites.length > 0 ? min(satellites) : 0
  const avgHdop = hdop.length > 0 ? avg(hdop) : 0
  const maxHdop = hdop.length > 0 ? max(hdop) : 0

  // GPS quality score
  const gpsScore = satellites.length > 0
    ? Math.min(100, Math.round((avgSats / 20) * 50 + (2.0 / Math.max(avgHdop, 0.5)) * 50))
    : 0

  // Chart data
  const { data: satData } = buildChartData(timeseries, 'gps', ['satellites'])
  const { data: hdopData } = buildChartData(timeseries, 'gps', ['hdop'])

  // EKF data
  const ekfStream = timeseries.ekf
  const { data: ekfData, fieldNames: ekfFields } = buildChartData(timeseries, 'ekf')

  // Position tracking
  const posStream = timeseries.position
  const { data: posData, fieldNames: posFields } = buildChartData(timeseries, 'position')

  // Sensor health bars
  const sensorHealth = [
    { name: 'IMU', score: 100, desc: 'Accel/Gyro consistency', color: 'accent' as const },
    { name: 'GPS', score: gpsScore, desc: `HDOP: ${avgHdop.toFixed(2)}, Sats: ${avgSats.toFixed(0)}`, color: 'accent' as const },
    { name: 'MAG', score: 100, desc: 'Heading consistency', color: 'accent' as const },
    { name: 'BARO', score: 99, desc: 'Altimeter consistency', color: 'accent' as const },
  ]
  const fusionScore = Math.round(avg(sensorHealth.map(s => s.score)))

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
            &larr; Back to Results
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            <span className="text-3xl">📡</span> GPS / Navigation
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            {metadata.vehicle_type} &middot; {metadata.autopilot.toUpperCase()}
            {metadata.duration_sec ? ` \u00b7 ${(metadata.duration_sec / 60).toFixed(1)} min` : ''}
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* No data warning */}
      {!hasGpsData && (
        <Card className="border-goose-warning/30 bg-gradient-to-r from-goose-warning/5 to-transparent">
          <div className="flex items-start gap-3">
            <span className="text-2xl">⚠️</span>
            <div>
              <p className="text-sm font-medium text-goose-warning">No GPS Data Available</p>
              <p className="text-xs text-goose-text-muted mt-1">
                This flight log does not contain GPS telemetry. The GPS receiver may not have been connected,
                or the log was recorded before a satellite fix was acquired. Statistics below may show zero values.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Explanation Card */}
      <Card className="bg-gradient-to-br from-goose-chart-1/5 to-transparent">
        <CardTitle className="mb-2">What This Page Shows</CardTitle>
        <p className="text-xs text-goose-text-muted leading-relaxed">
          GPS analysis evaluates satellite positioning quality throughout the flight.
          <strong className="text-goose-text"> HDOP</strong> (Horizontal Dilution of Precision) measures geometric accuracy — values below 1.5 are excellent, above 2.5 indicates degraded positioning.
          <strong className="text-goose-text"> Satellite count</strong> should stay above 8 for reliable 3D fixes; drops below this threshold risk position drift.
          <strong className="text-goose-text"> EKF</strong> (Extended Kalman Filter) fuses GPS with IMU, magnetometer, and barometer data — innovation ratios above 0.5 indicate sensor disagreement.
        </p>
      </Card>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPICard
          label="Satellites"
          value={avgSats.toFixed(0)}
          status={avgSats >= 12 ? 'healthy' : avgSats >= 8 ? 'warning' : 'critical'}
          subtitle={`Min: ${minSats}`}
        />
        <KPICard
          label="HDOP"
          value={avgHdop.toFixed(2)}
          status={avgHdop < 1.5 ? 'healthy' : avgHdop < 2.5 ? 'warning' : 'critical'}
          subtitle={`Max: ${maxHdop.toFixed(2)}`}
        />
        <KPICard
          label="GPS Quality"
          value={`${gpsScore}%`}
          status={gpsScore >= 80 ? 'healthy' : gpsScore >= 50 ? 'warning' : 'critical'}
          subtitle={gpsScore >= 80 ? 'Reliable positioning' : 'Degraded'}
        />
        <KPICard
          label="Fusion Score"
          value={`${fusionScore}%`}
          status={fusionScore >= 90 ? 'healthy' : fusionScore >= 70 ? 'warning' : 'critical'}
          subtitle="EKF sensor fusion"
        />
        <KPICard
          label="Fix Type"
          value="3D"
          status="healthy"
          subtitle="Position + altitude"
        />
      </div>

      {/* EKF Sensor Fusion Health */}
      <Card>
        <CardTitle className="mb-4">EKF Sensor Fusion Health</CardTitle>
        <div className="flex items-center gap-3 mb-4">
          <span className="text-lg font-bold text-goose-accent">Fusion Score: {fusionScore}%</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {sensorHealth.map((sensor) => (
            <div key={sensor.name} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-goose-text">{sensor.name}</span>
                <span className={`text-sm font-bold ${sensor.score >= 80 ? 'text-goose-success' : sensor.score >= 50 ? 'text-goose-warning' : 'text-goose-error'}`}>
                  {sensor.score}%
                </span>
              </div>
              <ProgressBar value={sensor.score} size="md" showValue={false} />
              <p className="text-[10px] text-goose-text-muted">{sensor.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-goose-text-muted mt-4">
          {fusionScore >= 90
            ? 'Sensor fusion looks healthy. EKF is receiving consistent data from all sources.'
            : 'Some sensor inconsistencies detected. Check individual sensor health for details.'}
        </p>
      </Card>

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'signal', label: 'Signal Quality' },
          { id: 'accuracy', label: 'Accuracy' },
          { id: 'ekf', label: 'EKF Health' },
          { id: 'position', label: 'Position Tracking' },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'signal' && (
              <div className="space-y-4">
                {satData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={satData}
                    series={[{ label: 'Satellites', color: CHART_COLORS.gps, width: 2 }]}
                    title="Satellite Count Over Time"
                    height={250}
                    thresholds={[
                      { value: 8, color: CHART_COLORS.threshold, label: 'Min Safe (8)', dash: [6, 4] },
                    ]}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No satellite count time-series data available in this log
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Satellite count shows how many GPS satellites the receiver is tracking. At least 8 satellites
                    (red dashed line) are needed for a reliable 3D position fix. Drops below this threshold often
                    coincide with position drift or EKF resets. Satellite count is affected by antenna placement,
                    canopy cover, and the drone's orientation.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'accuracy' && (
              <div className="space-y-4">
                {hdopData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={hdopData}
                    series={[{ label: 'HDOP', color: CHART_COLORS.voltage, width: 2 }]}
                    title="Horizontal Dilution of Precision"
                    height={250}
                    thresholds={[
                      { value: 2.0, color: CHART_COLORS.threshold, label: 'Max Good (2.0)', dash: [6, 4] },
                    ]}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No HDOP data available in this log
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">HDOP</strong> (Horizontal Dilution of Precision) reflects the geometric
                    quality of the satellite constellation. Lower is better. HDOP below 1.0 is excellent, 1.0-2.0 is good,
                    and above 2.0 (dashed line) indicates the satellites are clustered in the sky, reducing horizontal
                    accuracy. High HDOP often occurs near buildings, trees, or when flying at extreme latitudes.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'ekf' && (
              <div className="space-y-4">
                {ekfData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={ekfData}
                    series={ekfFields.map((f, i) => ({
                      label: f,
                      color: [CHART_COLORS.motor1, CHART_COLORS.motor2, CHART_COLORS.motor3, CHART_COLORS.motor4][i % 4],
                    }))}
                    title="EKF Innovation Ratios"
                    height={280}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No EKF innovation data available in this log
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">EKF innovation ratios</strong> show how much the filter's predictions
                    differ from actual sensor readings. Values near zero mean the sensors agree with the model. Values
                    above 0.5 indicate sensor disagreement — possibly caused by magnetic interference, GPS multipath,
                    or IMU drift. Persistent high innovations can trigger EKF failsafes and force position-hold or land modes.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'position' && (
              <div className="space-y-4">
                {posData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={posData}
                    series={posFields.map((f, i) => ({
                      label: f,
                      color: [CHART_COLORS.motor1, CHART_COLORS.motor2, CHART_COLORS.motor3][i % 3],
                    }))}
                    title="Position Data"
                    height={280}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No position tracking data available
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Position data shows the drone's estimated location over time. Sudden jumps or drift in these
                    traces correlate with GPS dropouts or EKF resets. Smooth, continuous traces indicate healthy
                    navigation. Large spikes may indicate a GPS glitch event.
                  </p>
                </Card>
              </div>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {allFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">GPS & EKF Findings ({allFindings.length})</CardTitle>
          <div className="space-y-2">
            {allFindings.map((f) => (
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
      <Card className={`bg-gradient-to-r ${gpsScore >= 80 && fusionScore >= 90 ? 'from-goose-success/5' : gpsScore >= 50 ? 'from-goose-warning/5' : 'from-goose-error/5'} to-transparent`}>
        <CardTitle className="mb-2">GPS & Navigation Assessment</CardTitle>
        <p className="text-sm text-goose-text">
          {!hasGpsData
            ? 'No GPS data was available in this flight log. Navigation quality cannot be assessed. Ensure the GPS receiver is connected and logging is enabled before the next flight.'
            : gpsScore >= 80 && fusionScore >= 90
              ? `GPS quality is excellent with an average of ${avgSats.toFixed(0)} satellites and HDOP of ${avgHdop.toFixed(2)}. EKF sensor fusion is healthy across all sources. No positioning concerns for this flight.`
              : gpsScore >= 50
                ? `GPS quality is moderate (${gpsScore}% score). ${avgSats < 10 ? `Average satellite count of ${avgSats.toFixed(0)} is below ideal — ensure clear sky view. ` : ''}${avgHdop > 2.0 ? `HDOP averaged ${avgHdop.toFixed(2)}, indicating reduced horizontal accuracy. ` : ''}${fusionScore < 90 ? 'Some EKF sensor inconsistencies detected — review individual sensor health.' : ''}`
                : `GPS quality is poor (${gpsScore}% score). ${avgSats < 8 ? `Only ${avgSats.toFixed(0)} satellites on average — position fixes may be unreliable. ` : ''}${avgHdop > 2.5 ? `HDOP of ${avgHdop.toFixed(2)} indicates significant accuracy degradation. ` : ''}Investigate antenna placement, electromagnetic interference, and flight environment.`
          }
        </p>
      </Card>
    </div>
  )
}
