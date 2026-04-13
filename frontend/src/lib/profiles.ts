// Profile-adaptive UI configuration
// Controls what's shown, emphasized, and hidden per profile

export interface ProfileUIConfig {
  id: string
  name: string
  icon: string
  description: string

  // Which subsystem cards to show on results page (order matters)
  subsystemOrder: string[]

  // Which subsystem gets the hero position (larger card)
  heroSubsystem: string | null

  // Which findings to emphasize (plugin IDs)
  priorityPlugins: string[]

  // Additional sections to show on results
  showCrashBanner: boolean
  showHypotheses: boolean
  showPhaseTimeline: boolean
  showMini3D: boolean
  showEvidenceBadge: boolean
  showSaveAsCase: boolean

  // Report emphasis
  defaultReportType: string

  // Quick action labels
  primaryAction: string
  primaryActionDesc: string
}

export const profileConfigs: Record<string, ProfileUIConfig> = {
  default: {
    id: 'default',
    name: 'Default',
    icon: '🎯',
    description: 'Balanced analysis for general use',
    subsystemOrder: ['motors', 'battery', 'gps', 'vibration', 'control', 'environment', 'flight-path', 'timeline'],
    heroSubsystem: null,
    priorityPlugins: ['crash_detection', 'battery_sag', 'motor_saturation', 'vibration'],
    showCrashBanner: true,
    showHypotheses: true,
    showPhaseTimeline: true,
    showMini3D: true,
    showEvidenceBadge: true,
    showSaveAsCase: true,
    defaultReportType: 'MissionSummaryReport',
    primaryAction: 'Review Findings',
    primaryActionDesc: 'Check all findings and hypotheses',
  },

  racer: {
    id: 'racer',
    name: 'Racer',
    icon: '🏁',
    description: 'FPV / racing focus — crash analysis and control response',
    // Racers care about: crash first, then control response, motors, vibration
    subsystemOrder: ['control', 'motors', 'vibration', 'battery', 'flight-path', 'timeline', 'gps', 'environment'],
    heroSubsystem: 'control',
    priorityPlugins: ['crash_detection', 'attitude_tracking', 'motor_saturation', 'vibration'],
    showCrashBanner: true,
    showHypotheses: true,
    showPhaseTimeline: false, // racers don't care about phases
    showMini3D: true,
    showEvidenceBadge: false, // racers don't need forensics
    showSaveAsCase: false,
    defaultReportType: 'QuickAnalysisSummary',
    primaryAction: 'Check Crash',
    primaryActionDesc: 'Was it a desync? Failsafe? Prop out?',
  },

  shop: {
    id: 'shop',
    name: 'Shop / Repair',
    icon: '🔧',
    description: 'Diagnostic workflow — customer-facing reports',
    // Shops care about: what's broken, can they bill warranty
    subsystemOrder: ['motors', 'battery', 'vibration', 'gps', 'control', 'environment', 'timeline', 'flight-path'],
    heroSubsystem: 'motors',
    priorityPlugins: ['motor_saturation', 'battery_sag', 'vibration', 'crash_detection'],
    showCrashBanner: true,
    showHypotheses: true,
    showPhaseTimeline: true,
    showMini3D: false,
    showEvidenceBadge: true, // warranty claims need evidence
    showSaveAsCase: true,
    defaultReportType: 'ServiceRepairSummary',
    primaryAction: 'Generate Repair Report',
    primaryActionDesc: 'Create customer-facing diagnostic report',
  },

  research: {
    id: 'research',
    name: 'Research',
    icon: '🔬',
    description: 'Academic — all data exposed, export-friendly',
    // Researchers want everything, in detail
    subsystemOrder: ['motors', 'battery', 'gps', 'vibration', 'control', 'environment', 'flight-path', 'timeline'],
    heroSubsystem: null,
    priorityPlugins: [], // show all equally
    showCrashBanner: true,
    showHypotheses: true,
    showPhaseTimeline: true,
    showMini3D: true,
    showEvidenceBadge: true,
    showSaveAsCase: true,
    defaultReportType: 'ForensicCaseReport',
    primaryAction: 'Export Data',
    primaryActionDesc: 'Download raw data for your own analysis',
  },

  gov_mil: {
    id: 'gov_mil',
    name: 'Gov / Military',
    icon: '🛡️',
    description: 'Full forensic rigor — evidence chain, compliance',
    // Gov/Mil: forensics first, everything auditable
    subsystemOrder: ['timeline', 'motors', 'battery', 'gps', 'vibration', 'control', 'environment', 'flight-path'],
    heroSubsystem: 'timeline',
    priorityPlugins: ['crash_detection', 'failsafe_events', 'operator_action_sequence', 'gps_health'],
    showCrashBanner: true,
    showHypotheses: true,
    showPhaseTimeline: true,
    showMini3D: true,
    showEvidenceBadge: true, // ALWAYS show for gov
    showSaveAsCase: true,
    defaultReportType: 'CrashMishapReport',
    primaryAction: 'Open Investigation',
    primaryActionDesc: 'Create forensic case with full audit trail',
  },

  factory: {
    id: 'factory',
    name: 'Factory QA',
    icon: '🏭',
    description: 'Production QA — pass/fail, batch testing',
    // Factory: quick pass/fail, motor balance, vibration
    subsystemOrder: ['motors', 'vibration', 'battery', 'control', 'gps', 'timeline', 'environment', 'flight-path'],
    heroSubsystem: 'motors',
    priorityPlugins: ['motor_saturation', 'vibration', 'battery_sag', 'attitude_tracking'],
    showCrashBanner: true,
    showHypotheses: false, // factory doesn't need root cause speculation
    showPhaseTimeline: false,
    showMini3D: false,
    showEvidenceBadge: true,
    showSaveAsCase: true,
    defaultReportType: 'QAValidationReport',
    primaryAction: 'QA Result',
    primaryActionDesc: 'Pass or fail this unit',
  },

  advanced: {
    id: 'advanced',
    name: 'Advanced',
    icon: '⚡',
    description: 'All plugins, all detail, no guardrails',
    subsystemOrder: ['motors', 'battery', 'gps', 'vibration', 'control', 'environment', 'flight-path', 'timeline'],
    heroSubsystem: null,
    priorityPlugins: [],
    showCrashBanner: true,
    showHypotheses: true,
    showPhaseTimeline: true,
    showMini3D: true,
    showEvidenceBadge: true,
    showSaveAsCase: true,
    defaultReportType: 'ForensicCaseReport',
    primaryAction: 'Deep Dive',
    primaryActionDesc: 'All 17 plugins, maximum detail',
  },
}

