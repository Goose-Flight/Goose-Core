# Goose Pro — GPS-Denied Navigation Validation Suite

## Strategic Vision

GPS-denied navigation is the hottest space in military drone tech. Companies building VIO, TRN, SLAM, celestial nav, and magnetic nav systems are closing mil deals in weeks. But every one of these companies needs a way to **validate and prove** their systems work.

**Goose Pro's lane**: We don't compete on nav tech. We're the **validation and forensic platform** they ALL need. The test bench, the evidence chain, the proof.

## Three Use Cases

### 1. Validation Testing (Pre-Deployment)
- "Does our nav system meet spec?"
- Controlled test flights compared against ground truth
- Pass/fail reports for mil customer acceptance
- Statistical confidence across N test runs

### 2. Crash/Mishap Investigation (Post-Incident)
- "Our nav system was on a drone that crashed — was it our fault?"
- Forensic analysis: what did the nav solution do vs what it should have done?
- Root cause: when/where/why did the nav diverge?
- Evidence chain for legal/insurance/contract disputes

### 3. Continuous Monitoring (Operations)
- "Is our nav system degrading over time?"
- Fleet-wide accuracy trends across hundreds of missions
- Drift rate tracking, sensor fusion health
- Predictive recalibration alerts

## Target Users

| User | Use Case | What They Need | Price Point |
|------|----------|---------------|-------------|
| Nav system engineers | Validation | Accuracy metrics, pass/fail, statistical confidence | $500-2K/seat/yr |
| Test pilots / operators | Validation | Test protocol management, run tracking | Included |
| Safety officers | Investigation | Root cause, evidence chain, timeline | $500-2K/seat/yr |
| Accident investigators | Investigation | Forensic reports, chain of custody | Enterprise |
| Fleet operations | Monitoring | Trend dashboards, degradation alerts | Enterprise |
| Mil program managers | All | Compliance reports, acceptance evidence | $50-100K contract |

## GPS-Denied Nav Tech Landscape

### Sensor Technologies Being Validated

| Sensor | Tech | Accuracy | PX4 Integration |
|--------|------|----------|-----------------|
| VIO (Visual-Inertial Odometry) | Stereo cameras + IMU | 0.1-2% drift | VISION_POSITION_ESTIMATE |
| TRN (Terrain-Relative Navigation) | Downward camera + terrain DB | 5-50m absolute | GPS_INPUT (synthetic) |
| SLAM | Cameras/LiDAR | Sub-meter relative | ODOMETRY |
| Celestial Nav | Star tracker / sun sensor | ~100m absolute | GPS_INPUT |
| Magnetic Nav | Magnetometer array | 10-100m absolute | GPS_INPUT |
| RF Nav (Signals of Opportunity) | Cell/radio towers | 10-50m | GPS_INPUT |

### PX4 Integration Points
- `VISION_POSITION_ESTIMATE` — external vision system position
- `ODOMETRY` — visual/inertial odometry (preferred for VIO)
- `ATT_POS_MOCAP` — motion capture (lab/indoor testing)
- `GPS_INPUT` — synthetic GPS from any nav source
- EKF2 params: `EKF2_AID_MASK`, `EKF2_EV_DELAY`, `EKF2_HGT_MODE`
- EKF2 innovations: velocity, position, heading test ratios

## Pro Plugin Architecture

### New Plugins (GPS-Denied Validation Suite)

```
goose_pro/plugins/
├── nav_accuracy_validator.py      # CEP, R95, RMS error vs ground truth
├── trajectory_comparator.py       # Cross-track / along-track error
├── gps_denial_analyzer.py         # Detect denial events, measure transition
├── drift_rate_analyzer.py         # Position drift per minute/hour
├── sensor_fusion_validator.py     # EKF innovation analysis for external nav
├── nav_latency_analyzer.py        # Processing delay, update rate gaps
├── multi_run_comparator.py        # Run-to-run repeatability scoring
├── ground_truth_ingest.py         # RTK/MoCap truth alignment
├── environmental_classifier.py    # Correlate accuracy vs conditions
└── compliance_report_gen.py       # MIL-STD report templates
```

### Data Flow

```
Inputs:
  Flight log (.ulg/.bin)     ──┐
  Ground truth (.csv/.rinex) ──┼── Ground Truth Ingest ──┐
  Mission plan (.json)       ──┘                         │
                                                         ▼
                                              Time-aligned dataset
                                                         │
                    ┌────────────────────────────────────┼────────────────────────┐
                    │                  │                  │                       │
                    ▼                  ▼                  ▼                       ▼
            Nav Accuracy       Trajectory          GPS Denial            Drift Rate
            Validator          Comparator           Analyzer              Analyzer
                    │                  │                  │                       │
                    └──────────┬───────┘                  └───────────┬───────────┘
                               │                                     │
                               ▼                                     ▼
                        ForensicFindings                    ForensicFindings
                               │                                     │
                               └──────────────┬──────────────────────┘
                                              │
                                              ▼
                                     Hypothesis Engine
                                     Compliance Reports
                                     Case Bundle Export
```

### Key Metrics Computed

**Accuracy Metrics:**
- CEP (Circular Error Probable) — 50% of positions within X meters
- R95 — 95% within X meters
- RMS error — root mean square position error
- Per-axis error (North, East, Down)
- Max error and error percentiles

**Drift Metrics:**
- Drift rate (m/min, m/hr)
- Drift acceleration (is it getting worse?)
- Drift direction (systematic bias?)
- Drift vs flight phase correlation

**Transition Metrics:**
- GPS denial detection latency (ms)
- Position jump at transition (m)
- Convergence time after GPS recovery (s)
- EKF health during transitions

