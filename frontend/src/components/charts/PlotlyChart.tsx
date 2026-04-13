import { useEffect, useRef, useState } from 'react'

interface PlotlyChartProps {
  data: any[]
  layout: Record<string, any>
  config?: Record<string, any>
  style?: React.CSSProperties
  className?: string
  onClick?: () => void
}

// Dynamic import — Plotly only loads when this component mounts (3MB saved from initial bundle)
let plotlyPromise: Promise<any> | null = null
function loadPlotly() {
  if (!plotlyPromise) {
    plotlyPromise = import('plotly.js-dist-min')
  }
  return plotlyPromise
}

export function PlotlyChart({ data, layout, config, style, className, onClick }: PlotlyChartProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [loaded, setLoaded] = useState(false)
  const plotlyRef = useRef<any>(null)

  useEffect(() => {
    loadPlotly().then((mod) => {
      plotlyRef.current = mod.default || mod
      setLoaded(true)
    })
  }, [])

  useEffect(() => {
    if (!ref.current || !loaded || !plotlyRef.current) return
    const Plotly = plotlyRef.current
    Plotly.newPlot(ref.current, data, layout, {
      displayModeBar: true,
      displaylogo: false,
      responsive: true,
      ...config,
    })
    return () => {
      if (ref.current) Plotly.purge(ref.current)
    }
  }, [data, layout, config, loaded])

  if (!loaded) {
    return (
      <div style={style} className={`flex items-center justify-center ${className || ''}`}>
        <div className="text-center">
          <svg className="w-6 h-6 animate-spin mx-auto mb-2 text-goose-accent" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <p className="text-xs text-goose-text-muted">Loading 3D renderer...</p>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={ref}
      style={style}
      className={className}
      onClick={onClick}
    />
  )
}
