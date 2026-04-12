import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { DropZone } from '@/components/ui/DropZone'
import { useAnalysisStore } from '@/stores/analysisStore'
import { runQuickAnalysis } from '@/lib/api'
import type { UploadMetadata } from '@/lib/types'

type WizardStep = 'drone' | 'incident' | 'upload'

const incidentTypes = [
  { value: 'routine', label: 'Routine Check', desc: 'Regular post-flight review', color: 'border-l-goose-success' },
  { value: 'crash', label: 'Crash / Incident', desc: 'Something went wrong', color: 'border-l-goose-error' },
  { value: 'abnormal', label: 'Abnormal Behavior', desc: 'Flew weird, unexpected behavior', color: 'border-l-goose-warning' },
  { value: 'warranty', label: 'Warranty Claim', desc: 'Investigating for warranty', color: 'border-l-goose-info' },
  { value: 'insurance', label: 'Insurance', desc: 'Documentation for insurance', color: 'border-l-goose-chart-5' },
  { value: 'training', label: 'Training Review', desc: 'Reviewing a training flight', color: 'border-l-goose-accent' },
] as const

const profiles = [
  { value: 'default', label: 'Default', desc: 'Balanced analysis', icon: '🎯', color: 'from-goose-accent/10' },
  { value: 'racer', label: 'Racer', desc: 'FPV / racing', icon: '🏁', color: 'from-goose-error/10' },
  { value: 'shop', label: 'Shop / Repair', desc: 'Diagnostics', icon: '🔧', color: 'from-goose-warning/10' },
  { value: 'research', label: 'Research', desc: 'Academic', icon: '🔬', color: 'from-goose-info/10' },
  { value: 'gov_mil', label: 'Gov / Mil', desc: 'Forensic rigor', icon: '🛡️', color: 'from-goose-chart-5/10' },
  { value: 'factory', label: 'Factory QA', desc: 'Production QA', icon: '🏭', color: 'from-goose-success/10' },
  { value: 'advanced', label: 'Advanced', desc: 'All plugins', icon: '⚡', color: 'from-goose-chart-6/10' },
] as const

const analysisStages = [
  'Uploading flight log...',
  'Detecting log format...',
  'Parsing telemetry streams...',
  'Running motor analysis...',
  'Running battery analysis...',
  'Running vibration analysis...',
  'Running GPS health check...',
  'Running crash detection...',
  'Running EKF consistency...',
  'Generating hypotheses...',
  'Computing overall score...',
  'Building timeline...',
  'Preparing results...',
]

