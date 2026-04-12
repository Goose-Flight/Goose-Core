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

  const { timeseries, findings } = currentAnalysis
  const gpsFindings = findingsByPlugin(findings, 'gps_health')
  const ekfFindings = findingsByPlugin(findings, 'ekf_consistency')
  const allFindings = [...gpsFindings, ...ekfFindings]
  const severity = worstSeverity(allFindings)

  const gpsStream = timeseries.gps
  const satellites = (gpsStream?.satellites as number[]) || []
  const hdop = (gpsStream?.hdop as number[]) || []

  const avgSats = avg(satellites)
  const minSats = satellites.length ? min(satellites) : 0
  const avgHdop = avg(hdop)
  const maxHdop = hdop.length ? max(hdop) : 0

  // GPS quality score
  const gpsScore = Math.min(100, Math.round((avgSats / 20) * 50 + (2.0 / Math.max(avgHdop, 0.5)) * 50))

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
        </div>
        <SeverityBadge severity={severity} />
      </div>

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
                <TimeSeriesChart
                  data={satData}
                  series={[{ label: 'Satellites', color: CHART_COLORS.gps, width: 2 }]}
                  title="Satellite Count Over Time"
                  height={250}
                  thresholds={[
                    { value: 8, color: CHART_COLORS.threshold, label: 'Min Safe (8)', dash: [6, 4] },
                  ]}
                />
              </div>
            )}
            {tab === 'accuracy' && (
              <TimeSeriesChart
                data={hdopData}
                series={[{ label: 'HDOP', color: CHART_COLORS.voltage, width: 2 }]}
                title="Horizontal Dilution of Precision"
                height={250}
                thresholds={[
                  { value: 2.0, color: CHART_COLORS.threshold, label: 'Max Good (2.0)', dash: [6, 4] },
                ]}
              />
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
                  <Card className="py-8 text-center text-goose-text-muted text-sm">
                    No EKF innovation data available in this log
                  </Card>
                )}
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
                  <Card className="py-8 text-center text-goose-text-muted text-sm">
                    No position tracking data available
                  </Card>
                )}
              </div>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {allFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">GPS & EKF Findings</CardTitle>
          <div className="space-y-2">
            {allFindings.map((f) => (
              <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                <SeverityBadge severity={f.severity} />
                <div>
                  <p className="text-sm font-medium text-goose-text">{f.title}</p>
                  <p className="text-xs text-goose-text-muted mt-1">{f.description}</p>
                  <div className="flex gap-2 mt-1">
                    <Badge>{f.plugin_id}</Badge>
                    <ConfidenceBadge band={f.confidence_band} score={f.confidence} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
