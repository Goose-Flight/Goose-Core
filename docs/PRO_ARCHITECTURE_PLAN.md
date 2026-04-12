# Goose Pro — Complete Architecture & Planning Document

## 1. System Overview

Goose Pro is a local-first forensic validation platform for GPS-denied navigation systems. It manages **test campaigns** across drone **fleets**, running standardized **validation protocols** with forensic-grade evidence chains. Every test run, every finding, every decision is logged, hashed, and auditable.

```
┌─────────────────────────────────────────────────────────────────┐
│                        GOOSE PRO                                 │
│                                                                  │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │   Auth    │  │  Test Campaign│  │   Fleet     │  │ Reports  │ │
│  │  & Roles  │  │  Management  │  │ Management  │  │ & Export │ │
│  └──────────┘  └──────────────┘  └─────────────┘  └──────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                  VALIDATION ENGINE                           ││
│  │  Ground Truth Ingest → Time Alignment → Plugin Pipeline     ││
│  │  → Accuracy Metrics → Pass/Fail → Hypothesis → Report       ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                  FORENSIC CORE (inherited)                   ││
│  │  Evidence hashing, Audit trail, Chain of custody, Cases      ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                  DATA LAYER                                  ││
│  │  SQLite (local) → Encrypted at rest → File-based cases      ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Authentication & Authorization

### 2.1 Auth Architecture

Pro runs locally — there's no cloud server to authenticate against. Auth serves two purposes:
1. **Identity** — who is performing this action (for audit trail)
2. **Authorization** — what are they allowed to do

```
Auth Model: Local User Database + Role-Based Access Control (RBAC)

┌─────────────────────────────────────────┐
│            Local Auth Store              │
│  (SQLite, encrypted with master key)    │
│                                         │
│  Users table:                           │
│    user_id, username, display_name,     │
│    password_hash (argon2), role,        │
│    created_at, last_login, status       │
│                                         │
│  Sessions table:                        │
│    session_id, user_id, token_hash,     │
│    created_at, expires_at, ip           │
│                                         │
│  Audit table:                           │
│    entry_id, user_id, action, target,   │
│    timestamp, details_json, ip          │
└─────────────────────────────────────────┘
```

### 2.2 Roles & Permissions

| Role | Can View | Can Analyze | Can Create Cases | Can Manage Fleet | Can Admin | Can Export |
|------|---------|-------------|-----------------|-----------------|-----------|-----------|
| **Viewer** | All results & reports | No | No | No | No | View only |
| **Analyst** | All | Run analysis | Yes | No | No | Yes |
| **Test Engineer** | All | Run analysis | Yes | Yes (own fleet) | No | Yes |
| **Lead Engineer** | All | Run analysis | Yes | Yes (all) | No | Yes + sign-off |
| **Program Manager** | All | No | Yes | Yes | No | Yes + approve |
| **Admin** | All | All | All | All | Yes | All |

### 2.3 Granular Permission Matrix

```
Permissions (bit flags — composable):

EVIDENCE:
  evidence.upload          — upload flight logs & ground truth
  evidence.view            — view evidence files and hashes
  evidence.delete          — delete evidence (DANGEROUS — audited)
  evidence.export          — download evidence files

ANALYSIS:
  analysis.run             — execute analysis plugins
  analysis.configure       — change plugin config / thresholds
  analysis.view_findings   — view findings and hypotheses
  
CASES:
  case.create              — create new investigation cases
  case.view                — view case details
  case.close               — close/archive cases
  case.delete              — delete cases (DANGEROUS — audited)
  
FLEET:
  fleet.view               — view drone registry
  fleet.manage             — add/edit/retire drones
  fleet.assign             — assign drones to test campaigns
  
CAMPAIGNS:
  campaign.create          — create test campaigns
  campaign.view            — view campaign status
  campaign.manage          — edit campaigns, add test runs
  campaign.approve         — sign off on campaign results
  
REPORTS:
  report.generate          — generate validation reports
  report.view              — view generated reports
  report.sign              — digitally sign reports
  report.export            — export reports (PDF/HTML/JSON)
  
