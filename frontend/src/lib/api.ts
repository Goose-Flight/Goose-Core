// ============================================================
// Goose Flight — API Client
// Connects to FastAPI backend with bearer token auth
// ============================================================

import type {
  QuickAnalysisResponse,
  Case,
  Finding,
  Hypothesis,
  TimeseriesData,
  TimelineEvent,
  FlightPhase,
  PluginInfo,
  Profile,
  AuditEntry,
  ReportType,
  Drone,
  UploadMetadata,
  AppSettings,
} from './types'

// Token injected by FastAPI into the served HTML, or set manually for dev
declare global {
  interface Window {
    GOOSE_TOKEN?: string
  }
}

function getToken(): string {
  // 1. Injected by FastAPI when it serves the HTML (production)
  if (window.GOOSE_TOKEN) return window.GOOSE_TOKEN
  // 2. Pulled from Vite env during development
  if (import.meta.env.VITE_GOOSE_TOKEN) return import.meta.env.VITE_GOOSE_TOKEN
  // 3. Dev fallback
  return 'goose-dev-2026'
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${getToken()}`,
    ...((options.headers as Record<string, string>) || {}),
  }

  // Don't set Content-Type for FormData (browser sets multipart boundary)
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(`/api${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    const error = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${error}`)
  }

  return res.json()
}

// ---- Quick Analysis ----

export async function runQuickAnalysis(
  file: File,
  metadata?: UploadMetadata,
  onUploadProgress?: (pct: number) => void
): Promise<QuickAnalysisResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('profile', metadata?.profile || 'default')

  // Use XMLHttpRequest for upload progress on large files
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/quick-analysis')
    xhr.setRequestHeader('Authorization', `Bearer ${getToken()}`)

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onUploadProgress) {
        onUploadProgress(Math.round((e.loaded / e.total) * 100))
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          reject(new Error('Failed to parse response'))
        }
      } else {
        reject(new Error(`API ${xhr.status}: ${xhr.responseText.slice(0, 200)}`))
      }
    }

    xhr.onerror = () => reject(new Error('Network error — is the backend running?'))
    xhr.ontimeout = () => reject(new Error('Request timed out — file may be too large'))
    xhr.timeout = 600000 // 10 minute timeout for huge files

    xhr.send(formData)
  })
}

// ---- Cases ----

export async function getCases(): Promise<Case[]> {
  return request<Case[]>('/cases')
}

export async function getCase(caseId: string): Promise<Case> {
  return request<Case>(`/cases/${caseId}`)
}

export async function createCase(data: {
  title: string
  profile: string
  description?: string
  metadata?: Record<string, unknown>
}): Promise<Case> {
  return request<Case>('/cases', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function runCaseAnalysis(caseId: string): Promise<{
  findings: Finding[]
  hypotheses: Hypothesis[]
}> {
  return request(`/cases/${caseId}/analyze`, { method: 'POST' })
}

export async function getCaseFindings(caseId: string): Promise<Finding[]> {
  return request<Finding[]>(`/cases/${caseId}/findings`)
}

export async function getCaseHypotheses(caseId: string): Promise<Hypothesis[]> {
  return request<Hypothesis[]>(`/cases/${caseId}/hypotheses`)
}

export async function getCaseTimeline(caseId: string): Promise<TimelineEvent[]> {
  return request<TimelineEvent[]>(`/cases/${caseId}/timeline`)
}

export async function getCaseChartData(
  caseId: string,
  streams: string[]
): Promise<TimeseriesData> {
  const query = streams.map((s) => `streams=${s}`).join('&')
  return request<TimeseriesData>(`/cases/${caseId}/charts/data?${query}`)
}

export async function getCaseAudit(caseId: string): Promise<AuditEntry[]> {
  return request<AuditEntry[]>(`/cases/${caseId}/audit`)
}

export async function uploadEvidence(caseId: string, file: File): Promise<{ evidence_id: string; hash: string }> {
  const formData = new FormData()
  formData.append('file', file)
  return request(`/cases/${caseId}/evidence`, {
    method: 'POST',
    body: formData,
  })
}

// ---- Plugins ----

export async function getPlugins(): Promise<PluginInfo[]> {
  return request<PluginInfo[]>('/plugins')
}

// ---- Profiles ----

export async function getProfiles(): Promise<Profile[]> {
  return request<Profile[]>('/profiles')
}

// ---- Settings ----

export async function getSettings(): Promise<AppSettings> {
  return request<AppSettings>('/settings')
}

// ---- Reports ----

export async function getReportTypes(caseId: string): Promise<ReportType[]> {
  return request<ReportType[]>(`/cases/${caseId}/exports/reports`)
}

export async function generateReport(
  caseId: string,
  reportType: string,
  format: string
): Promise<Blob> {
  const res = await fetch(`/api/cases/${caseId}/exports/reports/${reportType}?format=${format}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  if (!res.ok) throw new Error(`Report generation failed: ${res.status}`)
  return res.blob()
}

// ---- Recent Runs ----

export async function getRecentRuns(): Promise<unknown[]> {
  return request<unknown[]>('/runs/recent')
}

// ---- Health ----

export async function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>('/health')
}

// ---- Fleet (future — needs backend route) ----

export async function getFleet(): Promise<Drone[]> {
  return request<Drone[]>('/fleet')
}

export async function addDrone(drone: Omit<Drone, 'drone_id' | 'flight_count' | 'total_hours'>): Promise<Drone> {
  return request<Drone>('/fleet', {
    method: 'POST',
    body: JSON.stringify(drone),
  })
}
