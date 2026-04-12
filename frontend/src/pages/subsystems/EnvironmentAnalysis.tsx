import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Tabs } from '@/components/ui/Tabs'
import { SeverityBadge, ConfidenceBadge, Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TimeSeriesChart, CHART_COLORS } from '@/components/charts/TimeSeriesChart'
import { buildChartData, findingsByPlugin, worstSeverity, avg, max } from '@/lib/streams'

const BEAUFORT_SCALE = [
  { max: 0.5, name: 'Calm', desc: 'Smoke rises vertically' },
  { max: 1.5, name: 'Light air', desc: 'Smoke drifts slowly' },
  { max: 3.3, name: 'Light breeze', desc: 'Leaves rustle' },
  { max: 5.5, name: 'Gentle breeze', desc: 'Leaves move constantly' },
  { max: 7.9, name: 'Moderate breeze', desc: 'Small branches move' },
  { max: 10.7, name: 'Fresh breeze', desc: 'Small trees sway' },
  { max: 13.8, name: 'Strong breeze', desc: 'Large branches move' },
  { max: 17.1, name: 'Near gale', desc: 'Whole trees sway' },
]

function getBeaufort(speed: number) {
  const level = BEAUFORT_SCALE.findIndex(b => speed <= b.max)
  return level >= 0 ? { level, ...BEAUFORT_SCALE[level] } : { level: 7, ...BEAUFORT_SCALE[7] }
}

function getWindDirection(degrees: number): string {
  const dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  return dirs[Math.round(degrees / 22.5) % 16]
}

function getOverallAssessment(avgWind: number, maxWind: number, gustFactor: number, hasBaroData: boolean): { label: string; color: string; summary: string } {
  if (avgWind > 10 || maxWind > 15) {
    return {
      label: 'Hazardous',
      color: 'text-goose-error',
      summary: 'Wind conditions exceeded safe operating thresholds. High average or peak gust speeds can destabilize the aircraft and degrade control authority.',
    }
  }
  if (avgWind > 5 || maxWind > 8 || gustFactor > 2) {
    return {
      label: 'Marginal',
      color: 'text-goose-warning',
      summary: 'Wind conditions were within flyable limits but may have contributed to increased motor load, reduced endurance, or degraded position hold accuracy.',
    }
  }
  return {
    label: 'Favorable',
    color: 'text-goose-success',
    summary: `Conditions were calm with steady winds. ${hasBaroData ? 'Barometric data corroborates stable atmospheric conditions.' : 'No barometric data was available to cross-reference.'}`,
  }
}