ADMIN:
  admin.users              — manage user accounts
  admin.roles              — manage role assignments
  admin.config             — system configuration
  admin.audit              — view full audit log
  admin.backup             — backup/restore database
```

### 2.4 Auth Flow

```
1. First Launch (Setup):
   - No users exist → force admin account creation
   - Set master encryption key (derives from admin password + salt)
   - Create initial admin user
   - Admin creates other users and assigns roles

2. Login:
   - Username + password → argon2 verify
   - Generate session token (32-byte random)
   - Store session in DB (token hash, not plaintext)
   - Inject token into browser session
   - All API calls require valid session token

3. Session Management:
   - Sessions expire after configurable timeout (default 8 hours)
   - "Remember me" extends to 30 days
   - Concurrent sessions per user: configurable (default 3)
   - Force logout via admin panel

4. Audit:
   - EVERY action logged: who, what, when, target, result
   - Login attempts (success + failure)
   - Evidence uploads, analysis runs, report generation
   - Permission changes, user management
   - Append-only — cannot be edited or deleted
```

---

## 3. Data Architecture

### 3.1 Storage Layout

```
goose-pro-data/                        # Root data directory
├── config/
│   ├── goose-pro.yaml                 # System configuration
│   ├── auth.db                        # User database (encrypted)
│   └── encryption.key                 # Master key (derived, never stored in plaintext)
│
├── fleet/
│   ├── fleet.db                       # Drone registry database
│   └── drones/
│       ├── DRN-001/
│       │   ├── metadata.json          # Drone specs, config
│       │   ├── nav_system.json        # Nav system under test details
│       │   └── maintenance.json       # Maintenance history
│       └── DRN-002/
│           └── ...
│
├── campaigns/
│   ├── campaigns.db                   # Campaign registry
│   └── CAMP-2026-001/
│       ├── campaign.json              # Campaign metadata & config
│       ├── protocol.json              # Test protocol definition
│       ├── thresholds.json            # Pass/fail criteria
│       ├── runs/
│       │   ├── RUN-001/
│       │   │   ├── run.json           # Run metadata
│       │   │   ├── evidence/          # Flight log + ground truth
│       │   │   │   ├── flight.ulg     # SHA-256 hashed
│       │   │   │   └── truth.csv      # SHA-256 hashed
│       │   │   ├── aligned/           # Time-aligned datasets
│       │   │   │   └── aligned.parquet
│       │   │   ├── analysis/          # Plugin results
│       │   │   │   └── findings.json
│       │   │   └── audit/             # Per-run audit trail
│       │   │       └── audit.jsonl
│       │   ├── RUN-002/
│       │   │   └── ...
│       │   └── RUN-010/
│       │       └── ...
│       ├── comparison/                # Cross-run analysis
│       │   └── multi_run_results.json
│       ├── reports/                   # Generated reports
│       │   ├── validation_report.pdf
│       │   └── validation_report.html
│       └── audit/                     # Campaign-level audit
│           └── audit.jsonl
│
├── cases/                             # Investigation cases (inherited from Core)
│   └── CASE-2026-000001/
│       └── ... (existing structure)
│
└── audit/                             # Global audit log
    └── global_audit.jsonl             # Append-only, all actions
```

### 3.2 Encryption at Rest

```
Encryption Strategy:
  - Master key derived from admin password via Argon2id (memory-hard)
  - SQLite databases encrypted with SQLCipher (AES-256)
  - Evidence files: SHA-256 integrity hash stored separately
  - Encryption key never stored in plaintext — derived at runtime
  - Optional: FIPS 140-2 mode for mil customers

What's encrypted:
  ✅ auth.db (user credentials, sessions)
  ✅ fleet.db (drone details may be sensitive)
  ✅ campaigns.db (test results, pass/fail)
  ✅ Evidence files at rest (optional — configurable)
  
What's NOT encrypted (for performance):
  ❌ Aligned datasets (derived from evidence — regenerable)
  ❌ Generated reports (user explicitly exported them)
  ❌ Audit logs (must be readable for compliance)
