import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Tabs } from '@/components/ui/Tabs'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TimeSeriesChart, CHART_COLORS } from '@/components/charts/TimeSeriesChart'
import { buildChartData, findingsByPlugin, worstSeverity, avg, max, stdDev } from '@/lib/streams'

export function ControlAnalysis() {
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
  const attFindings = findingsByPlugin(findings, 'attitude_tracking')
  const posFindings = findingsByPlugin(findings, 'position_tracking')
  const rcFindings = findingsByPlugin(findings, 'rc_signal')
  const opFindings = findingsByPlugin(findings, 'operator_action_sequence')
  const allFindings = [...attFindings, ...posFindings, ...rcFindings, ...opFindings]
  const severity = worstSeverity(allFindings)

  // Attitude data
  const { data: attData, fieldNames: attFields } = buildChartData(timeseries, 'attitude')
  const { data: attSpData, fieldNames: attSpFields } = buildChartData(timeseries, 'attitude_setpoint')

  // RC data
  const rcStream = timeseries.rc_input || timeseries.rc_channels
  const rcStreamName = timeseries.rc_input ? 'rc_input' : 'rc_channels'
  const { data: rcData, fieldNames: rcFields } = buildChartData(timeseries, rcStreamName)
  const rssi = (rcStream?.rssi as number[]) || []
  const avgRssi = avg(rssi)

  // RC signal quality
  const rcQuality = avgRssi > 0 ? Math.min(100, Math.round(avgRssi)) : 90

  // Attitude tracking - compute error if we have both actual and setpoint
  const attStream = timeseries.attitude
  const roll = (attStream?.roll as number[]) || []
  const pitch = (attStream?.pitch as number[]) || []
  const rollStd = stdDev(roll.map(r => r * (180 / Math.PI))) // Convert to degrees
  const pitchStd = stdDev(pitch.map(p => p * (180 / Math.PI)))

  // Manual control / stick inputs
  const { data: stickData, fieldNames: stickFields } = buildChartData(timeseries, 'manual_control')

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
            &larr; Back to Results
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            <span className="text-3xl">🎮</span> Control Analysis
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            Attitude tracking, RC signal quality, and operator inputs
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Attitude Tracking"
          value={rollStd < 3 && pitchStd < 3 ? 'Good' : rollStd < 8 ? 'Fair' : 'Poor'}
          status={rollStd < 3 && pitchStd < 3 ? 'healthy' : rollStd < 8 ? 'warning' : 'critical'}
          subtitle={`Roll σ: ${rollStd.toFixed(1)}° | Pitch σ: ${pitchStd.toFixed(1)}°`}
        />
        <KPICard
          label="RC Signal"
          value={`${rcQuality}%`}
          status={rcQuality >= 80 ? 'healthy' : rcQuality >= 50 ? 'warning' : 'critical'}
          subtitle={avgRssi > 0 ? `RSSI: ${avgRssi.toFixed(0)}` : 'Signal quality'}
        />
        <KPICard
          label="Attitude Findings"
          value={attFindings.length}
          status={attFindings.some(f => f.severity === 'critical') ? 'critical' : attFindings.some(f => f.severity === 'warning') ? 'warning' : 'healthy'}
          subtitle="Tracking errors detected"
        />
        <KPICard
          label="RC Findings"
          value={rcFindings.length}
          status={rcFindings.some(f => f.severity === 'critical') ? 'critical' : 'healthy'}
          subtitle="Signal issues detected"
        />
      </div>

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'attitude', label: 'Attitude', badge: attFindings.length || undefined },
          { id: 'position', label: 'Position', badge: posFindings.length || undefined },
          { id: 'rc', label: 'RC Signal', badge: rcFindings.length || undefined },
          { id: 'operator', label: 'Operator Actions', badge: opFindings.length || undefined },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'attitude' && (
              <div className="space-y-4">
                {attData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={attData}
                    series={attFields.map((f, i) => ({
                      label: f,
                      color: [CHART_COLORS.roll, CHART_COLORS.pitch, CHART_COLORS.yaw][i % 3],
                      width: 2,
                    }))}
                    title="Attitude (Roll / Pitch / Yaw)"
                    height={300}
                  />
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">No attitude data available</Card>
                )}
                {attSpData[0].length > 0 && (
                  <TimeSeriesChart
                    data={attSpData}
                    series={attSpFields.map((f, i) => ({
                      label: `${f} (setpoint)`,
                      color: [CHART_COLORS.roll, CHART_COLORS.pitch, CHART_COLORS.yaw][i % 3],
                      width: 1,
                      dash: [4, 4],
                    }))}
                    title="Attitude Setpoint (commanded)"
                    height={250}
                  />
                )}
                {attFindings.length > 0 && (
                  <Card>
                    <CardTitle className="mb-3">Attitude Findings</CardTitle>
                    <div className="space-y-2">
                      {attFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div>
                            <p className="text-sm text-goose-text">{f.title}</p>
                            <p className="text-xs text-goose-text-muted mt-1">{f.description}</p>
                            <ConfidenceBadge band={f.confidence_band} score={f.confidence} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            )}
            {tab === 'position' && (
              <div className="space-y-4">
                {posFindings.length > 0 ? (
                  <Card>
                    <CardTitle className="mb-3">Position Tracking Findings</CardTitle>
                    <div className="space-y-2">
                      {posFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div>
                            <p className="text-sm text-goose-text">{f.title}</p>
                            <p className="text-xs text-goose-text-muted mt-1">{f.description}</p>
                            <ConfidenceBadge band={f.confidence_band} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">
                    Position tracking analysis found no issues.
                  </Card>
                )}
              </div>
            )}
            {tab === 'rc' && (
              <div className="space-y-4">
                {rcData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={rcData}
                    series={rcFields.slice(0, 6).map((f, i) => ({
                      label: f,
                      color: [CHART_COLORS.motor1, CHART_COLORS.motor2, CHART_COLORS.motor3, CHART_COLORS.motor4, CHART_COLORS.motor5, CHART_COLORS.rc][i],
                    }))}
                    title="RC Channel Inputs"
                    height={280}
                  />
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">No RC input data available</Card>
                )}
                {rcFindings.length > 0 && (
                  <Card>
                    <CardTitle className="mb-3">RC Signal Findings</CardTitle>
                    <div className="space-y-2">
                      {rcFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div>
                            <p className="text-sm text-goose-text">{f.title}</p>
                            <p className="text-xs text-goose-text-muted mt-1">{f.description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            )}
            {tab === 'operator' && (
              <div className="space-y-4">
                {stickData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={stickData}
                    series={stickFields.map((f, i) => ({
                      label: f,
                      color: [CHART_COLORS.motor1, CHART_COLORS.motor2, CHART_COLORS.motor3, CHART_COLORS.motor4][i % 4],
                    }))}
                    title="Stick Inputs (Manual Control)"
                    height={280}
                  />
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">No manual control data available</Card>
                )}
                {opFindings.length > 0 && (
                  <Card>
                    <CardTitle className="mb-3">Operator Action Findings</CardTitle>
                    <div className="space-y-2">
                      {opFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div>
                            <p className="text-sm text-goose-text">{f.title}</p>
                            <p className="text-xs text-goose-text-muted mt-1">{f.description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            )}
          </>
        )}
      </Tabs>
    </div>
  )
}