export function UploadWizard() {
  const navigate = useNavigate()
  const { setAnalysis, setAnalyzing, setError, isAnalyzing, error } = useAnalysisStore()

  // Reset stuck analyzing state on mount (e.g. after HMR or back navigation)
  useEffect(() => {
    setAnalyzing(false)
    setError(null)
  }, [])

  const [step, setStep] = useState<WizardStep>('incident')
  const [metadata, setMetadata] = useState<UploadMetadata>({
    incident_type: 'routine',
    profile: 'default',
  })
  const [file, setFile] = useState<File | null>(null)
  const [stageIndex, setStageIndex] = useState(0)
  const [uploadPct, setUploadPct] = useState(0)
  const [phase, setPhase] = useState<'idle' | 'uploading' | 'analyzing' | 'done'>('idle')

  // Animated progress during analysis
  useEffect(() => {
    if (!isAnalyzing) { setStageIndex(0); return }
    const interval = setInterval(() => {
      setStageIndex((prev) => (prev < analysisStages.length - 1 ? prev + 1 : prev))
    }, 1200)
    return () => clearInterval(interval)
  }, [isAnalyzing])

  const handleAnalyze = async () => {
    if (!file) return
    setAnalyzing(true)
    setStageIndex(0)
    setUploadPct(0)
    setPhase('uploading')
    setError(null)
    try {
      const result = await runQuickAnalysis(file, metadata, (pct) => {
        setUploadPct(pct)
        if (pct >= 100) setPhase('analyzing')
      })
      console.log('Analysis complete:', result.quick_analysis_id, 'score:', result.overall_score, 'findings:', result.findings?.length)
      if (!result || !result.ok) {
        throw new Error('Analysis returned invalid response')
      }
      setPhase('done')
      setAnalysis(result)
      setAnalyzing(false)
      navigate(`/analyze/${result.quick_analysis_id}`)
    } catch (err) {
      console.error('Analysis error:', err)
      setError(err instanceof Error ? err.message : String(err))
      setAnalyzing(false)
      setPhase('idle')
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-goose-text">Quick Analysis</h1>
        <p className="text-sm text-goose-text-muted mt-1">
          Tell us about the flight, then drop your log file.
        </p>
      </div>

      {/* Step indicators */}
      <div className="flex items-center gap-2">
        {(['incident', 'upload'] as const).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <button
              onClick={() => setStep(s)}
              className={`
                w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors cursor-pointer
                ${step === s ? 'bg-goose-accent text-white' : 'bg-goose-surface border border-goose-border text-goose-text-muted'}
              `}
            >
              {i + 1}
            </button>
            <span className={`text-sm ${step === s ? 'text-goose-text font-medium' : 'text-goose-text-muted'}`}>
              {s === 'incident' ? 'Flight Details' : 'Upload & Analyze'}
            </span>
            {i < 1 && <div className="w-12 h-px bg-goose-border" />}
          </div>
        ))}
      </div>

      {/* Loading / Analyzing State */}
      {isAnalyzing && (
        <Card className="py-10">
          <div className="flex flex-col items-center gap-6">
            {/* Animated goose */}
            <div className="relative">
              <div className="w-20 h-20 rounded-full bg-goose-accent/10 flex items-center justify-center animate-pulse">
                <span className="text-4xl">🪿</span>
              </div>
              <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-goose-accent flex items-center justify-center">
                <svg className="w-3.5 h-3.5 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
            </div>

            <div className="text-center">
              <p className="text-lg font-semibold text-goose-text">
                {phase === 'uploading' ? 'Uploading Flight Log' : phase === 'done' ? 'Analysis Complete!' : 'Analyzing Flight Log'}
              </p>
              <p className="text-sm text-goose-accent mt-1">
                {phase === 'uploading'
                  ? `Uploading ${file?.name || 'file'}... ${uploadPct}%`
                  : phase === 'done'
                    ? 'Preparing results...'
                    : analysisStages[stageIndex]
                }
              </p>
              {file && phase === 'uploading' && (
                <p className="text-xs text-goose-text-muted mt-1">
                  {(file.size / 1024 / 1024).toFixed(1)} MB
                </p>
              )}
            </div>

            {/* Progress bar */}
            <div className="w-full max-w-md">
              <div className="w-full h-2 bg-goose-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-goose-accent to-goose-success rounded-full transition-all duration-500 ease-out"
                  style={{ width: phase === 'uploading'
                    ? `${uploadPct * 0.4}%`
                    : `${40 + ((stageIndex + 1) / analysisStages.length) * 60}%`
                  }}
                />
              </div>
              <div className="flex justify-between mt-1.5 text-[10px] text-goose-text-muted">
                <span>{phase === 'uploading' ? `Uploading (${uploadPct}%)` : '17 plugins running'}</span>
                <span>{phase === 'uploading'
                  ? `${Math.round(uploadPct * 0.4)}%`
                  : `${Math.round(40 + ((stageIndex + 1) / analysisStages.length) * 60)}%`
                }</span>
              </div>
            </div>

            {/* Plugin badges */}
            <div className="flex flex-wrap justify-center gap-1.5 max-w-lg">
              {['Crash Detection', 'Vibration', 'Battery', 'GPS', 'Motors', 'EKF', 'RC Signal', 'Attitude'].map((name, i) => (
                <span
                  key={name}
                  className={`px-2 py-0.5 text-[10px] rounded-full transition-all duration-500 ${
                    i <= stageIndex * 0.6
                      ? 'bg-goose-success/15 text-goose-success'
                      : 'bg-goose-surface-hover text-goose-text-muted'
                  }`}
                >
                  {i <= stageIndex * 0.6 ? '\u2713' : '\u2022'} {name}
                </span>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Error State */}
      {error && !isAnalyzing && (
        <Card className="border-goose-error/30">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-full bg-goose-error/10 flex items-center justify-center shrink-0">
              <svg className="w-5 h-5 text-goose-error" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-goose-error">Analysis Failed</p>
              <p className="text-xs text-goose-text-muted mt-1">{error}</p>
              <Button size="sm" variant="danger" className="mt-3" onClick={() => { setError(null); setStep('upload'); }}>
                Try Again
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Step 1: Incident Details */}
      {step === 'incident' && !isAnalyzing && (
        <div className="space-y-6">
          {/* Incident Type */}
          <Card>
            <CardTitle className="mb-4">What are you investigating?</CardTitle>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {incidentTypes.map((type) => (
                <button
                  key={type.value}
                  onClick={() => setMetadata({ ...metadata, incident_type: type.value })}
                  className={`
                    p-3 rounded-lg border border-l-4 text-left transition-all cursor-pointer ${type.color}
                    ${
                      metadata.incident_type === type.value
                        ? 'border-goose-accent bg-goose-accent/5 border-l-goose-accent'
                        : 'border-goose-border hover:border-goose-border-subtle'
                    }
                  `}
                >
                  <p className="text-sm font-medium text-goose-text">{type.label}</p>
                  <p className="text-xs text-goose-text-muted mt-0.5">{type.desc}</p>
                </button>
              ))}
            </div>
          </Card>

          {/* Pilot Notes */}
          <Card>
            <CardTitle className="mb-3">Pilot Notes (optional)</CardTitle>
            <textarea
              value={metadata.pilot_notes || ''}
              onChange={(e) => setMetadata({ ...metadata, pilot_notes: e.target.value })}
              placeholder="What happened? Any observations before/during/after the flight..."
              className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent resize-y min-h-[80px]"
              rows={3}
            />
          </Card>

          {/* Profile */}
          <Card>
            <CardTitle className="mb-4">Analysis Profile</CardTitle>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {profiles.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setMetadata({ ...metadata, profile: p.value })}
                  className={`
                    p-3 rounded-lg border text-left transition-all cursor-pointer bg-gradient-to-br ${p.color} to-transparent
                    ${
                      metadata.profile === p.value
                        ? 'border-goose-accent ring-1 ring-goose-accent/50'
                        : 'border-goose-border hover:border-goose-border-subtle'
                    }
                  `}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{p.icon}</span>
                    <p className="text-sm font-medium text-goose-text">{p.label}</p>
                  </div>
                  <p className="text-[10px] text-goose-text-muted mt-1">{p.desc}</p>
                </button>
              ))}
            </div>
          </Card>

          <div className="flex justify-end">
            <Button onClick={() => setStep('upload')}>
              Next: Upload Log
            </Button>
          </div>
        </div>
      )}

      {/* Step 2: Upload */}
      {step === 'upload' && !isAnalyzing && (
        <div className="space-y-6">
          <Card>
            <CardTitle className="mb-4">Drop Your Flight Log</CardTitle>
            <DropZone onFileDrop={setFile} />
            {file && (
              <div className="mt-3 flex items-center gap-2 text-xs text-goose-text-muted">
                <span className="font-mono">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                <span>&middot;</span>
                <span>{file.name.split('.').pop()?.toUpperCase()} format</span>
              </div>
            )}
          </Card>

          {/* Summary */}
          <Card>
            <CardTitle className="mb-3">Analysis Summary</CardTitle>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div className="text-goose-text-muted">Type:</div>
              <div className="text-goose-text capitalize">{metadata.incident_type.replace('_', ' ')}</div>
              <div className="text-goose-text-muted">Profile:</div>
              <div className="text-goose-text capitalize">{metadata.profile.replace('_', ' ')}</div>
              {metadata.pilot_notes && (
                <>
                  <div className="text-goose-text-muted">Notes:</div>
                  <div className="text-goose-text truncate">{metadata.pilot_notes}</div>
                </>
              )}
              <div className="text-goose-text-muted">File:</div>
              <div className="text-goose-text">{file?.name || 'No file selected'}</div>
            </div>
          </Card>

          <div className="flex justify-between">
            <Button variant="secondary" onClick={() => setStep('incident')}>
              Back
            </Button>
            <Button
              onClick={handleAnalyze}
              disabled={!file}
              loading={isAnalyzing}
            >
              {isAnalyzing ? 'Analyzing...' : 'Analyze Flight'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