```

### 3.3 Data Classification

| Data Type | Classification | Encryption | Access Control |
|-----------|---------------|------------|----------------|
| User credentials | SENSITIVE | Always encrypted (argon2 hash) | Admin only |
| Evidence files | CONFIGURABLE | Optional AES-256 | evidence.view permission |
| Ground truth | CONFIGURABLE | Optional AES-256 | evidence.view permission |
| Analysis results | INTERNAL | SQLCipher DB | analysis.view_findings |
| Audit trail | COMPLIANCE | Plaintext (append-only, tamper-evident) | admin.audit |
| Reports | EXPORT | Not encrypted (exported by user) | report.view |
| Drone metadata | INTERNAL | SQLCipher DB | fleet.view |
| Campaign config | INTERNAL | SQLCipher DB | campaign.view |

---

## 4. Test Campaign Workflow

### 4.1 End-to-End Flow

```
Step 1: SETUP CAMPAIGN
├── Create campaign (name, description, nav system under test)
├── Select drone from fleet (or register new one)
├── Define test protocol (which test cases to run)
├── Set pass/fail thresholds per test case
├── Assign test engineer
└── [Audit: campaign.created by user at timestamp]

Step 2: EXECUTE TEST FLIGHTS
├── For each test case in protocol:
│   ├── Fly the drone per test case instructions
│   ├── Record flight log (.ulg/.bin)
│   ├── Record ground truth (RTK GPS, MoCap, etc.)
│   └── Note environmental conditions
└── [Audit: test_flight.completed per run]

Step 3: INGEST EVIDENCE
├── Upload flight log → SHA-256 hash generated
├── Upload ground truth → SHA-256 hash generated
├── Enter run metadata (conditions, pilot, notes)
├── System auto-detects log format
├── Ground truth alignment runs automatically
└── [Audit: evidence.ingested per file, hashes recorded]

Step 4: RUN VALIDATION
├── System runs validation plugin pipeline:
│   ├── ground_truth_ingest → time-align truth + nav
│   ├── nav_accuracy_validator → CEP, R95, RMS
│   ├── trajectory_comparator → cross/along-track error
│   ├── drift_rate_analyzer → drift per minute
│   ├── gps_denial_analyzer → transition metrics
│   └── sensor_fusion_validator → EKF health
├── Each plugin emits ForensicFindings with evidence refs
├── Hypothesis engine generates root-cause candidates
├── Pass/fail evaluated against campaign thresholds
└── [Audit: analysis.completed, findings.generated]

Step 5: REVIEW RESULTS
├── Test engineer reviews per-run results
├── Lead engineer reviews cross-run comparison
├── Flag any failed test cases
├── Add manual observations / notes
├── Approve or reject individual runs
└── [Audit: run.reviewed, run.approved/rejected by user]

Step 6: MULTI-RUN COMPARISON
├── Aggregate metrics across all runs
├── Statistical analysis (mean, σ, confidence intervals)
├── Repeatability scoring
├── Identify outlier runs
├── Generate cross-run summary
└── [Audit: comparison.generated]

Step 7: GENERATE REPORT
├── Select report template (validation, compliance, etc.)
├── System assembles findings, metrics, evidence chain
├── Lead engineer reviews and signs report
├── Program manager approves
├── Export as PDF/HTML with embedded evidence hashes
└── [Audit: report.generated, report.signed, report.approved]

Step 8: EXPORT & DELIVER
├── Export campaign bundle (all evidence, results, audit trail)
├── Bundle is version-stamped and hash-verified
├── Deliver to customer / program office
└── [Audit: campaign.exported]
```

### 4.2 Required vs Optional Data

**REQUIRED for every test run:**
```
✅ Flight log file (.ulg, .bin, .log)
✅ Test case ID (which protocol step)
✅ Drone ID (which aircraft)
✅ Date and time
✅ Operator/pilot name
```

**REQUIRED for validation (at least one):**
```
✅ Ground truth file (RTK, MoCap, PPK, or surveyed waypoints)
   — Without ground truth, can only do relative analysis (drift, consistency)
   — With ground truth, can compute absolute accuracy (CEP, R95)