export function getProfileConfig(profileId: string): ProfileUIConfig {
  return profileConfigs[profileId] || profileConfigs.default
}

// Subsystem metadata for rendering
export const subsystemMeta: Record<string, { label: string; icon: string; desc: string; color: string }> = {
  motors: { label: 'Motors', icon: '⚙️', desc: 'Saturation, imbalance, headroom', color: 'from-goose-chart-1/10' },
  battery: { label: 'Battery', icon: '🔋', desc: 'Voltage sag, cell health, temperature', color: 'from-goose-chart-3/10' },
  gps: { label: 'GPS / Nav', icon: '📡', desc: 'Fix quality, HDOP, EKF fusion', color: 'from-goose-chart-7/10' },
  vibration: { label: 'Vibration', icon: '📳', desc: 'RMS, clipping, spectrum analysis', color: 'from-goose-chart-4/10' },
  control: { label: 'Control', icon: '🎮', desc: 'Attitude tracking, RC signal', color: 'from-goose-chart-5/10' },
  environment: { label: 'Environment', icon: '🌬️', desc: 'Wind estimation, conditions', color: 'from-goose-chart-2/10' },
  'flight-path': { label: 'Flight Path', icon: '🗺️', desc: '3D GPS track & replay', color: 'from-goose-accent/10' },
  timeline: { label: 'Timeline', icon: '📊', desc: 'Anomaly timeline & events', color: 'from-goose-chart-6/10' },
}