export function EnvironmentAnalysis() {
  const navigate = useNavigate()
  const { currentAnalysis } = useAnalysisStore()

  if (!currentAnalysis) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <Card className="text-center py-12">
          <div className="text-4xl mb-4">🌬️</div>
          <p className="text-goose-text font-medium">No Analysis Loaded</p>
          <p className="text-sm text-goose-text-muted mt-1">
            Run an analysis first to see environment and wind condition data.
          </p>
          <Button className="mt-4" onClick={() => navigate('/analyze')}>Run Analysis</Button>
        </Card>
      </div>
    )
  }

  const { timeseries, findings } = currentAnalysis
  const envFindings = findingsByPlugin(findings, 'environment_conditions')
  const severity = worstSeverity(envFindings)

  // Wind data
  const windStream = timeseries.wind
  const windSpeed = (windStream?.speed as number[]) || (windStream?.wind_speed as number[]) || []
  const windDir = (windStream?.direction as number[]) || (windStream?.wind_dir as number[]) || []

  const hasWindData = windSpeed.length > 0
  const avgWindSpeed = avg(windSpeed)
  const maxWindSpeed = max(windSpeed)
  const avgWindDir = avg(windDir)
  const gustFactor = avgWindSpeed > 0 ? maxWindSpeed / avgWindSpeed : 1
  const beaufort = getBeaufort(avgWindSpeed)
  const dirLabel = windDir.length > 0 ? getWindDirection(avgWindDir) : 'N/A'

  // Chart data
  const { data: windData } = buildChartData(timeseries, 'wind', ['speed', 'wind_speed'])

  // Barometer / temperature
  const { data: baroData, fieldNames: baroFields } = buildChartData(timeseries, 'barometer')
  const hasBaroData = baroData[0].length > 0

  const assessment = getOverallAssessment(avgWindSpeed, maxWindSpeed, gustFactor, hasBaroData)

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
            &larr; Back to Results
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            <span className="text-3xl">🌬️</span> Environment
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            Wind estimation, temperature, and flight conditions
          </p>
        </div>
        <SeverityBadge severity={severity} />
      </div>

      {/* What This Page Shows */}
      <Card className="bg-gradient-to-br from-goose-accent/5 to-transparent border-goose-accent/20">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-goose-accent/10 flex items-center justify-center shrink-0">
            <svg className="w-5 h-5 text-goose-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-goose-accent">What This Page Shows</p>
            <p className="text-xs text-goose-text-muted mt-1 leading-relaxed">
              This page analyzes environmental conditions during the flight. Wind speed and direction are
              estimated from the drone's tilt angle and GPS ground-speed difference (not from an onboard
              anemometer). Barometric data, when available, provides atmospheric pressure and temperature
              context. Together these help determine whether weather contributed to any anomalies.
            </p>
          </div>
        </div>
      </Card>

      {/* Wind Overview */}
      {hasWindData ? (
        <div className="grid grid-cols-12 gap-4">
          {/* Wind Compass */}
          <Card className="col-span-4 flex flex-col items-center justify-center py-6">
            <div className="relative w-32 h-32">
              {/* Compass ring */}
              <svg viewBox="0 0 100 100" className="w-full h-full">
                <circle cx="50" cy="50" r="45" fill="none" stroke="#1E293B" strokeWidth="2" />
                <circle cx="50" cy="50" r="35" fill="none" stroke="#1E293B" strokeWidth="1" strokeDasharray="2,4" />
                {/* Cardinal labels */}
                <text x="50" y="12" textAnchor="middle" fill="#94A3B8" fontSize="8" fontWeight="bold">N</text>
                <text x="90" y="53" textAnchor="middle" fill="#64748B" fontSize="7">E</text>
                <text x="50" y="95" textAnchor="middle" fill="#64748B" fontSize="7">S</text>
                <text x="10" y="53" textAnchor="middle" fill="#64748B" fontSize="7">W</text>
                {/* Wind arrow */}
                {windDir.length > 0 && (
                  <g transform={`rotate(${avgWindDir}, 50, 50)`}>
                    <line x1="50" y1="50" x2="50" y2="18" stroke="#14B8A6" strokeWidth="2.5" strokeLinecap="round" />
                    <polygon points="50,14 46,22 54,22" fill="#14B8A6" />
                  </g>
                )}
                {/* Center dot */}
                <circle cx="50" cy="50" r="3" fill="#14B8A6" />
              </svg>
            </div>
            <div className="text-center mt-3">
              <div className="text-xl font-bold text-goose-accent">{dirLabel} {avgWindSpeed.toFixed(1)}m/s</div>
              <div className="text-xs text-goose-text-muted mt-1">
                Beaufort {beaufort.level}: {beaufort.name}
              </div>
            </div>
          </Card>

          {/* Wind KPIs */}
          <div className="col-span-8 grid grid-cols-2 gap-4">
            <KPICard
              label="Avg Wind Speed"
              value={`${avgWindSpeed.toFixed(1)}`}
              unit="m/s"
              status={avgWindSpeed > 10 ? 'critical' : avgWindSpeed > 5 ? 'warning' : 'healthy'}
              subtitle={`${beaufort.name} (Beaufort ${beaufort.level})`}
            />
            <KPICard
              label="Max Wind Speed"
              value={`${maxWindSpeed.toFixed(1)}`}
              unit="m/s"
              status={maxWindSpeed > 15 ? 'critical' : maxWindSpeed > 8 ? 'warning' : 'healthy'}
              subtitle="Peak gust recorded"
            />
            <KPICard
              label="Dominant Direction"
              value={dirLabel}
              subtitle={windDir.length > 0 ? `${avgWindDir.toFixed(0)}deg from north` : 'No direction data'}
            />
            <KPICard
              label="Gust Factor"
              value={gustFactor.toFixed(2)}
              status={gustFactor > 2 ? 'warning' : 'healthy'}
              subtitle={gustFactor > 2 ? 'Gusty conditions' : 'Steady wind'}
            />
          </div>
        </div>
      ) : (
        <Card className="bg-gradient-to-br from-goose-warning/5 to-transparent border-goose-warning/20 py-8">
          <div className="flex flex-col items-center text-center">
            <div className="w-12 h-12 rounded-full bg-goose-warning/10 flex items-center justify-center mb-3">
              <svg className="w-6 h-6 text-goose-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-goose-text">No Wind Data Available</p>
            <p className="text-xs text-goose-text-muted mt-1 max-w-md">
              Wind estimation requires GPS ground speed and attitude (tilt) data. This log may lack the
              necessary telemetry streams, or the flight was too short for reliable estimation. Wind
              KPIs and compass are unavailable for this analysis.
            </p>
          </div>
        </Card>
      )}

      {/* Beaufort Scale Reference */}
      <Card>
        <CardTitle className="mb-3">Beaufort Scale</CardTitle>
        <div className="grid grid-cols-4 md:grid-cols-8 gap-1.5">
          {BEAUFORT_SCALE.map((b, i) => (
            <div
              key={i}
              className={`p-2 rounded-lg text-center ${beaufort.level === i ? 'bg-goose-accent/10 border border-goose-accent/30' : 'bg-goose-bg'}`}
            >
              <div className="text-xs font-bold text-goose-text">{i}</div>
              <div className="text-[9px] text-goose-text-muted truncate">{b.name}</div>
              <div className="text-[9px] text-goose-text-muted">&lt;{b.max}m/s</div>
            </div>
          ))}
        </div>
        <p className="text-xs text-goose-text-muted mt-3">
          The Beaufort scale classifies wind intensity from 0 (calm) to 12 (hurricane). Most consumer
          drones operate safely up to Beaufort 4 (moderate breeze, ~8 m/s). Higher levels increase
          motor load and reduce controllability.
        </p>
      </Card>

      {/* Tabbed Charts */}
      <Tabs
        tabs={[
          { id: 'wind', label: 'Wind Speed' },
          { id: 'baro', label: 'Barometer' },
        ]}
      >
        {(tab) => (
          <>
            {tab === 'wind' && (
              <div>
                {windData[0].length > 0 ? (
                  <>
                    <TimeSeriesChart
                      data={windData}
                      series={[{ label: 'Wind Speed (m/s)', color: CHART_COLORS.altitude, width: 2 }]}
                      title="Wind Speed Over Time"
                      height={280}
                      thresholds={[
                        { value: 5, color: CHART_COLORS.voltage, label: 'Moderate', dash: [6, 4] },
                        { value: 10, color: CHART_COLORS.threshold, label: 'Strong', dash: [4, 2] },
                      ]}
                    />
                    <p className="text-xs text-goose-text-muted mt-2 px-1">
                      Wind speed over the flight duration. The yellow dashed line marks the moderate
                      threshold (5 m/s) and the red dashed line marks the strong threshold (10 m/s).
                      Sustained readings above 10 m/s indicate conditions that may exceed the aircraft's
                      wind resistance rating.
                    </p>
                  </>
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">
                    No wind estimation data available. Wind speed is estimated from drone tilt angle and GPS ground speed difference.
                  </Card>
                )}
              </div>
            )}
            {tab === 'baro' && (
              <div>
                {baroData[0].length > 0 ? (
                  <>
                    <TimeSeriesChart
                      data={baroData}
                      series={baroFields.map((f, i) => ({
                        label: f,
                        color: [CHART_COLORS.motor1, CHART_COLORS.motor2][i % 2],
                      }))}
                      title="Barometer Data"
                      height={280}
                    />
                    <p className="text-xs text-goose-text-muted mt-2 px-1">
                      Barometric pressure and temperature readings over time. Rapid pressure drops may
                      indicate altitude changes or approaching weather fronts. Temperature data helps
                      assess battery performance and air density effects on propulsion.
                    </p>
                  </>
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">
                    No barometer data available. This sensor stream was not present in the flight log.
                  </Card>
                )}
              </div>
            )}
          </>
        )}
      </Tabs>

      {/* Findings */}
      {envFindings.length > 0 && (
        <Card>
          <CardTitle className="mb-3">Environment Findings</CardTitle>
          <div className="space-y-2">
            {envFindings.map((f) => (
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

      {/* Overall Assessment */}
      <Card className="bg-gradient-to-br from-goose-chart-2/5 to-transparent">
        <CardTitle className="mb-3">Environment Assessment</CardTitle>
        <div className="flex items-start gap-4">
          <div className={`text-lg font-bold ${assessment.color}`}>
            {assessment.label}
          </div>
        </div>
        <p className="text-sm text-goose-text-muted mt-2 leading-relaxed">
          {assessment.summary}
        </p>
        <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-goose-border">
          <div className="text-center">
            <div className="text-xs text-goose-text-muted">Wind Data</div>
            <div className="text-sm font-medium text-goose-text mt-0.5">
              {hasWindData ? `${windSpeed.length} samples` : 'Not available'}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-goose-text-muted">Barometer Data</div>
            <div className="text-sm font-medium text-goose-text mt-0.5">
              {hasBaroData ? `${baroData[0].length} samples` : 'Not available'}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-goose-text-muted">Findings</div>
            <div className="text-sm font-medium text-goose-text mt-0.5">
              {envFindings.length > 0 ? `${envFindings.length} issue${envFindings.length > 1 ? 's' : ''}` : 'None'}
            </div>
          </div>
        </div>
      </Card>

      <Card className="bg-goose-bg border-goose-border">
        <p className="text-xs text-goose-text-muted">
          Note: Wind speed is estimated from drone tilt angle and GPS ground speed difference.
          More accurate in GPS-guided modes (Position, Mission). Less reliable in manual/stabilized flight.
        </p>
      </Card>
    </div>
  )
}