```

**OPTIONAL but recommended:**
```
◻ Environmental conditions (wind, temp, visibility)
◻ Nav system configuration (software version, parameters)
◻ Mission plan / planned route
◻ Photos/video of test setup
◻ Pilot notes / observations
◻ Equipment serial numbers
◻ Battery condition (cell count, cycles, IR)
```

**AUTO-CAPTURED (from flight log):**
```
🔄 Duration, mode changes, events
🔄 Sensor data (IMU, mag, baro)
🔄 Nav solution (position, velocity, attitude)
🔄 EKF state and innovations
🔄 GPS status (if available for denial detection)
🔄 Motor outputs, battery telemetry
```

---

## 5. UI Design

### 5.1 Pro Navigation Structure

```
Sidebar (when logged into Pro):

QUICK TOOLS
  ├── Dashboard (campaign overview, fleet status, recent activity)
  ├── Quick Analysis (same as Core — instant single-file analysis)
  
TEST MANAGEMENT
  ├── Campaigns (list, create, manage test campaigns)
  ├── Test Protocols (define test case libraries)
  ├── Fleet (drone registry + nav system configs)
  
RESULTS (active campaign context)
  ├── Overview (campaign summary, pass/fail dashboard)
  ├── Test Runs (list of runs with status)
  ├── Accuracy (CEP/R95 charts, error distributions)
  ├── Trajectory (3D dual-track overlay)
  ├── Drift (drift rate analysis)
  ├── GPS Denial (denial event timeline)
  ├── Sensor Fusion (EKF health)
  ├── Comparison (multi-run statistics)
  ├── Timeline (anomaly timeline)
  
INVESTIGATION
  ├── Cases (forensic investigation cases)
  
REPORTING
  ├── Reports (generate, view, sign, export)
  ├── Compliance (MIL-STD templates)
  
ADMIN
  ├── Users & Roles
  ├── Audit Trail
  ├── Settings
  ├── Backup
```

### 5.2 Key UI Pages

**Campaign Dashboard:**
```
┌─────────────────────────────────────────────────────────────┐
│  Campaign: "VIO System v2.1 Acceptance Test"                │
│  Status: In Progress    Drone: SURVEY-04    NAV: VisNav 2.1│
│                                                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ 12 Runs │ │ 9 Pass  │ │ 2 Fail  │ │ 1 Open  │          │
│  │ Total   │ │ 75%     │ │ 17%     │ │ 8%      │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
│                                                              │
│  Test Case Matrix:                                          │
│  ┌──────────────────┬────────┬───────┬───────────┐          │
│  │ Test Case        │ Status │ CEP   │ Pass/Fail │          │
│  ├──────────────────┼────────┼───────┼───────────┤          │
│  │ NAV-001 Cruise   │ ✅ 3/3 │ 1.2m  │ PASS      │          │
│  │ NAV-002 Orbit    │ ✅ 3/3 │ 3.8m  │ PASS      │          │
│  │ NAV-003 Denial   │ ⚠️ 2/3 │ 4.1m  │ MARGINAL  │          │
│  │ NAV-005 Obscured │ ❌ 1/3 │ 14.2m │ FAIL      │          │
│  │ NAV-010 Repeat   │ 🔄 0/3 │ —     │ PENDING   │          │
│  └──────────────────┴────────┴───────┴───────────┘          │
│                                                              │
│  [Run Next Test]  [Generate Report]  [Export Campaign]      │
└─────────────────────────────────────────────────────────────┘
```

**Accuracy Dashboard (per run or aggregated):**
```
┌─────────────────────────────────────────────────────────────┐
│  Accuracy Analysis — Run NAV-001-R03                        │
│                                                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ CEP     │ │ R95     │ │ RMS     │ │ Max Err │          │
│  │ 1.23m   │ │ 3.45m   │ │ 1.67m   │ │ 5.82m   │          │
│  │ ✅ PASS │ │ ✅ PASS │ │ ✅ PASS │ │ ⚠️ WARN │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
│                                                              │
│  Per-Axis Error:                                            │
│  ┌──────┬───────┬───────┬───────┐                           │
│  │ Axis │ Mean  │ σ     │ Max   │                           │
│  ├──────┼───────┼───────┼───────┤                           │
│  │ N    │ 0.3m  │ 0.8m  │ 2.1m  │                           │
│  │ E    │ -0.1m │ 1.1m  │ 4.8m  │                           │
│  │ D    │ 0.5m  │ 0.4m  │ 1.2m  │                           │
│  └──────┴───────┴───────┴───────┘                           │
│                                                              │
│  [Error Distribution Chart]  [Error Over Time Chart]        │
│  [CEP Circle Plot]           [Per-Axis Time Series]         │
└─────────────────────────────────────────────────────────────┘
```

**Trajectory Overlay (3D dual-track):**
```
┌─────────────────────────────────────────────────────────────┐
│  Trajectory Comparison                                       │
│                                                              │
│  ┌─────────────────────────────────────────────┐            │
│  │                                              │            │
│  │    ──── Nav Solution (colored by error)      │            │
│  │    - - - Ground Truth (green dashed)         │            │
│  │    ╌╌╌╌ Planned Route (grey)                 │            │
│  │                                              │            │
│  │         [Interactive 3D Plotly View]         │            │
│  │    Drag to rotate, scroll to zoom            │            │
│  │                                              │            │
│  └─────────────────────────────────────────────┘            │
│                                                              │
│  Color: [Error Magnitude] [Altitude] [Speed]                │
│  Show:  [✓ Nav] [✓ Truth] [□ Planned] [□ Error Vectors]    │
│                                                              │
│  Cross-Track Error: avg 0.8m, max 4.2m                      │
│  Along-Track Error: avg 1.2m, max 3.1m                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Fleet & Nav System Management

