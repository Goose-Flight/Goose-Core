import { useState, useEffect } from 'react'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ProBadge } from '@/components/ui/Badge'
import { proApi } from '@/lib/proApi'
import type { Campaign, ValidationReport } from '@/lib/proTypes'

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-5 w-5 text-goose-accent" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

interface GeneratedReport extends ValidationReport {
  type: 'validation' | 'compliance'
  standard?: string
}

export function ReportsProPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [reports, setReports] = useState<GeneratedReport[]>([])
  const [loadingCampaigns, setLoadingCampaigns] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Validation form state
  const [valCampaignId, setValCampaignId] = useState('')
  const [generatingVal, setGeneratingVal] = useState(false)

  // Compliance form state
  const [compCampaignId, setCompCampaignId] = useState('')
  const [compStandard, setCompStandard] = useState('MIL-STD-810H')
  const [generatingComp, setGeneratingComp] = useState(false)

  useEffect(() => {
    proApi.get<Campaign[]>('/api/campaigns')
      .then(data => {
        setCampaigns(data)
        if (data.length > 0) {
          setValCampaignId(data[0].id)
          setCompCampaignId(data[0].id)
        }
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load campaigns'))
      .finally(() => setLoadingCampaigns(false))
  }, [])

  const handleGenerateValidation = async () => {
    if (!valCampaignId) return
    setGeneratingVal(true)
    setError(null)
    try {
      const result = await proApi.post<ValidationReport>('/api/reports/validation', { campaign_id: valCampaignId })
      setReports(prev => [{ ...result, type: 'validation' }, ...prev])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate validation report')
    } finally {
      setGeneratingVal(false)
    }
  }

  const handleGenerateCompliance = async () => {
    if (!compCampaignId) return
    setGeneratingComp(true)
    setError(null)
    try {
      const result = await proApi.post<ValidationReport>('/api/reports/compliance', {
        campaign_id: compCampaignId,
        standard: compStandard,
      })
      setReports(prev => [{ ...result, type: 'compliance', standard: compStandard }, ...prev])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate compliance report')
    } finally {
      setGeneratingComp(false)
    }
  }

  const proBase = (import.meta.env.VITE_PRO_API_URL as string) ?? 'http://localhost:8765'

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
          Reports <ProBadge />
        </h1>
        <p className="text-sm text-goose-text-muted mt-1">
          Generate validation and compliance reports for test campaigns
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
      )}

      {/* Generator cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Validation Report */}
        <Card>
          <CardTitle className="mb-1">Validation Report</CardTitle>
          <CardDescription className="mb-4">
            GPS-denied navigation accuracy report including CEP, R95, and drift analysis
          </CardDescription>
          {loadingCampaigns ? (
            <div className="flex items-center gap-2 text-sm text-goose-text-muted">
              <LoadingSpinner /> Loading campaigns…
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-goose-text-muted block mb-1">Campaign</label>
                <select
                  value={valCampaignId}
                  onChange={e => setValCampaignId(e.target.value)}
                  className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text focus:outline-none focus:border-goose-accent"
                >
                  {campaigns.length === 0 && <option value="">No campaigns available</option>}
                  {campaigns.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <Button
                loading={generatingVal}
                disabled={!valCampaignId || campaigns.length === 0}
                onClick={handleGenerateValidation}
                className="w-full"
              >
                Generate Validation Report
              </Button>
            </div>
          )}
        </Card>

        {/* Compliance Report */}
        <Card>
          <CardTitle className="mb-1">Compliance Report</CardTitle>
          <CardDescription className="mb-4">
            Standards-based compliance assessment for regulatory or procurement documentation
          </CardDescription>
          {loadingCampaigns ? (
            <div className="flex items-center gap-2 text-sm text-goose-text-muted">
              <LoadingSpinner /> Loading campaigns…
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-goose-text-muted block mb-1">Campaign</label>
                <select
                  value={compCampaignId}
                  onChange={e => setCompCampaignId(e.target.value)}
                  className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text focus:outline-none focus:border-goose-accent"
                >
                  {campaigns.length === 0 && <option value="">No campaigns available</option>}
                  {campaigns.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-goose-text-muted block mb-1">Standard</label>
                <input
                  value={compStandard}
                  onChange={e => setCompStandard(e.target.value)}
                  className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text font-mono focus:outline-none focus:border-goose-accent"
                />
              </div>
              <Button
                loading={generatingComp}
                disabled={!compCampaignId || campaigns.length === 0}
                onClick={handleGenerateCompliance}
                className="w-full"
              >
                Generate Compliance Report
              </Button>
            </div>
          )}
        </Card>
      </div>

      {/* Generated reports list */}
      {reports.length > 0 && (
        <Card>
          <CardTitle className="mb-4">Generated Reports</CardTitle>
          <div className="space-y-3">
            {reports.map(r => (
              <div
                key={r.report_id}
                className="flex items-center justify-between p-3 rounded-lg bg-goose-bg border border-goose-border"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Badge variant={r.type === 'validation' ? 'accent' : 'info'}>
                    {r.type === 'validation' ? 'VALIDATION' : 'COMPLIANCE'}
                  </Badge>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-goose-text truncate">{r.campaign_name}</p>
                    <p className="text-xs text-goose-text-muted">
                      {r.type === 'compliance' && r.standard && `${r.standard} · `}
                      {new Date(r.generated_at).toLocaleString()}
                      {r.overall_result && (
                        <span className={`ml-2 font-medium ${r.overall_result === 'PASS' ? 'text-goose-success' : 'text-goose-error'}`}>
                          {r.overall_result}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <a
                    href={`${proBase}/api/reports/${r.report_id}/html`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button size="sm" variant="secondary">Download HTML</Button>
                  </a>
                  <a
                    href={`${proBase}/api/reports/${r.report_id}/json`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button size="sm" variant="ghost">Download JSON</Button>
                  </a>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
