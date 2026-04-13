import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

export interface SeriesConfig {
  label: string
  color: string
  width?: number
  dash?: number[]
  show?: boolean
  scale?: string
  value?: (self: uPlot, rawValue: number) => string
}

interface TimeSeriesChartProps {
  data: uPlot.AlignedData
  series: SeriesConfig[]
  title?: string
  height?: number
  thresholds?: { value: number; color: string; label?: string; dash?: number[] }[]
  bands?: { from: number; to: number; color: string; label?: string }[]
  className?: string
  syncKey?: string
}

// Chart colors from theme
export const CHART_COLORS = {
  motor1: '#14B8A6',
  motor2: '#3B82F6',
  motor3: '#F59E0B',
  motor4: '#EF4444',
  motor5: '#8B5CF6',
  motor6: '#EC4899',
  motor7: '#22C55E',
  motor8: '#F97316',
  altitude: '#14B8A6',
  voltage: '#F59E0B',
  current: '#EF4444',
  temperature: '#F97316',
  gps: '#22C55E',
  vibration: '#EF4444',
  roll: '#3B82F6',
  pitch: '#22C55E',
  yaw: '#F59E0B',
  speed: '#14B8A6',
  rc: '#8B5CF6',
  setpoint: '#64748B',
  threshold: '#EF4444',
}

// Shared sync cursor across charts
const syncKeys = new Map<string, uPlot.SyncPubSub>()
function getSync(key: string): uPlot.SyncPubSub {
  if (!syncKeys.has(key)) {
    syncKeys.set(key, uPlot.sync(key))
  }
  return syncKeys.get(key)!
}

export function TimeSeriesChart({
  data,
  series,
  title,
  height = 250,
  thresholds,
  bands,
  className = '',
  syncKey = 'goose-sync',
}: TimeSeriesChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<uPlot | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data || !data[0] || data[0].length === 0) return

    // Ensure data array length matches series + 1 (timestamps + N series)
    // If mismatch, uPlot will crash with "Cannot read properties of undefined"
    const expectedCols = series.length + 1
    if (data.length < expectedCols) {
      console.warn(`TimeSeriesChart: data has ${data.length} columns but ${series.length} series defined. Skipping render.`)
      return
    }

    const sync = getSync(syncKey)

    const opts: uPlot.Options = {
      width: containerRef.current.clientWidth,
      height,
      cursor: {
        sync: { key: sync.key },
        drag: { x: true, y: false },
      },
      scales: {
        x: { time: false },
      },
      axes: [
        {
          stroke: '#64748B',
          grid: { stroke: '#1E293B', width: 1 },
          ticks: { stroke: '#334155', width: 1 },
          font: '11px Inter, system-ui',
          values: (_, vals) => vals.map(v => {
            if (v >= 60) return `${Math.floor(v / 60)}:${String(Math.floor(v % 60)).padStart(2, '0')}`
            return `${v.toFixed(0)}s`
          }),
        },
        {
          stroke: '#64748B',
          grid: { stroke: '#1E293B', width: 1 },
          ticks: { stroke: '#334155', width: 1 },
          font: '11px Inter, system-ui',
          size: 60,
        },
      ],
      series: [
        { label: 'Time' },
        ...series.map((s) => ({
          label: s.label,
          stroke: s.color,
          width: s.width ?? 1.5,
          dash: s.dash,
          show: s.show ?? true,
          scale: s.scale ?? 'y',
          value: s.value || ((_: uPlot, v: number) => v != null ? v.toFixed(1) : '--'),
        })),
      ],
      hooks: {
        draw: [
          (u: uPlot) => {
            const ctx = u.ctx
            // Draw threshold lines
            thresholds?.forEach((t) => {
              const y = u.valToPos(t.value, 'y', true)
              if (y < u.bbox.top || y > u.bbox.top + u.bbox.height) return
              ctx.save()
              ctx.strokeStyle = t.color
              ctx.lineWidth = 1
              ctx.setLineDash(t.dash || [6, 4])
              ctx.beginPath()
              ctx.moveTo(u.bbox.left, y)
              ctx.lineTo(u.bbox.left + u.bbox.width, y)
              ctx.stroke()
              if (t.label) {
                ctx.fillStyle = t.color
                ctx.font = '10px Inter, system-ui'
                ctx.fillText(t.label, u.bbox.left + 4, y - 4)
              }
              ctx.restore()
            })
          },
        ],
      },
    }

    // Add second Y axis if any series uses a different scale
    const hasSecondScale = series.some(s => s.scale && s.scale !== 'y')
    if (hasSecondScale) {
      opts.axes!.push({
        side: 1,
        stroke: '#64748B',
        grid: { show: false },
        ticks: { stroke: '#334155', width: 1 },
        font: '11px Inter, system-ui',
        size: 60,
        scale: series.find(s => s.scale && s.scale !== 'y')?.scale,
      })
    }

    chartRef.current = new uPlot(opts, data, containerRef.current)

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.setSize({
          width: containerRef.current.clientWidth,
          height,
        })
      }
    }
    const observer = new ResizeObserver(handleResize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [data, series, height, thresholds, syncKey])

  return (
    <div className={`bg-goose-surface border border-goose-border rounded-xl p-4 ${className}`}>
      {title && (
        <h4 className="text-sm font-medium text-goose-text mb-3">{title}</h4>
      )}
      <div ref={containerRef} className="w-full" />
      {(!data || data[0].length === 0) && (
        <div className="flex items-center justify-center h-[200px] text-sm text-goose-text-muted">
          No data available for this stream
        </div>
      )}
    </div>
  )
}