### 6.1 Drone Registry

Each drone has a complete profile:

```json
{
  "drone_id": "DRN-2026-004",
  "name": "SURVEY-04",
  "type": "quadcopter",
  "make": "Holybro",
  "model": "X500 V2",
  "serial": "HB-X500-2024-0847",
  "status": "active",
  "autopilot": "px4",
  "firmware_version": "v1.15.0",
  
  "nav_system": {
    "vendor": "NavTech Inc",
    "product": "VisNav 2.1",
    "version": "2.1.3",
    "sensor_type": "vio",
    "cameras": ["Intel RealSense D435i"],
    "imu": "BMI088",
    "processing": "NVIDIA Jetson Orin Nano",
    "px4_integration": "ODOMETRY",
    "config_params": {
      "EKF2_AID_MASK": 24,
      "EKF2_EV_DELAY": 50,
      "EKF2_HGT_MODE": 3
    }
  },
  
  "battery": {
    "type": "LiPo",
    "cells": 4,
    "capacity_mah": 5200,
    "cycles": 47
  },
  
  "total_flights": 127,
  "total_hours": 48.3,
  "last_flight": "2026-04-11",
  "last_maintenance": "2026-04-01",
  "campaigns": ["CAMP-2026-001", "CAMP-2026-003"],
  
  "created_by": "josh",
  "created_at": "2026-01-15T10:00:00Z"
}
```

### 6.2 Nav System Profiles

Reusable profiles for different nav systems under test:

```json
{
  "nav_profile_id": "NAVP-001",
  "vendor": "NavTech Inc",
  "product": "VisNav",
  "version": "2.1.3",
  "sensor_type": "vio",
  "description": "Stereo VIO with Intel RealSense D435i",
  "px4_message_type": "ODOMETRY",
  "expected_accuracy_cep": 3.0,
  "expected_drift_rate": 1.5,
  "validation_thresholds": {
    "cep_pass": 5.0,
    "cep_marginal": 8.0,
    "r95_pass": 10.0,
    "drift_rate_pass": 2.0,
    "transition_latency_pass": 2000
  }
}
```

---

## 7. Validation Plugin Specifications

### 7.1 Ground Truth Ingest Plugin

**Purpose**: Load, validate, and time-align ground truth data with flight log data.

