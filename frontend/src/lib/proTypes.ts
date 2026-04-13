// ============================================================
// Goose Pro — TypeScript interfaces for Pro data models
// ============================================================

export interface Campaign {
  id: string
  name: string
  status: 'ACTIVE' | 'COMPLETE' | 'PLANNING' | 'ARCHIVED'
  platform_name: string
  total_runs: number
  passed_runs: number
  failed_runs: number
  created_at: string
}

export interface TestRun {
  run_id: string
  run_number: number
  test_case_id: string
  status: string
  outcome: 'PASS' | 'FAIL' | 'MARGINAL' | 'PENDING'
  operator: string
  started_at: string
  completed_at: string | null
  metrics_json: Record<string, unknown> | null
}

export interface NavSystemProfile {
  profile_id: string
  name: string
  vendor: string
  technology: string
  firmware_version: string
  specifications: Record<string, unknown>
}

export interface DroneProfile {
  drone_id: string
  name: string
  vehicle_type: string
  serial_number: string
  status: 'active' | 'maintenance' | 'retired'
  nav_system_id: string | null
}

export interface ValidationReport {
  report_id: string
  campaign_name: string
  overall_result: string
  cep_m: number | null
  r95_m: number | null
  drift_rate_ms: number | null
  generated_at: string
}

export interface AuditEntry {
  entry_id: string
  user_id: string
  username: string
  action: string
  target: string
  timestamp: string
}

export interface User {
  user_id: string
  username: string
  display_name: string
  role: 'admin' | 'lead_engineer' | 'analyst' | 'viewer'
  status: 'active' | 'inactive'
  last_login: string | null
}
