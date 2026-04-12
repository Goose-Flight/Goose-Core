import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '@/stores/analysisStore'
import { Card, CardTitle } from '@/components/ui/Card'
import { KPICard } from '@/components/ui/KPICard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { max, min } from '@/lib/streams'
import { PlotlyChart } from '@/components/charts/PlotlyChart'

type ColorMode = 'altitude' | 'speed'

export function FlightPath3D() {
  const navigate = useNavigate()
  const { currentAnalysis } = useAnalysisStore()
  const [colorMode, setColorMode] = useState<ColorMode>('altitude')
  const [showSetpoint, setShowSetpoint] = useState(false)

  if (!currentAnalysis) {
    return (
      <div className="p-6">
        <Button variant="secondary" onClick={() => navigate('/analyze')}>Run Analysis First</Button>
      </div>
    )
  }

  const { flight_path, setpoint_path, metadata } = currentAnalysis

  if (!flight_path || !flight_path.lat || flight_path.lat.length === 0) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-4">
          &larr; Back to Results
        </Button>
        <Card className="py-12 text-center">
          <span className="text-4xl mb-4 block">🗺️</span>
          <p className="text-goose-text font-medium">No GPS Data Available</p>
          <p className="text-sm text-goose-text-muted mt-2">This flight log does not contain GPS position data for 3D visualization.</p>
        </Card>
      </div>
    )
  }

  const { lat, lon, alt, timestamps } = flight_path

  // Compute speeds from position deltas
  const speeds: number[] = [0]
  for (let i = 1; i < lat.length; i++) {
    const dt = timestamps[i] - timestamps[i - 1]
    if (dt <= 0) { speeds.push(speeds[speeds.length - 1]); continue }
    const dlat = (lat[i] - lat[i - 1]) * 111320 // meters per degree lat
    const dlon = (lon[i] - lon[i - 1]) * 111320 * Math.cos((lat[i] * Math.PI) / 180)
    const dalt = alt[i] - alt[i - 1]
    const dist = Math.sqrt(dlat * dlat + dlon * dlon + dalt * dalt)
    speeds.push(dist / dt)
  }

  const maxAlt = max(alt)
  const maxSpeed = max(speeds)
  const minAlt = min(alt.filter(a => a > 0))

  // Total distance
  let totalDist = 0
  for (let i = 1; i < lat.length; i++) {
    const dlat = (lat[i] - lat[i - 1]) * 111320
    const dlon = (lon[i] - lon[i - 1]) * 111320 * Math.cos((lat[i] * Math.PI) / 180)
    totalDist += Math.sqrt(dlat * dlat + dlon * dlon)
  }

  const colorValues = colorMode === 'altitude' ? alt : speeds
  const colorLabel = colorMode === 'altitude' ? 'Altitude (m)' : 'Speed (m/s)'

  // Plotly trace
  const trace: any = {
    type: 'scatter3d',
    mode: 'lines+markers',
    x: lon,
    y: lat,
    z: alt,
    marker: {
      size: 2,
      color: colorValues,
      colorscale: colorMode === 'altitude'
        ? [[0, '#3B82F6'], [0.5, '#22C55E'], [1, '#EF4444']]
        : [[0, '#22C55E'], [0.5, '#F59E0B'], [1, '#EF4444']],
      colorbar: {
        title: { text: colorLabel, font: { color: '#94A3B8', size: 11 } },
        tickfont: { color: '#94A3B8', size: 10 },
        bgcolor: 'rgba(0,0,0,0)',
        bordercolor: '#1E293B',
        len: 0.6,
      },
      showscale: true,
    },
    line: {
      color: colorValues,
      colorscale: colorMode === 'altitude'
        ? [[0, '#3B82F6'], [0.5, '#22C55E'], [1, '#EF4444']]
        : [[0, '#22C55E'], [0.5, '#F59E0B'], [1, '#EF4444']],
      width: 4,
    },
    hovertemplate:
      'Lat: %{y:.5f}<br>Lon: %{x:.5f}<br>Alt: %{z:.1f}m<extra></extra>',
    name: 'Flight Path',
  }

  const traces = [trace]

  // Setpoint path overlay (unique to Goose!)
  if (showSetpoint && setpoint_path && setpoint_path.lat.length > 0) {
    traces.push({
      type: 'scatter3d',
      mode: 'lines',
      x: setpoint_path.lon,
      y: setpoint_path.lat,
      z: setpoint_path.alt,
      line: { color: '#64748B', width: 2, dash: 'dash' },
      name: 'Commanded Path',
      hovertemplate: 'Setpoint<br>Alt: %{z:.1f}m<extra></extra>',
    })
  }

  // Start/End markers
  traces.push({
    type: 'scatter3d',
    mode: 'markers',
    x: [lon[0]],
    y: [lat[0]],
    z: [alt[0]],
    marker: { size: 8, color: '#22C55E', symbol: 'diamond' },
    name: 'Takeoff',
    hovertemplate: 'Takeoff<br>Alt: %{z:.1f}m<extra></extra>',
  })
  traces.push({
    type: 'scatter3d',
    mode: 'markers',
    x: [lon[lon.length - 1]],
    y: [lat[lat.length - 1]],
    z: [alt[alt.length - 1]],
    marker: { size: 8, color: '#EF4444', symbol: 'square' },
    name: 'Landing',
    hovertemplate: 'Landing<br>Alt: %{z:.1f}m<extra></extra>',
  })

  const layout: any = {
    paper_bgcolor: '#0B1120',
    plot_bgcolor: '#0B1120',
    font: { color: '#94A3B8', family: 'Inter, system-ui' },
    margin: { l: 0, r: 0, t: 0, b: 0 },
    scene: {
      bgcolor: '#0B1120',
      xaxis: {
        title: { text: 'Longitude', font: { size: 10 } },
        gridcolor: '#1E293B',
        zerolinecolor: '#334155',
        tickfont: { size: 9 },
      },
      yaxis: {
        title: { text: 'Latitude', font: { size: 10 } },
        gridcolor: '#1E293B',
        zerolinecolor: '#334155',
        tickfont: { size: 9 },
      },
      zaxis: {
        title: { text: 'Altitude (m)', font: { size: 10 } },
        gridcolor: '#1E293B',
        zerolinecolor: '#334155',
        tickfont: { size: 9 },
      },
      camera: {
        eye: { x: 1.5, y: 1.5, z: 0.8 },
      },
      dragmode: 'turntable',
    },
    showlegend: true,
    legend: {
      x: 0.02, y: 0.98,
      bgcolor: 'rgba(17,24,39,0.8)',
      bordercolor: '#1E293B',
      font: { size: 10 },
    },
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
            &larr; Back to Results
          </Button>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            <span className="text-3xl">🗺️</span> 3D Flight Path
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            Drag to rotate, scroll to zoom, right-click to pan
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex gap-1 bg-goose-surface border border-goose-border rounded-lg p-1">
          <button
            onClick={() => setColorMode('altitude')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium cursor-pointer transition-colors ${colorMode === 'altitude' ? 'bg-goose-accent text-white' : 'text-goose-text-muted hover:text-goose-text'}`}
          >
            Altitude
          </button>
          <button
            onClick={() => setColorMode('speed')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium cursor-pointer transition-colors ${colorMode === 'speed' ? 'bg-goose-accent text-white' : 'text-goose-text-muted hover:text-goose-text'}`}
          >
            Speed
          </button>
        </div>

        {setpoint_path && setpoint_path.lat.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-goose-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={showSetpoint}
              onChange={(e) => setShowSetpoint(e.target.checked)}
              className="rounded border-goose-border"
            />
            Show Commanded Path
            <Badge variant="accent">Goose Only</Badge>
          </label>
        )}

        <div className="ml-auto flex items-center gap-2 text-xs text-goose-text-muted">
          <span className="inline-block w-3 h-1 rounded bg-goose-success" /> Low
          <span className="inline-block w-3 h-1 rounded bg-goose-warning" /> Mid
          <span className="inline-block w-3 h-1 rounded bg-goose-error" /> High
          <span className="ml-1">{colorLabel}</span>
        </div>
      </div>

      {/* 3D Plot */}
      <Card padding="none" className="overflow-hidden">
          <PlotlyChart
            data={traces}
            layout={layout}
            config={{
              displayModeBar: true,
              modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'] as any,
            }}
            style={{ width: '100%', height: '500px' }}
          />
      </Card>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard label="Max Altitude" value={`${maxAlt.toFixed(1)}`} unit="m" status="neutral" />
        <KPICard label="Max Speed" value={`${maxSpeed.toFixed(1)}`} unit="m/s" status="neutral" />
        <KPICard label="Total Distance" value={totalDist > 1000 ? `${(totalDist / 1000).toFixed(1)}` : `${totalDist.toFixed(0)}`} unit={totalDist > 1000 ? 'km' : 'm'} />
        <KPICard label="Duration" value={`${Math.floor(metadata.duration_sec / 60)}:${String(Math.round(metadata.duration_sec % 60)).padStart(2, '0')}`} subtitle={`${lat.length} GPS points`} />
      </div>
    </div>
  )
}
