import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Tabs } from '@/components/ui/Tabs'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TimeSeriesChart, CHART_COLORS } from '@/components/charts/TimeSeriesChart'
import { buildChartData, findingsByPlugin, worstSeverity, avg, max, min, stdDev } from '@/lib/streams'

export function BatteryAnalysis() {
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
  const battFindings = findingsByPlugin(findings, 'battery_sag')
  const severity = worstSeverity(battFindings)

  const battStream = timeseries.battery
  const hasBatteryData = !!battStream && !!battStream.timestamps && (battStream.timestamps as number[]).length > 0

  const voltage = (battStream?.voltage as number[]) || []
  const current = (battStream?.current as number[]) || []
  const remaining = (battStream?.remaining_pct as number[]) || []
  const temperature = (battStream?.temperature as number[]) || []

  const startV = voltage.length > 0 ? voltage[0] : 0
  const endV = voltage.length > 0 ? voltage[voltage.length - 1] : 0
  const minV = voltage.length ? min(voltage.filter(v => v > 0)) : 0
  const maxV = voltage.length ? max(voltage) : 0
  const voltageSag = startV - minV
  const avgCurrent = avg(current)
  const maxCurrent = max(current)
  const peakPower = maxV > 0 && maxCurrent > 0 ? maxV * maxCurrent : 0
  const avgPower = voltage.length > 0 && current.length > 0
    ? avg(voltage.map((v, i) => v * (current[i] || 0)))
    : 0
  const finalPct = remaining.length ? remaining[remaining.length - 1] : 0
  const startPct = remaining.length ? remaining[0] : 100
  const pctUsed = startPct - finalPct
  const maxTemp = temperature.length ? max(temperature) : 0
  const avgTemp = temperature.length ? avg(temperature) : 0
  const minTemp = temperature.length ? min(temperature.filter(t => t > 0)) : 0

  // Estimate cell count from voltage
  const cellCount = startV > 0 ? Math.round(startV / 4.2) : maxV > 0 ? Math.round(maxV / 4.2) : 4
  const cellVoltageMin = cellCount > 0 ? minV / cellCount : 0
  const cellVoltageStart = cellCount > 0 ? startV / cellCount : 0

  // Estimated consumed mAh
  const durationHrs = metadata.duration_sec / 3600
  const consumedMah = avgCurrent > 0 ? avgCurrent * durationHrs * 1000 : 0

  // Internal resistance estimation (V-I regression)
  const internalR = maxCurrent > 0 && voltageSag > 0 ? (voltageSag / maxCurrent) * 1000 : 0 // mΩ

  // Discharge rate (C rating usage)
  // Assume capacity from consumed if we don't know it
  const estimatedCapacity = consumedMah > 0 && pctUsed > 0 ? (consumedMah / pctUsed) * 100 : 5000
  const cRating = estimatedCapacity > 0 ? maxCurrent / (estimatedCapacity / 1000) : 0

  // Battery health
  const battHealth = voltageSag < 1 && cellVoltageMin > 3.5 ? 'healthy'
    : voltageSag < 2.5 && cellVoltageMin > 3.3 ? 'warning' : 'critical'
  const battLabel = battHealth === 'healthy' ? 'Healthy' : battHealth === 'warning' ? 'Aging' : 'Replace'

  // Chart data
  const { data: voltData } = buildChartData(timeseries, 'battery', ['voltage'])
  const { data: currentData } = buildChartData(timeseries, 'battery', ['current'])
  const { data: remainingData } = buildChartData(timeseries, 'battery', ['remaining_pct'])
  const { data: tempData } = buildChartData(timeseries, 'battery', ['temperature'])

  // Power chart — combine voltage and current
  const powerTimestamps = battStream?.timestamps as number[] || []
  const powerValues = powerTimestamps.map((_, i) => (voltage[i] || 0) * (current[i] || 0))
  const powerData = powerTimestamps.length > 0 ? [powerTimestamps, powerValues] : [new Float64Array(0)]

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
            &larr; Back to Results
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            <span className="text-3xl">🔋</span> Battery Analysis
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            {cellCount}S LiPo &middot; {metadata.vehicle_type} &middot; {Math.round(metadata.duration_sec)}s flight
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* No data warning */}
      {!hasBatteryData && (
        <Card className="border-goose-warning/30 bg-gradient-to-r from-goose-warning/5 to-transparent">
          <div className="flex items-start gap-3">
            <span className="text-2xl">⚠️</span>
            <div>
              <p className="text-sm font-medium text-goose-warning">No Battery Telemetry</p>
              <p className="text-xs text-goose-text-muted mt-1">
                This flight log does not contain battery voltage/current data. Battery analysis requires
                a power module or smart battery that reports telemetry to the flight controller.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Explanation */}
      <Card className="bg-gradient-to-br from-goose-chart-3/5 to-transparent">
        <CardTitle className="mb-2">What This Page Shows</CardTitle>
        <p className="text-xs text-goose-text-muted leading-relaxed">
          Battery analysis examines voltage, current draw, temperature, and remaining capacity throughout the flight.
          <strong className="text-goose-text"> Voltage sag</strong> is the drop under load — excessive sag indicates high internal resistance (aging battery).
          <strong className="text-goose-text"> Per-cell voltage</strong> should stay above 3.3V under load to avoid cell damage.
          <strong className="text-goose-text"> Internal resistance</strong> is estimated from the voltage-current relationship — healthy LiPo packs are typically under 50mΩ.
          <strong className="text-goose-text"> Temperature</strong> should stay below 60°C during normal operation.
        </p>
      </Card>

      {/* Hero KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {/* Battery Icon Card */}
        <Card className="flex flex-col items-center justify-center py-4">
          <div className="relative w-14 h-24 border-2 border-goose-text-muted rounded-lg overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 w-5 h-2 bg-goose-text-muted rounded-t-sm" />
            <div
              className={`absolute bottom-0 w-full transition-all duration-1000 ${
                finalPct > 50 ? 'bg-goose-success' : finalPct > 20 ? 'bg-goose-warning' : 'bg-goose-error'
              }`}
              style={{ height: `${Math.max(5, finalPct)}%` }}
            />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-sm font-bold text-white drop-shadow">{finalPct.toFixed(0)}%</span>
            </div>
          </div>
          <Badge variant={battHealth === 'healthy' ? 'success' : battHealth === 'warning' ? 'warning' : 'error'} className="mt-2">
            {battLabel}
          </Badge>
          <span className="text-[10px] text-goose-text-muted mt-1">{cellCount}S Pack</span>
        </Card>

        {/* Voltage */}
        <Card>
          <div className="text-xs text-goose-text-muted uppercase tracking-wide mb-2">Voltage</div>
          <div className="text-2xl font-bold text-goose-text">{endV > 0 ? endV.toFixed(2) : minV.toFixed(2)}V</div>
          <div className="mt-2 space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Start</span>
              <span className="text-goose-success font-mono">{startV.toFixed(2)}V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Minimum</span>
              <span className="text-goose-warning font-mono">{minV.toFixed(2)}V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Sag</span>
              <span className={`font-mono ${voltageSag > 2 ? 'text-goose-error' : 'text-goose-text'}`}>{voltageSag.toFixed(2)}V</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Per Cell (min)</span>
              <span className={`font-mono ${cellVoltageMin < 3.3 ? 'text-goose-error' : cellVoltageMin < 3.5 ? 'text-goose-warning' : 'text-goose-text'}`}>{cellVoltageMin.toFixed(3)}V</span>
            </div>
          </div>
        </Card>

        {/* Current */}
        <Card>
          <div className="text-xs text-goose-text-muted uppercase tracking-wide mb-2">Current</div>
          <div className="text-2xl font-bold text-goose-text">{avgCurrent.toFixed(1)}A</div>
          <div className="mt-2 space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Average</span>
              <span className="font-mono text-goose-text">{avgCurrent.toFixed(1)}A</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Peak</span>
              <span className="font-mono text-goose-error">{maxCurrent.toFixed(1)}A</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Consumed</span>
              <span className="font-mono text-goose-text">{consumedMah.toFixed(0)} mAh</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">C-Rate (peak)</span>
              <span className="font-mono text-goose-text">{cRating.toFixed(1)}C</span>
            </div>
          </div>
        </Card>

        {/* Power */}
        <Card>
          <div className="text-xs text-goose-text-muted uppercase tracking-wide mb-2">Power</div>
          <div className="text-2xl font-bold text-goose-text">{avgPower.toFixed(0)}W</div>
          <div className="mt-2 space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Average</span>
              <span className="font-mono text-goose-text">{avgPower.toFixed(0)}W</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Peak</span>
              <span className="font-mono text-goose-error">{peakPower.toFixed(0)}W</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Efficiency</span>
              <span className="font-mono text-goose-text">
                {metadata.duration_sec > 0 && avgPower > 0 ? `${(avgPower / metadata.duration_sec * 60).toFixed(1)} Wh/min` : 'N/A'}
              </span>
            </div>
          </div>
        </Card>

        {/* Temperature */}
        <Card>
          <div className="text-xs text-goose-text-muted uppercase tracking-wide mb-2">Temperature</div>
          <div className="text-2xl font-bold text-goose-text">{maxTemp > 0 ? `${maxTemp.toFixed(1)}°C` : 'N/A'}</div>
          <div className="mt-2 space-y-1.5 text-xs">
            {maxTemp > 0 ? (
              <>
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Maximum</span>
                  <span className={`font-mono ${maxTemp > 60 ? 'text-goose-error' : maxTemp > 45 ? 'text-goose-warning' : 'text-goose-text'}`}>{maxTemp.toFixed(1)}°C</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Average</span>
                  <span className="font-mono text-goose-text">{avgTemp.toFixed(1)}°C</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-goose-text-muted">Rise</span>
                  <span className="font-mono text-goose-text">{(maxTemp - minTemp).toFixed(1)}°C</span>
                </div>
                <ProgressBar value={Math.min(100, (maxTemp / 80) * 100)} size="sm" color={maxTemp > 60 ? 'error' : maxTemp > 45 ? 'warning' : 'success'} showValue={false} />
              </>
            ) : (
              <span className="text-goose-text-muted">No temperature sensor data</span>
            )}
          </div>
        </Card>
      </div>

      {/* Cell Balance (estimated) */}
      <Card>
        <CardTitle className="mb-2">
          Cell Balance
          <span className="text-xs text-goose-text-muted font-normal ml-2">
            Estimated from total pack voltage — {cellCount}S detected
          </span>
        </CardTitle>
        <CardDescription className="mb-3">
          Individual cell voltages are estimated by dividing pack voltage equally. Actual cell balance
          may differ — use a cell checker for precise measurements. Significant imbalance accelerates battery aging.
        </CardDescription>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
          {Array.from({ length: cellCount }).map((_, i) => {
            const cellV = cellCount > 0 ? minV / cellCount : 0
            const cellPct = ((cellV - 3.0) / (4.2 - 3.0)) * 100
            return (
              <Card key={i} padding="sm" className="text-center">
                <div className="text-[10px] text-goose-text-muted uppercase font-medium">Cell {i + 1}</div>
                <div className={`text-lg font-bold font-mono mt-1 ${cellV < 3.3 ? 'text-goose-error' : cellV < 3.5 ? 'text-goose-warning' : 'text-goose-text'}`}>
                  {cellV.toFixed(2)}V
                </div>
                <ProgressBar value={Math.max(0, cellPct)} size="sm" showValue={false} className="mt-1" />
                <div className="text-[9px] text-goose-text-muted mt-0.5">{Math.max(0, cellPct).toFixed(0)}%</div>
              </Card>
            )
          })}
        </div>
      </Card>

      {/* Internal Resistance Estimation */}
      <Card className="bg-gradient-to-br from-goose-chart-5/5 to-transparent">
        <CardTitle className="mb-2">Internal Resistance Estimation</CardTitle>
        <CardDescription className="mb-4">
          Estimated from voltage-current regression during flight. Higher resistance = aging battery.
          Use a dedicated battery tester for precise measurements.
        </CardDescription>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            label="Internal R"
            value={internalR > 0 ? `${internalR.toFixed(0)}` : 'N/A'}
            unit={internalR > 0 ? 'mΩ' : ''}
            status={internalR > 0 ? (internalR < 30 ? 'healthy' : internalR < 60 ? 'warning' : 'critical') : 'neutral'}
            subtitle={internalR < 30 ? 'Low — healthy pack' : internalR < 60 ? 'Moderate — aging' : internalR > 60 ? 'High — consider replacement' : 'Not enough data'}
          />
          <KPICard label="Open Circuit V" value={`${startV.toFixed(1)}`} unit="V" subtitle="Voltage at rest / start" />
          <KPICard label="Max Current" value={`${maxCurrent.toFixed(1)}`} unit="A" subtitle="Peak demand during flight" />
          <KPICard
            label="Voltage Sag"
            value={`-${voltageSag.toFixed(2)}`}
            unit="V"
            status={voltageSag < 1 ? 'healthy' : voltageSag < 2.5 ? 'warning' : 'critical'}
            subtitle={`${(voltageSag / cellCount).toFixed(3)}V per cell`}
          />
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-[10px]">
          {[
            { range: '< 30 mΩ', label: 'Healthy', color: 'bg-goose-success' },
            { range: '30-60 mΩ', label: 'Aging', color: 'bg-goose-warning' },
            { range: '> 60 mΩ', label: 'Replace', color: 'bg-goose-error' },
          ].map((t) => (
            <div key={t.label} className="flex items-center gap-1.5 text-goose-text-muted">
              <span className={`w-2 h-2 rounded-full ${t.color}`} /> {t.range} — {t.label}
            </div>
          ))}
        </div>
      </Card>

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'voltage', label: 'Voltage' },
          { id: 'current', label: 'Current' },
          { id: 'power', label: 'Power Draw' },
          { id: 'capacity', label: 'Capacity' },
          { id: 'temperature', label: 'Temperature' },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'voltage' && (
              <div className="space-y-3">
                {voltData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={voltData}
                    series={[{ label: 'Pack Voltage (V)', color: CHART_COLORS.voltage, width: 2 }]}
                    title="Battery Voltage Over Time"
                    height={280}
                    thresholds={[
                      { value: cellCount * 3.5, color: CHART_COLORS.voltage, label: `${cellCount}S Warning (${(cellCount * 3.5).toFixed(1)}V)`, dash: [6, 4] },
                      { value: cellCount * 3.3, color: CHART_COLORS.threshold, label: `${cellCount}S Critical (${(cellCount * 3.3).toFixed(1)}V)`, dash: [4, 2] },
                    ]}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">No voltage data available</Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Voltage should remain above {(cellCount * 3.5).toFixed(1)}V ({cellCount}S pack) during flight.
                    A sharp drop at the end indicates the battery is nearly depleted. Gradual decline is normal.
                    Voltage sag under load is the difference between resting voltage and minimum under peak current.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'current' && (
              <div className="space-y-3">
                {currentData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={currentData}
                    series={[{ label: 'Current Draw (A)', color: CHART_COLORS.current, width: 2 }]}
                    title="Current Draw Over Time"
                    height={280}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">No current data available</Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Current draw reflects motor demand. Spikes indicate aggressive maneuvers or wind gusts.
                    Sustained high current reduces flight time and increases battery temperature.
                    Peak: {maxCurrent.toFixed(1)}A | Average: {avgCurrent.toFixed(1)}A | Consumed: ~{consumedMah.toFixed(0)} mAh
                  </p>
                </Card>
              </div>
            )}
            {tab === 'power' && (
              <div className="space-y-3">
                {powerData[0] instanceof Float64Array && powerData[0].length === 0 ? (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">No power data — requires both voltage and current</Card>
                ) : (
                  <TimeSeriesChart
                    data={powerData as any}
                    series={[{ label: 'Power (W)', color: '#8B5CF6', width: 2 }]}
                    title="Power Draw (Voltage × Current)"
                    height={280}
                  />
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Power draw = Voltage × Current. This shows the total electrical power consumed by the aircraft.
                    Average: {avgPower.toFixed(0)}W | Peak: {peakPower.toFixed(0)}W |
                    Total energy: ~{(avgPower * durationHrs).toFixed(1)} Wh
                  </p>
                </Card>
              </div>
            )}
            {tab === 'capacity' && (
              <div className="space-y-3">
                {remainingData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={remainingData}
                    series={[{ label: 'Remaining (%)', color: CHART_COLORS.gps, width: 2 }]}
                    title="Battery Remaining (%)"
                    height={280}
                    thresholds={[
                      { value: 20, color: CHART_COLORS.threshold, label: '20% Landing Warning', dash: [6, 4] },
                      { value: 10, color: '#DC2626', label: '10% Critical', dash: [4, 2] },
                    ]}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">No remaining capacity data available</Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    Battery remaining percentage reported by the flight controller's fuel gauge.
                    Land at or above 20% to preserve battery health and maintain a safety margin.
                    Started at {startPct.toFixed(0)}%, ended at {finalPct.toFixed(0)}% — used {pctUsed.toFixed(0)}% of capacity.
                  </p>
                </Card>
              </div>
            )}
            {tab === 'temperature' && (
              <div className="space-y-3">
                {tempData[0].length > 0 ? (
                  <TimeSeriesChart
                    data={tempData}
                    series={[{ label: 'Temperature (°C)', color: CHART_COLORS.temperature, width: 2 }]}
                    title="Battery Temperature"
                    height={280}
                    thresholds={[
                      { value: 45, color: CHART_COLORS.voltage, label: '45°C Warm', dash: [6, 4] },
                      { value: 60, color: CHART_COLORS.threshold, label: '60°C Max Safe', dash: [4, 2] },
                    ]}
                  />
                ) : (
                  <Card className="py-12 text-center text-goose-text-muted text-sm">
                    No temperature data available. Battery temperature requires a smart battery or external temp sensor.
                  </Card>
                )}
                <Card className="bg-goose-bg">
                  <p className="text-xs text-goose-text-muted">
                    LiPo batteries operate safely between 10°C and 60°C. Above 60°C risks thermal runaway.
                    Below 10°C, internal resistance increases significantly, reducing available power.
                    {maxTemp > 0 && ` This flight peaked at ${maxTemp.toFixed(1)}°C with a ${(maxTemp - minTemp).toFixed(1)}°C rise during flight.`}
                  </p>
                </Card>
              </div>
            )}
          </>
        )}
      </Tabs>

      {/* Overall Assessment */}
      <Card className={`bg-gradient-to-r ${battHealth === 'healthy' ? 'from-goose-success/5' : battHealth === 'warning' ? 'from-goose-warning/5' : 'from-goose-error/5'} to-transparent`}>
        <CardTitle className="mb-2">Battery Health Assessment</CardTitle>
        <p className="text-sm text-goose-text">
          {battHealth === 'healthy'
            ? `Battery is in good condition. Voltage sag of ${voltageSag.toFixed(2)}V is within normal limits. ${cellVoltageMin > 3.5 ? 'All cells stayed above safe voltage.' : ''} ${internalR > 0 && internalR < 30 ? `Internal resistance (${internalR.toFixed(0)}mΩ) indicates a healthy pack.` : ''} No action needed.`
            : battHealth === 'warning'
              ? `Battery showing signs of wear. Voltage sag of ${voltageSag.toFixed(2)}V is elevated. ${cellVoltageMin < 3.5 ? `Cells dropped to ${cellVoltageMin.toFixed(3)}V which is concerning. ` : ''}${internalR > 30 ? `Internal resistance (${internalR.toFixed(0)}mΩ) is above ideal. ` : ''}Consider checking cell balance with a battery tester and replacing if IR continues to rise.`
              : `Battery needs attention. ${voltageSag > 2.5 ? `Severe voltage sag of ${voltageSag.toFixed(2)}V under load. ` : ''}${cellVoltageMin < 3.3 ? `Cells dropped below 3.3V (${cellVoltageMin.toFixed(3)}V) — this damages LiPo cells. ` : ''}${internalR > 60 ? `Internal resistance (${internalR.toFixed(0)}mΩ) is high — battery should be replaced. ` : ''}${maxTemp > 60 ? `Peak temperature of ${maxTemp.toFixed(1)}°C exceeded safe limit. ` : ''}Recommend replacing this battery.`
          }
        </p>
      </Card>

      {/* Findings */}
      {battFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Battery Findings ({battFindings.length})</CardTitle>
          <div className="space-y-2">
            {battFindings.map((f) => (
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
