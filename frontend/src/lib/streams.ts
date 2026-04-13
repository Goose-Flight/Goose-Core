// Helper to extract uPlot-ready data from analysis timeseries
import type { TimeseriesData, Finding } from './types'
import type uPlot from 'uplot'

/**
 * Build uPlot AlignedData from a timeseries stream.
 * Returns [timestamps, ...values] arrays aligned to the timestamps.
 */
export function buildChartData(
  timeseries: TimeseriesData,
  streamName: string,
  fields?: string[]
): { data: uPlot.AlignedData; fieldNames: string[] } {
  const stream = timeseries[streamName]
  if (!stream || !stream.timestamps || stream.timestamps.length === 0) {
    return { data: [new Float64Array(0)], fieldNames: [] }
  }

  const timestamps = stream.timestamps
  const fieldNames: string[] = []
  const arrays: (number[] | Float64Array)[] = [timestamps]

  const keys = fields || Object.keys(stream).filter((k) => k !== 'timestamps')
  for (const key of keys) {
    const vals = stream[key]
    if (vals && Array.isArray(vals) && vals.length > 0) {
      fieldNames.push(key)
      arrays.push(vals)
    }
  }

  // If no data columns found, return empty
  if (arrays.length <= 1) {
    return { data: [new Float64Array(0)], fieldNames: [] }
  }

  return { data: arrays as uPlot.AlignedData, fieldNames }
}

/**
 * Filter findings by plugin ID prefix
 */
export function findingsByPlugin(findings: Finding[], pluginId: string): Finding[] {
  return findings.filter((f) => f.plugin_id === pluginId)
}

/**
 * Get the worst severity from a list of findings
 */
export function worstSeverity(findings: Finding[]): 'critical' | 'warning' | 'info' | 'pass' {
  const order = { critical: 0, warning: 1, info: 2, pass: 3 }
  if (findings.length === 0) return 'pass'
  return findings.reduce((worst, f) => {
    return (order[f.severity] ?? 4) < (order[worst] ?? 4) ? f.severity : worst
  }, 'pass' as 'critical' | 'warning' | 'info' | 'pass')
}

/**
 * Compute average of a numeric array, ignoring nulls/NaN
 */
export function avg(arr: number[]): number {
  const valid = arr.filter((v) => v != null && !isNaN(v))
  if (valid.length === 0) return 0
  return valid.reduce((sum, v) => sum + v, 0) / valid.length
}

/**
 * Compute max of a numeric array
 */
export function max(arr: number[]): number {
  const valid = arr.filter((v) => v != null && !isNaN(v))
  if (valid.length === 0) return 0
  return Math.max(...valid)
}

/**
 * Compute min of a numeric array
 */
export function min(arr: number[]): number {
  const valid = arr.filter((v) => v != null && !isNaN(v))
  if (valid.length === 0) return 0
  return Math.min(...valid)
}

/**
 * Compute std deviation
 */
export function stdDev(arr: number[]): number {
  const valid = arr.filter((v) => v != null && !isNaN(v))
  if (valid.length < 2) return 0
  const mean = avg(valid)
  const variance = valid.reduce((sum, v) => sum + (v - mean) ** 2, 0) / valid.length
  return Math.sqrt(variance)
}

/**
 * Format seconds to mm:ss
 */
export function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