**Repeatability Metrics:**
- Run-to-run position variance (σ)
- Consistency score (0-100)
- Statistical confidence interval
- Outlier detection across runs

## Test Case Matrix

| ID | Scenario | Measured | Example Pass Criteria |
|----|----------|----------|----------------------|
| NAV-001 | Straight cruise, GPS denied | Drift rate | < 2m/min |
| NAV-002 | Orbit pattern, GPS denied | CEP | < 5m after 10min |
| NAV-003 | GPS denial onset | Transition latency | < 2s |
| NAV-004 | GPS recovery | Convergence time | < 10s to < 2m error |
| NAV-005 | Camera obscured | IMU-only fallback drift | < 10m/min |
| NAV-006 | High vibration | Accuracy under stress | CEP < 10m |
| NAV-007 | Night flight | IR sensor accuracy | Within 2x daytime CEP |
| NAV-008 | Urban canyon | Multipath handling | < 5m error |
| NAV-009 | Featureless terrain | Vision degradation | Detect and flag |
| NAV-010 | Multi-run (10x) | Repeatability | σ < 2m |
| NAV-011 | Long endurance (60min+) | Cumulative drift | < 50m total |
| NAV-012 | Dynamic maneuvers | Accuracy in turns | CEP < 8m |

## Ground Truth Sources

| Source | Accuracy | Use Case | Format |
|--------|----------|----------|--------|
| RTK GPS | 1-2cm | Outdoor validation (when GPS available as truth) | RINEX, .csv |
| PPK GPS | 2-5cm | Post-processed outdoor truth | RINEX |
| Motion Capture | sub-mm | Indoor lab testing | .csv, NatNet |
| Surveyed Waypoints | cm-level | Fixed-point accuracy checks | .json, .csv |
| LiDAR SLAM | 2-5cm | Reference trajectory | .csv |
| Total Station | mm-level | Precision ground truth | .csv |

## UI Components Needed

### New Pages (Pro)
- **Validation Dashboard** — test campaign overview, pass/fail summary
- **Ground Truth Upload** — ingest RTK/MoCap data, preview alignment
- **Trajectory Comparison** — dual-track 3D overlay (truth vs estimate)
- **Accuracy Report** — CEP/R95 plots, error distribution, per-axis breakdown
- **GPS Denial Timeline** — detect and annotate denial events
- **Multi-Run Comparison** — statistical analysis across test flights
- **Test Protocol Manager** — define test cases, track execution, record results
- **Compliance Report Builder** — select MIL-STD template, assemble evidence

### Enhanced Existing Pages
- **3D Flight Path** — overlay ground truth trajectory (dashed green line)
- **GPS/Nav page** — add nav system source indicators (GPS vs VIO vs TRN)
- **EKF page** — show external nav innovation ratios
- **Anomaly Timeline** — GPS denial events as a special category

## Why This Must Be Local

1. Mil customers won't upload classified nav data to cloud
2. Test data is often CUI (Controlled Unclassified Information)
3. Air-gapped labs can't reach internet
4. Evidence integrity requires local chain of custody
5. Labs operate on classified networks (SIPR, JWICS)
6. Some nav algorithms themselves are classified — can't risk exposure

## Business Model

| Tier | Price | Includes |
|------|-------|---------|
| **Core** (free) | $0 | Standard flight forensics, 17 plugins |
| **Pro** | $500-2K/seat/yr | GPS-denied validation suite, all Pro plugins, compliance reports |
| **Enterprise** | $50-100K/yr | On-premise, custom plugins, training, support SLA |
| **Consulting** | $200-400/hr | Test protocol design, custom validator development |
| **Training** | $5-10K/class | 2-day validation methodology workshop |

## Competitive Advantage

No one else offers this:
1. **Evidence integrity** — SHA-256 hashing, audit trails, chain of custody
2. **Hypothesis engine** — auto-generated root cause when nav fails
3. **Open plugin architecture** — labs can write custom validators
4. **Multi-format support** — PX4, ArduPilot, MAVLink, CSV
5. **Forensic rigor** — designed for court/contract/compliance from day 1
6. **Local-first** — no data leaves the lab

Current alternatives:
- Custom MATLAB scripts (no standardization, no evidence chain)
- Flight Review (basic visualization only)
- BBA FlightHub (hobby-level, no validation features)
- Nothing purpose-built for GPS-denied nav validation

## Implementation Roadmap

### Phase 1: Ground Truth Pipeline (4 weeks)
- Ground truth file ingest (CSV, RINEX)
- Time alignment engine
- Truth + nav solution dataset builder
- Basic accuracy metrics (CEP, RMS)

### Phase 2: Core Validation Plugins (6 weeks)
- nav_accuracy_validator
- trajectory_comparator
- drift_rate_analyzer
- gps_denial_analyzer

### Phase 3: Advanced Analysis (4 weeks)
- sensor_fusion_validator
- nav_latency_analyzer
- multi_run_comparator
- environmental_classifier

### Phase 4: Reporting & UI (4 weeks)
- Compliance report templates
- Validation dashboard UI
- Trajectory overlay visualization
- Test protocol management

### Phase 5: Go-to-Market (ongoing)
- Documentation + tutorials
- Demo with SITL + simulated GPS denial
- Outreach to GPS-denied nav companies
- Conference presence (AUVSI, AAAI, mil events)

---

*This document defines the strategic direction for Goose Pro. The GPS-denied navigation validation suite is the primary revenue driver for the Pro tier, targeting mil integrators and nav system developers who need forensic-grade validation tools.*
