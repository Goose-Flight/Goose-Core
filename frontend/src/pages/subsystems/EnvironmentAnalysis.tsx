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

export function EnvironmentAnalysis() {
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
  const envFindings = findingsByPlugin(findings, 'environment_conditions')
  const severity = worstSeverity(envFindings)

  // Wind data
  const windStream = timeseries.wind
  const windSpeed = (windStream?.speed as number[]) || (windStream?.wind_speed as number[]) || []
  const windDir = (windStream?.direction as number[]) || (windStream?.wind_dir as number[]) || []

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

      {/* Wind Overview */}
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
            subtitle={windDir.length > 0 ? `${avgWindDir.toFixed(0)}° from north` : 'No direction data'}
          />
          <KPICard
            label="Gust Factor"
            value={gustFactor.toFixed(2)}
            status={gustFactor > 2 ? 'warning' : 'healthy'}
            subtitle={gustFactor > 2 ? 'Gusty conditions' : 'Steady wind'}
          />
        </div>
      </div>

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
                  <TimeSeriesChart
                    data={baroData}
                    series={baroFields.map((f, i) => ({
                      label: f,
                      color: [CHART_COLORS.motor1, CHART_COLORS.motor2][i % 2],
                    }))}
                    title="Barometer Data"
                    height={280}
                  />
                ) : (
                  <Card className="py-8 text-center text-goose-text-muted text-sm">No barometer data available</Card>
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

      <Card className="bg-goose-bg border-goose-border">
        <p className="text-xs text-goose-text-muted">
          Note: Wind speed is estimated from drone tilt angle and GPS ground speed difference.
          More accurate in GPS-guided modes (Position, Mission). Less reliable in manual/stabilized flight.
        </p>
      </Card>
    </div>
  )
}
