// ============================================================
// Goose Flight — Core TypeScript Types
// Maps to FastAPI backend data structures
// ============================================================

// --- Severity & Confidence ---

export type Severity = 'critical' | 'warning' | 'info' | 'pass'
export type ConfidenceBand = 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN'
export type HypothesisStatus = 'CANDIDATE' | 'SUPPORTED' | 'REFUTED' | 'INCONCLUSIVE'
export type PluginTrustState = 'BUILTIN_TRUSTED' | 'LOCAL_UNSIGNED' | 'LOCAL_SIGNED' | 'COMMUNITY' | 'ENTERPRISE_TRUSTED' | 'BLOCKED'
export type CaseStatus = 'open' | 'closed' | 'archived'
export type EntitlementLevel = 'COMMUNITY' | 'LOCAL_PRO' | 'ENTERPRISE'

// --- Findings ---

export interface Finding {
  finding_id: string
  plugin_id: string
  plugin_version: string
  title: string
  description: string
  severity: Severity
  score: number
  confidence: number
  confidence_band: ConfidenceBand
  phase: string | null
  start_time: number | null
  end_time: number | null
  evidence_references: EvidenceReference[]
  supporting_metrics: Record<string, unknown>
  contradicting_metrics: Record<string, unknown>
  assumptions: string[]
  trust_state?: PluginTrustState
}

export interface EvidenceReference {
  evidence_id: string
  stream_name: string | null
  time_range_start: number | null
  time_range_end: number | null
  support_summary: string
}

// --- Hypotheses ---

export interface Hypothesis {
  hypothesis_id: string
  statement: string
  supporting_finding_ids: string[]
  contradicting_finding_ids: string[]
  confidence: number
  confidence_band: ConfidenceBand
  status: HypothesisStatus
  theme: string
  category: string
  related_timeline_events: string[]
  recommendations: string[]
  supporting_metrics: Record<string, unknown>
}

// --- Flight Metadata ---

export interface FlightMetadata {
  source_file: string
  autopilot: string
  firmware_version: string
  vehicle_type: string
  duration_sec: number
  start_time_utc: string | null
  log_format: string
  motor_count: number
  hardware?: string
}

// --- Flight Phases ---

export interface FlightPhase {
  name: string
  start_time: number
  end_time: number
  duration: number
  altitude_avg?: number
  speed_avg?: number
}

// --- Timeline Events ---

export interface TimelineEvent {
  timestamp: number
  severity: Severity
  category: string
  type: string
  message: string
  plugin_id?: string
}

// --- Mode Changes ---

export interface ModeChange {
  timestamp: number
  from_mode: string
  to_mode: string
}

// --- Timeseries Data ---

export interface TimeseriesStream {
  timestamps: number[]
  [key: string]: number[]
}

export interface TimeseriesData {
  [streamName: string]: TimeseriesStream
}

// --- Signal Quality ---

export interface SignalQuality {
  stream_name: string
  coverage: number
  gaps: number
  quality: string
}

// --- Quick Analysis Response ---

export interface QuickAnalysisResponse {
  ok: boolean
  quick_analysis_id: string
  profile: Record<string, unknown>
  engine_version: string
  overall_score: number
  metadata: {
    filename: string
    autopilot: string
    vehicle_type: string
    firmware_version: string
    frame_type: string | null
    hardware: string | null
    motor_count: number
    log_format: string
    duration_sec: number
    start_time_utc: string | null
    primary_mode: string | null
    modes_used: string[]
    crashed: boolean
    crash_confidence: number | null
    crash_signals: Record<string, unknown>[]
  }
  summary: {
    total_findings: number
    by_severity: Record<string, number>
    plugins_run: number
    plugin_errors: { plugin: string; error: string }[]
    hypotheses_count: number
    phases_count: number
    parameters_count: number
    events_count: number
  }
  findings: Finding[]
  hypotheses: Hypothesis[]
  signal_quality: SignalQuality[]
  timeline: TimelineEvent[]
  phases: FlightPhase[]
  parameters: Record<string, unknown>
  timeseries: TimeseriesData
  flight_path: FlightPath | null
  setpoint_path: FlightPath | null
  parse_diagnostics: ParseDiagnostics
}

export interface FlightPath {
  lat: number[]
  lon: number[]
  alt: number[]
  timestamps: number[]
}

export interface ParseDiagnostics {
  format_detected: string
  streams_found: string[]
  streams_missing: string[]
  warnings: string[]
  confidence: number
}

// --- Cases ---

export interface Case {
  case_id: string
  title: string
  status: CaseStatus
  profile: string
  created_at: string
  updated_at: string
  evidence_count: number
  findings_count: number
  description?: string
  metadata?: Record<string, unknown>
}

// --- Fleet / Drone ---

export interface Drone {
  drone_id: string
  name: string
  type: string // quad, hex, vtol, fixed-wing
  make?: string
  model?: string
  serial?: string
  status: 'active' | 'maintenance' | 'retired'
  flight_count: number
  total_hours: number
  last_flight?: string
  notes?: string
  battery_info?: {
    cell_count: number
    capacity_mah: number
    serial?: string
  }
  equipment_notes?: string
}

// --- Upload Wizard Metadata ---

export interface UploadMetadata {
  drone_id?: string
  incident_type: 'routine' | 'crash' | 'abnormal' | 'warranty' | 'insurance' | 'training'
  pilot_notes?: string
  conditions?: string
  severity_estimate?: 'none' | 'minor' | 'major' | 'total_loss'
  profile: string
}

// --- Plugins ---

export interface PluginInfo {
  plugin_id: string
  name: string
  version: string
  category: string
  description: string
  trust_state: PluginTrustState
  required_streams: string[]
  is_pro: boolean
}

// --- Profiles ---

export interface Profile {
  name: string
  display_name: string
  description: string
  icon?: string
}

// --- Audit ---

export interface AuditEntry {
  timestamp: string
  action: string
  actor: string
  details: Record<string, unknown>
}

// --- Reports ---

export interface ReportType {
  id: string
  name: string
  description: string
  formats: string[] // pdf, html, json
  is_pro: boolean
}

// --- App Settings ---

export interface AppSettings {
  telemetry_enabled: boolean
  theme: 'dark' | 'light' | 'hud'
  entitlement: EntitlementLevel
  version: string
}
