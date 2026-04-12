import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

interface PlotlyChartProps {
  data: Plotly.Data[]
  layout: Partial<Plotly.Layout>
  config?: Partial<Plotly.Config>
  style?: React.CSSProperties
  className?: string
  onClick?: () => void
}

export function PlotlyChart({ data, layout, config, style, className, onClick }: PlotlyChartProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    Plotly.newPlot(ref.current, data, layout as any, {
      displayModeBar: true,
      displaylogo: false,
      responsive: true,
      ...config,
    })
    return () => {
      if (ref.current) Plotly.purge(ref.current)
    }
  }, [data, layout, config])

  return (
    <div
      ref={ref}
      style={style}
      className={className}
      onClick={onClick}
    />
  )
}