```
Input:
  - truth_file: CSV/RINEX with columns [timestamp, lat, lon, alt] or [timestamp, x, y, z]
  - flight: Flight object from parser
  - clock_offset: optional manual time offset (ms)

Processing:
  1. Detect truth file format (CSV columns, RINEX, NatNet)
  2. Parse into [timestamp, position] array
  3. Detect time reference (UTC, GPS time, relative)
  4. Auto-align with flight log timestamps:
     a. Cross-correlate altitude profiles (robust to clock offset)
     b. Find best-fit time offset
     c. Apply offset and interpolate truth to flight log rate
  5. Validate alignment quality (correlation coefficient)
  6. Generate aligned dataset: [timestamp, nav_pos, truth_pos, error]

Output:
  - AlignedDataset object (stored as parquet)
  - Alignment quality score
  - Time offset applied
  - ForensicFinding if alignment quality is poor

Required: YES (for absolute accuracy validation)
Optional: NO truth = relative-only analysis (drift, consistency)
```

### 7.2 Nav Accuracy Validator Plugin

**Purpose**: Compute absolute position accuracy metrics.

```
Input:
  - AlignedDataset (from ground_truth_ingest)
  - Pass/fail thresholds from campaign config

Computes:
  - Horizontal error at each timestamp: sqrt((nav_n - truth_n)² + (nav_e - truth_e)²)
  - Vertical error: |nav_d - truth_d|
  - 3D error: sqrt(h_error² + v_error²)
  - CEP (50th percentile horizontal error)
  - R95 (95th percentile horizontal error)
  - RMS error (root mean square)
  - Max error
  - Per-axis: North error, East error, Down error (mean, σ, max)
  - Error distribution (histogram)
  - Error over time (time series)
  - Error vs flight phase correlation

Pass/Fail:
  - PASS: CEP < threshold AND R95 < threshold
  - MARGINAL: CEP < threshold but R95 > threshold
  - FAIL: CEP > threshold

Output:
  - ForensicFinding with accuracy metrics in supporting_metrics
  - Severity: pass/warning/critical based on thresholds
  - Evidence references to aligned dataset time ranges
```

### 7.3 GPS Denial Analyzer Plugin

**Purpose**: Detect GPS denial events and measure nav system response.

```
Input:
  - Flight object with GPS status, EKF flags, nav solution
  - AlignedDataset (optional — for accuracy during denial)

Processing:
  1. Detect GPS denial events:
     a. GPS fix type drops to 0 or NO_FIX
     b. Satellite count drops to 0
     c. EKF2_AID_MASK changes (GPS aid removed)
     d. Manual denial flag in flight log
  2. For each denial event:
     a. Record onset time, duration, recovery time
     b. Measure position jump at denial onset
     c. Measure accuracy BEFORE denial (baseline)
     d. Measure accuracy DURING denial
     e. Measure accuracy AFTER recovery
     f. Compute drift rate during denial
     g. Check if EKF remained healthy
  3. Aggregate across all denial events

Output per event:
  - ForensicFinding:
    - denial_onset_time
    - denial_duration_sec
    - transition_latency_ms (time to switch to backup nav)
    - position_jump_m (discontinuity at transition)
    - drift_rate_m_per_min (during denial)
    - accuracy_before_cep (baseline)
    - accuracy_during_cep (degraded)
    - accuracy_after_cep (post-recovery)
    - recovery_convergence_time_sec
    - ekf_healthy_during_denial (bool)
```

### 7.4 Drift Rate Analyzer Plugin

```
Input:
  - AlignedDataset
  
Computes:
  - Position error over time → linear regression → drift rate (m/min)
  - Drift acceleration (is drift rate increasing?)
  - Drift direction (systematic bias vector)
  - Drift vs flight phase (hover vs cruise vs maneuver)
  - Time-to-threshold (when will error exceed X meters?)
  - Cumulative drift over entire flight

Output:
  - ForensicFinding with drift_rate_m_per_min, drift_direction_deg, cumulative_drift_m
  - Pass/fail against threshold
```

### 7.5 Multi-Run Comparator Plugin

