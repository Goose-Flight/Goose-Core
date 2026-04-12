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

  const { timeseries, findings } = currentAnalysis
  const battFindings = findingsByPlugin(findings, 'battery_sag')
  const severity = worstSeverity(battFindings)

  const battStream = timeseries.battery
  const voltage = (battStream?.voltage as number[]) || []
  const current = (battStream?.current as number[]) || []
  const remaining = (battStream?.remaining_pct as number[]) || []
  const temperature = (battStream?.temperature as number[]) || []

  const startV = voltage[0] || 0
  const minV = voltage.length ? min(voltage) : 0
  const voltageSag = startV - minV
  const avgCurrent = avg(current)
  const maxCurrent = max(current)
  const finalPct = remaining.length ? remaining[remaining.length - 1] : 0
  const maxTemp = temperature.length ? max(temperature) : 0
  const avgTemp = temperature.length ? avg(temperature) : 0

  // Estimate cell count from voltage
  const cellCount = startV > 0 ? Math.round(startV / 4.2) : 4
  const cellVoltage = voltage.length ? minV / cellCount : 0

  // Chart data
  const { data: voltData } = buildChartData(timeseries, 'battery', ['voltage'])
  const { data: currentData } = buildChartData(timeseries, 'battery', ['current'])
  const { data: remainingData } = buildChartData(timeseries, 'battery', ['remaining_pct'])
  const { data: tempData } = buildChartData(timeseries, 'battery', ['temperature'])

  // Battery health based on sag
  const battHealth = voltageSag < 1 ? 'healthy' : voltageSag < 2 ? 'warning' : 'critical'
  const battLabel = voltageSag < 1 ? 'Healthy' : voltageSag < 2 ? 'Aging' : 'Replace'

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
          <p className="text-sm text-goose-text-muted mt-1">{cellCount}S LiPo estimated</p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* Hero KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Battery Icon Card */}
        <Card className="flex flex-col items-center justify-center py-4">
          <div className="relative w-16 h-28 border-2 border-goose-text-muted rounded-lg overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 w-6 h-2 bg-goose-text-muted rounded-t-sm" />
            <div
              className={`absolute bottom-0 w-full transition-all duration-1000 ${
                finalPct > 50 ? 'bg-goose-success' : finalPct > 20 ? 'bg-goose-warning' : 'bg-goose-error'
              }`}
              style={{ height: `${finalPct}%` }}
            />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-sm font-bold text-white drop-shadow">{finalPct.toFixed(0)}%</span>
            </div>
          </div>
          <Badge variant={battHealth === 'healthy' ? 'success' : battHealth === 'warning' ? 'warning' : 'error'} className="mt-2">
            {battLabel}
          </Badge>
        </Card>

        {/* Voltage */}
        <Card>
          <div className="text-xs text-goose-text-muted uppercase tracking-wide mb-2">Voltage</div>
          <div className="text-2xl font-bold text-goose-text">{minV.toFixed(2)}V</div>
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
            <ProgressBar value={Math.max(0, 100 - (voltageSag / startV) * 100)} size="sm" />
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
              <span className="text-goose-text-muted">Maximum</span>
              <span className="font-mono text-goose-error">{maxCurrent.toFixed(1)}A</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Consumed</span>
              <span className="font-mono text-goose-text">{((avgCurrent * (currentAnalysis.metadata.duration_sec / 3600)) * 1000).toFixed(0)} mAh</span>
            </div>
          </div>
        </Card>

        {/* Temperature */}
        <Card>
          <div className="text-xs text-goose-text-muted uppercase tracking-wide mb-2">Temperature</div>
          <div className="text-2xl font-bold text-goose-text">{maxTemp.toFixed(1)}°C</div>
          <div className="mt-2 space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Maximum</span>
              <span className={`font-mono ${maxTemp > 60 ? 'text-goose-error' : 'text-goose-text'}`}>{maxTemp.toFixed(1)}°C</span>
            </div>
            <div className="flex justify-between">
              <span className="text-goose-text-muted">Average</span>
              <span className="font-mono text-goose-text">{avgTemp.toFixed(1)}°C</span>
            </div>
            <ProgressBar value={Math.min(100, (maxTemp / 80) * 100)} size="sm" color={maxTemp > 60 ? 'error' : maxTemp > 45 ? 'warning' : 'success'} showValue={false} />
          </div>
        </Card>
      </div>

      {/* Cell Balance (estimated) */}
      <Card>
        <CardTitle className="mb-3">
          Cell Balance (estimated)
          <span className="text-xs text-goose-text-muted font-normal ml-2">
            Estimated from total pack voltage &mdash; {cellCount}S detected
          </span>
        </CardTitle>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
          {Array.from({ length: cellCount }).map((_, i) => (
            <Card key={i} padding="sm" className="text-center">
              <div className="text-[10px] text-goose-text-muted uppercase">Cell {i + 1}</div>
              <div className="text-lg font-bold font-mono text-goose-text mt-1">{cellVoltage.toFixed(2)}V</div>
              <ProgressBar
                value={((cellVoltage - 3.0) / (4.2 - 3.0)) * 100}
                size="sm"
                showValue={false}
                className="mt-1"
              />
            </Card>
          ))}
        </div>
      </Card>

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'voltage', label: 'Voltage' },
          { id: 'current', label: 'Current' },
          { id: 'capacity', label: 'Capacity' },
          { id: 'temperature', label: 'Temperature' },
          { id: 'sag', label: 'Sag Analysis' },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'voltage' && (
              <TimeSeriesChart
                data={voltData}
                series={[{ label: 'Voltage (V)', color: CHART_COLORS.voltage, width: 2 }]}
                title="Battery Voltage Over Time"
                height={280}
                thresholds={[
                  { value: cellCount * 3.5, color: CHART_COLORS.threshold, label: 'Warning', dash: [6, 4] },
                  { value: cellCount * 3.3, color: '#DC2626', label: 'Critical', dash: [4, 2] },
                ]}
              />
            )}
            {tab === 'current' && (
              <TimeSeriesChart
                data={currentData}
                series={[{ label: 'Current (A)', color: CHART_COLORS.current, width: 2 }]}
                title="Current Draw Over Time"
                height={280}
              />
            )}
            {tab === 'capacity' && (
              <TimeSeriesChart
                data={remainingData}
                series={[{ label: 'Remaining (%)', color: CHART_COLORS.gps, width: 2 }]}
                title="Battery Remaining (%)"
                height={280}
                thresholds={[
                  { value: 20, color: CHART_COLORS.threshold, label: '20% Warning', dash: [6, 4] },
                ]}
              />
            )}
            {tab === 'temperature' && (
              <TimeSeriesChart
                data={tempData}
                series={[{ label: 'Temperature (°C)', color: CHART_COLORS.temperature, width: 2 }]}
                title="Battery Temperature"
                height={280}
                thresholds={[
                  { value: 60, color: CHART_COLORS.threshold, label: '60°C Max Safe', dash: [6, 4] },
                ]}
              />
            )}
            {tab === 'sag' && (
              <Card>
                <CardTitle className="mb-4">Voltage Sag Under Load</CardTitle>
                <div className="grid grid-cols-3 gap-4">
                  <KPICard label="Voltage Drop" value={`${voltageSag.toFixed(2)}V`} status={voltageSag > 2 ? 'critical' : voltageSag > 1 ? 'warning' : 'healthy'} />
                  <KPICard label="Per-Cell Sag" value={`${(voltageSag / cellCount).toFixed(3)}V`} status={voltageSag / cellCount > 0.3 ? 'warning' : 'healthy'} />
                  <KPICard label="Internal R (est)" value={avgCurrent > 0 ? `${((voltageSag / maxCurrent) * 1000).toFixed(0)}mΩ` : 'N/A'} subtitle="Estimated from V-I" />
                </div>
                <p className="text-xs text-goose-text-muted mt-3">
                  Note: Internal resistance is estimated from voltage-current regression during flight. Use a battery tester for precise measurements.
                </p>
              </Card>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {battFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Battery Findings</CardTitle>
          <div className="space-y-2">
            {battFindings.map((f) => (
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
