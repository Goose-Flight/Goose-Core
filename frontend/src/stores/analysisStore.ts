import { create } from 'zustand'
import type { QuickAnalysisResponse, Finding, Hypothesis, FlightPhase, TimelineEvent } from '@/lib/types'

interface AnalysisState {
  // Current analysis
  currentAnalysis: QuickAnalysisResponse | null
  isAnalyzing: boolean
  error: string | null

  // Filtered views
  selectedPhase: string | null
  severityFilter: string | null
  categoryFilter: string | null

  // Actions
  setAnalysis: (analysis: QuickAnalysisResponse) => void
  setAnalyzing: (v: boolean) => void
  setError: (error: string | null) => void
  setSelectedPhase: (phase: string | null) => void
  setSeverityFilter: (severity: string | null) => void
  setCategoryFilter: (category: string | null) => void
  clearAnalysis: () => void

  // Computed
  criticalFindings: () => Finding[]
  topHypothesis: () => Hypothesis | null
}

export const useAnalysisStore = create<AnalysisState>((set, get) => ({
  currentAnalysis: null,
  isAnalyzing: false,
  error: null,
  selectedPhase: null,
  severityFilter: null,
  categoryFilter: null,

  setAnalysis: (analysis) => set({ currentAnalysis: analysis, isAnalyzing: false, error: null }),
  setAnalyzing: (v) => set({ isAnalyzing: v }),
  setError: (error) => set({ error, isAnalyzing: false }),
  setSelectedPhase: (phase) => set({ selectedPhase: phase }),
  setSeverityFilter: (severity) => set({ severityFilter: severity }),
  setCategoryFilter: (category) => set({ categoryFilter: category }),
  clearAnalysis: () => set({ currentAnalysis: null, error: null, selectedPhase: null }),

  criticalFindings: () => {
    const analysis = get().currentAnalysis
    if (!analysis) return []
    return analysis.findings.filter((f) => f.severity === 'critical')
  },

  topHypothesis: () => {
    const analysis = get().currentAnalysis
    if (!analysis || !analysis.hypotheses.length) return null
    return analysis.hypotheses.reduce((best, h) => (h.confidence > best.confidence ? h : best))
  },
}))