```
Input:
  - List of AlignedDatasets from multiple runs of same test case
  
Computes:
  - Per-run: CEP, R95, RMS, drift rate
  - Across runs: mean, σ, min, max for each metric
  - Confidence intervals (95% CI)
  - Outlier detection (runs > 2σ from mean)
  - Repeatability score (0-100)
  - Trend detection (is accuracy improving/degrading across runs?)

Output:
  - MultiRunComparison object with statistical summary
  - Per-run pass/fail status
  - Overall campaign pass/fail determination
  - Identified outlier runs for investigation
```

---

## 8. Report Templates

### 8.1 Validation Report (primary deliverable)

```
NAVIGATION SYSTEM VALIDATION REPORT

1. Executive Summary
   - System under test, test dates, overall result
   - Key metrics (CEP, R95, drift rate)
   - Pass/fail determination with confidence level

2. Test Configuration
   - Drone platform details
   - Nav system specification
   - Ground truth system used
   - Test environment description

3. Test Protocol
   - List of test cases executed
   - Pass/fail criteria for each

4. Results by Test Case
   - NAV-001: [detailed metrics, charts, pass/fail]
   - NAV-002: [...]
   - ...

5. Statistical Analysis
   - Multi-run comparison
   - Confidence intervals
   - Repeatability assessment

6. GPS Denial Performance
   - Denial event analysis
   - Transition metrics
   - Drift during denial

7. Findings & Recommendations
   - Forensic findings from all plugins
   - Hypothesis engine results
   - Recommended actions

8. Evidence Chain
   - SHA-256 hashes of all input files
   - Analysis engine version
   - Plugin versions
   - Audit trail excerpt

Appendices:
  A. Raw accuracy data
  B. Time-series plots
  C. Full audit trail
  D. Glossary of terms
```

---

## 9. Implementation Plan

### Phase 0: Auth System (2 weeks)
- Local user database (SQLCipher)
- Login UI (React page)
- RBAC middleware for FastAPI
- Session management
- Audit logging for auth events

### Phase 1: Ground Truth Pipeline (4 weeks)
- CSV/RINEX parser for truth data
- Time alignment engine (cross-correlation)
- AlignedDataset data model
- Upload UI for truth files
- Alignment preview/verification page

### Phase 2: Core Validation Plugins (6 weeks)
- nav_accuracy_validator (CEP, R95, RMS)
- trajectory_comparator (cross/along-track)
- drift_rate_analyzer
- gps_denial_analyzer

### Phase 3: Campaign Management (4 weeks)
- Campaign CRUD (API + UI)
- Test protocol definition
- Run management (create, track, approve)
- Pass/fail threshold configuration
- Campaign dashboard UI

### Phase 4: Advanced Plugins (4 weeks)
- sensor_fusion_validator
- nav_latency_analyzer
- multi_run_comparator
- environmental_classifier

### Phase 5: Reporting (3 weeks)
- Validation report template
- Compliance report template
- Report builder UI
- Digital signature support
- PDF/HTML export

### Phase 6: Fleet Integration (2 weeks)
- Nav system profile management
- Drone-to-campaign linking
- Fleet-wide trend dashboards
- Historical accuracy tracking

### Phase 7: Polish & Security (2 weeks)
- Encryption at rest
- Data export/import
- Backup/restore
- Penetration testing
- Documentation

**Total: ~27 weeks (6-7 months)**
**With 2 developers: ~18-20 weeks (4-5 months)**

---

## 10. Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Auth DB | SQLCipher (encrypted SQLite) | Local-first, no server needed, encrypted |
| Password hashing | Argon2id | Memory-hard, recommended by OWASP |
| Session tokens | 32-byte random, SHA-256 hashed in DB | Standard practice |
| Data alignment | Cross-correlation + interpolation | Robust to clock offsets |
| Accuracy metrics | NumPy/SciPy | Already in stack, fast |
| Statistical analysis | SciPy stats | Confidence intervals, distributions |
| Report generation | WeasyPrint (PDF) + Jinja2 (HTML) | Already in Core dependencies |
| Data format | Parquet for aligned datasets | Columnar, fast, compact |
| Encryption | AES-256-GCM via SQLCipher + cryptography lib | FIPS-capable |

---

*This document is the technical specification for Goose Pro's GPS-denied navigation validation suite. It covers authentication, authorization, data architecture, workflow, plugins, UI, and implementation plan.*
