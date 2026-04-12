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

  const { timeseries, findings, metadata } = currentAnalysis
  const attFindings = findingsByPlugin(findings, 'attitude_tracking')
  const posFindings = findingsByPlugin(findings, 'position_tracking')
  const rcFindings = findingsByPlugin(findings, 'rc_signal')
  const opFindings = findingsByPlugin(findings, 'operator_action_sequence')
  const allFindings = [...attFindings, ...posFindings, ...rcFindings, ...opFindings]
  const severity = worstSeverity(allFindings)

  // Attitude data
  const { data: attData, fieldNames: attFields } = buildChartData(timeseries, 'attitude')
  const { data: attSpData, fieldNames: attSpFields } = buildChartData(timeseries, 'attitude_setpoint')

  const hasAttitudeData = attData[0].length > 0
  const hasRcData = !!(timeseries.rc_input || timeseries.rc_channels)

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
  const rollStd = roll.length > 0 ? stdDev(roll.map(r => r * (180 / Math.PI))) : 0
  const pitchStd = pitch.length > 0 ? stdDev(pitch.map(p => p * (180 / Math.PI))) : 0

  // Manual control / stick inputs
  const { data: stickData, fieldNames: stickFields } = buildChartData(timeseries, 'manual_control')

  const noData = !hasAttitudeData && !hasRcData

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
            {metadata.vehicle_type} &middot; {metadata.autopilot.toUpperCase()}
            {metadata.duration_sec ? ` \u00b7 ${(metadata.duration_sec / 60).toFixed(1)} min` : ''}
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* No data warning */}
      {noData && (
        <Card className="border-goose-warning/30 bg-gradient-to-r from-goose-warning/5 to-transparent">
          <div className="flex items-start gap-3">
            <span className="text-2xl">⚠️</span>
            <div>
              <p className="text-sm font-medium text-goose-warning">Limited Control Data</p>
              <p className="text-xs text-goose-text-muted mt-1">
                This flight log does not contain attitude or RC input streams. The flight controller may not have been
                logging control data, or the aircraft was not armed during this recording. Statistics below may show
                default values.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Explanation Card */}
      <Card className="bg-gradient-to-br from-goose-chart-1/5 to-transparent">
        <CardTitle className="mb-2">What This Page Shows</CardTitle>
        <p className="text-xs text-goose-text-muted leading-relaxed">
          Control analysis evaluates how well the flight controller tracks commanded attitudes and how reliably the RC link performs.
          <strong className="text-goose-text"> Attitude tracking</strong> compares actual roll/pitch/yaw to the commanded setpoints — large deviations indicate tuning problems, mechanical issues, or wind disturbance.
          <strong className="text-goose-text"> RC signal quality</strong> measures RSSI and channel integrity — dropouts or low RSSI can cause failsafe triggers.
          <strong className="text-goose-text"> Operator actions</strong> reconstruct what the pilot commanded during flight, which is critical for incident analysis.
        </p>
      </Card>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Attitude Tracking"
          value={roll.length > 0 ? (rollStd < 3 && pitchStd < 3 ? 'Good' : rollStd < 8 ? 'Fair' : 'Poor') : 'N/A'}
          status={roll.length > 0 ? (rollStd < 3 && pitchStd < 3 ? 'healthy' : rollStd < 8 ? 'warning' : 'critical') : 'neutral'}
          subtitle={roll.length > 0 ? `Roll \u03c3: ${rollStd.toFixed(1)}\u00b0 | Pitch \u03c3: ${pitchStd.toFixed(1)}\u00b0` : 'No attitude data'}
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
                  <Card className="py-12 text-center text-goose-text-muted text-sm">No attitude data available in this log</Card>
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
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">Attitude</strong> shows the aircraft's actual orientation (roll, pitch, yaw) over time.
                    The <strong className="text-goose-text">setpoint</strong> chart (dashed lines) shows what the flight controller was commanded
                    to achieve. The difference between actual and setpoint is the tracking error. Large or sustained
                    errors indicate PID tuning issues, mechanical problems, or excessive wind loading. A well-tuned
                    aircraft should track setpoints within 1-2 degrees during stable flight.
                  </p>
                </Card>
                {attFindings.length > 0 && (
                  <Card>
                    <CardTitle className="mb-3">Attitude Findings ({attFindings.length})</CardTitle>
                    <div className="space-y-2">
                      {attFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className="text-sm text-goose-text">{f.title}</p>
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
            )}
            {tab === 'position' && (
              <div className="space-y-4">
                {posFindings.length > 0 ? (
                  <Card>
                    <CardTitle className="mb-3">Position Tracking Findings ({posFindings.length})</CardTitle>
                    <div className="space-y-2">
                      {posFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className="text-sm text-goose-text">{f.title}</p>
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
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    Position tracking analysis found no issues.
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Position tracking evaluates how well the aircraft holds its commanded position during GPS-assisted
                    flight modes (Loiter, PosHold, Auto). Drift beyond acceptable thresholds may indicate GPS issues,
                    wind exceeding the aircraft's capabilities, or poor EKF estimation.
                  </p>
                </Card>
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
                  <Card className="py-12 text-center text-goose-text-muted text-sm">No RC input data available in this log</Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">RC channels</strong> show the raw stick and switch inputs from the transmitter.
                    Channels 1-4 are typically roll, pitch, throttle, and yaw. Higher channels control flight modes and auxiliary functions.
                    Sudden drops to zero or erratic values indicate signal loss or interference. RSSI below 50% warrants
                    a range check. Persistent glitches suggest antenna issues or electromagnetic interference.
                  </p>
                </Card>
                {rcFindings.length > 0 && (
                  <Card>
                    <CardTitle className="mb-3">RC Signal Findings ({rcFindings.length})</CardTitle>
                    <div className="space-y-2">
                      {rcFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className="text-sm text-goose-text">{f.title}</p>
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
                  <Card className="py-12 text-center text-goose-text-muted text-sm">No manual control data available in this log</Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    <strong className="text-goose-text">Stick inputs</strong> show the normalized pilot commands (-1 to +1 range).
                    These represent what the operator was commanding at each moment. Rapid, full-deflection inputs during
                    an incident may indicate panic response. Gentle, centered inputs during unstable flight suggest the
                    issue is mechanical or environmental, not pilot-induced. This data is essential for incident reconstruction.
                  </p>
                </Card>
                {opFindings.length > 0 && (
                  <Card>
                    <CardTitle className="mb-3">Operator Action Findings ({opFindings.length})</CardTitle>
                    <div className="space-y-2">
                      {opFindings.map((f) => (
                        <div key={f.finding_id} className="flex items-start gap-3 p-3 rounded-lg bg-goose-bg border border-goose-border">
                          <SeverityBadge severity={f.severity} />
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className="text-sm text-goose-text">{f.title}</p>
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
            )}
          </>
        )}
      </Tabs>

      {/* Assessment */}
      <Card className={`bg-gradient-to-r ${rollStd < 3 && pitchStd < 3 && rcQuality >= 80 ? 'from-goose-success/5' : allFindings.some(f => f.severity === 'critical') ? 'from-goose-error/5' : 'from-goose-warning/5'} to-transparent`}>
        <CardTitle className="mb-2">Control System Assessment</CardTitle>
        <p className="text-sm text-goose-text">
          {noData
            ? 'No control data was available in this flight log. Attitude tracking and RC signal quality cannot be assessed. Ensure the flight controller is logging attitude, RC input, and manual control streams.'
            : rollStd < 3 && pitchStd < 3 && rcQuality >= 80 && allFindings.length === 0
              ? `Control system is performing well. Attitude tracking is tight (roll \u03c3: ${rollStd.toFixed(1)}\u00b0, pitch \u03c3: ${pitchStd.toFixed(1)}\u00b0) and RC signal quality is strong at ${rcQuality}%. No control-related issues detected.`
              : rollStd < 8 && rcQuality >= 50
                ? `Control performance is acceptable but has room for improvement. ${rollStd >= 3 || pitchStd >= 3 ? `Attitude variation is moderate (roll \u03c3: ${rollStd.toFixed(1)}\u00b0, pitch \u03c3: ${pitchStd.toFixed(1)}\u00b0) — consider PID tuning adjustments. ` : ''}${rcQuality < 80 ? `RC signal quality is at ${rcQuality}% — verify antenna placement and range. ` : ''}${allFindings.length > 0 ? `${allFindings.length} finding(s) require attention.` : ''}`
                : `Control system needs attention. ${rollStd >= 8 ? `High attitude variation detected (roll \u03c3: ${rollStd.toFixed(1)}\u00b0, pitch \u03c3: ${pitchStd.toFixed(1)}\u00b0) — the aircraft is struggling to maintain stable orientation. ` : ''}${rcQuality < 50 ? `RC signal quality is poor at ${rcQuality}% — risk of failsafe activation. ` : ''}${allFindings.filter(f => f.severity === 'critical').length > 0 ? 'Critical findings detected — review each finding carefully before the next flight.' : ''}`
          }
        </p>
      </Card>
    </div>
  )
}
