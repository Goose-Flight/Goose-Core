```
   _____
  / ___ \
 / /   \ \   GOOSE
| |     | |  Flight Forensic & Investigation Platform
| |     | |
 \ \___/ /   Local-first. Evidence-preserving. Profile-aware.
  \_____/
```

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/Goose-Flight/Goose-Core/actions/workflows/ci.yml/badge.svg)](https://github.com/Goose-Flight/Goose-Core/actions)

---

**Goose is an open-source, local-first flight forensic and investigation platform for UAV logs.** It parses PX4, ArduPilot, and CSV flight logs, runs 17 deterministic analysis plugins, scores crash confidence with an XGBoost ML model trained on 8,668 real-world flights, and presents results through 27+ interactive telemetry charts — all without sending a single byte off your machine.

### Why Goose instead of PX4 Flight Review?

| | PX4 Flight Review | Goose |
|---|---|---|
| **Crash analysis** | Manual visual inspection | Automated crash detection with root-cause classification and confidence scoring |
| **ML scoring** | None | XGBoost model (AUC 1.000) trained on 8,668 real flights with 190 features |
| **Analyzers** | None — chart viewer only | 17 built-in forensic plugins with evidence-linked findings |
| **Evidence integrity** | Upload to cloud server | SHA-256/512 hashing, immutable evidence, append-only audit log |
| **Provenance** | None | Every finding traces to parser version, plugin version, trust state, and evidence reference |
| **Privacy** | Logs uploaded to remote server | 100% local — nothing leaves your machine |
| **Charting** | Basic timeseries | 27+ uPlot interactive charts with synchronized zoom/pan + forensic canvas overlays |
| **Case management** | None | Full investigation cases with chain of custody and replay/export |

---

## Quick Start

```bash
# Install
pip install goose-flight

# Verify installation
goose doctor

# Launch the web GUI (primary interface)
goose serve

# Or use the CLI directly
goose crash flight.ulg
goose analyze flight.ulg
```

The web GUI runs at `http://localhost:8000`. A session token is generated at startup for API security — the browser receives it automatically, no login required. No data leaves your machine.

---

## Key Capabilities

**Crash confidence scoring** — Multi-signal probabilistic crash detection using altitude drop rate, G-force signatures, attitude divergence, and motor cutoff patterns. Each crash is classified (motor failure, power loss, GPS loss, impact, mechanical, pilot error) with a confidence score.

**ML-powered analysis** — XGBoost gradient-boosted classifier trained on 8,668 real-world PX4 flights with 190 extracted features. Cross-validated AUC of 1.000. Top predictors: maximum roll angle (40% importance), peak G-force, IMU accelerometer clipping. See [research findings](https://goose.ing/research).

**17 built-in analyzers** — Deterministic forensic plugins covering crash detection, vibration, battery health, GPS, EKF consistency, motor saturation, attitude/position tracking, RC signal, failsafe events, log integrity, payload changes, mission phase anomalies, operator actions, environment conditions, damage classification, and telemetry link health.

**Forensic case system** — Create investigation cases with SHA-256/SHA-512 evidence hashing, immutable evidence storage, chain of custody, append-only audit logs, and run-scoped artifact archives. Quick Analysis mode provides session-only triage without creating a case.

**27+ interactive telemetry charts** — uPlot-based time-series visualization covering altitude, attitude, attitude setpoint, attitude rate, rate setpoint, velocity, velocity setpoint, motors, battery, GPS, vibration, RC signal, EKF, CPU load, attitude tracking error, rate tracking error, velocity tracking error, control-response correlation, stick inputs, actuator demands, magnetometer, airspeed, wind estimate, RC channels, barometer, raw gyro, and raw accelerometer.

**Parser framework with diagnostics** — `ParseResult` returns `(Flight, ParseDiagnostics, Provenance)` for every parse. Diagnostics include format confidence, parse confidence, stream coverage, corruption indicators, and timebase anomaly detection. The parser never raises — it always returns structured output.

**Provenance and trust model** — Every plugin declares a `PluginManifest` with trust state (`builtin_trusted`, `local_signed`, `community`). Every finding includes evidence references linking it to specific time ranges and streams. Parser confidence, finding confidence, and hypothesis confidence are explicitly scoped and never conflated.

**User profiles** — Seven data-driven profiles (Racer, Research, Shop/Repair, Factory/QA, Gov/Mil, Advanced, Default) tailor plugin emphasis, chart ordering, report wording, and metadata fields. Profiles never change forensic truth — the same canonical model is produced regardless of profile.

**Session token auth** — API is protected by a per-session bearer token generated at startup. The token is injected into the SPA automatically. No login UI needed, but local processes cannot call the API without the token.

**Export and replay** — Cases export as replayable bundles containing all findings, hypotheses, diagnostics, and plugin versions. Replay verification detects engine version drift between export and reimport.

---

## Supported Formats

| Format | Status |
|--------|--------|
| PX4 ULog (`.ulg`) | **Supported** — full telemetry extraction across 20+ streams |
| ArduPilot DataFlash (`.bin`, `.log`) | **Supported** — basic message extraction |
| MAVLink telemetry (`.tlog`) | Core stub — full parser in Goose Pro |
| Generic CSV (`.csv`) | **Supported** — stream heuristics |

See [docs/supported-formats.md](docs/supported-formats.md) for format-specific extraction details.

---

## Plugins

Goose ships with 17 built-in analyzers. Each plugin declares a formal `PluginManifest` with required streams, trust state, and output finding types.

| Plugin | What It Checks |
|--------|---------------|
| `crash_detection` | Crash events with classification (motor failure, power loss, impact, GPS loss, pilot error, mechanical) and confidence scoring |
| `vibration` | IMU vibration RMS/peak per axis, accelerometer clipping, bearing degradation trends |
| `battery_sag` | Voltage sag under load, cell voltage thresholds, brownout risk, temperature monitoring |
| `gps_health` | Fix quality, satellite count, HDOP, position drift, dropout detection, jamming indicators |
| `motor_saturation` | Motor output saturation, asymmetry between axes, failure signatures, remaining headroom |
| `ekf_consistency` | EKF innovation ratios, magnetometer consistency, reset detection, estimator fault flags |
| `rc_signal` | RSSI monitoring, signal dropout detection, stuck channel detection, RC failsafe tracking |
| `attitude_tracking` | Roll/pitch/yaw tracking error vs setpoint, PID oscillation detection |
| `position_tracking` | Horizontal position error (Haversine), vertical altitude error, hover drift detection |
| `failsafe_events` | Failsafe trigger cataloging, emergency mode transitions, failsafe vs pilot-initiated classification |
| `log_health` | Log integrity, data gaps, sensor dropout, data rate validation |
| `payload_change_detection` | Candidate mid-flight payload/mass-change events |
| `mission_phase_anomaly` | Anomalous behavior within mission phases (takeoff, cruise, landing) |
| `operator_action_sequence` | Operator input patterns — mode switches, arm/disarm, RC commands |
| `environment_conditions` | Environmental inference — wind estimation, GPS multipath indicators |
| `damage_impact_classification` | Post-impact damage signature classification |
| `link_telemetry_health` | Telemetry link quality, dropout events, RSSI degradation |

Plugins are discoverable via Python entry points. See [docs/writing-plugins.md](docs/writing-plugins.md) for the plugin development guide.

---

## ML Research

Goose includes an ML pipeline trained on 8,668 community-submitted PX4 flights from the public flight.review database:

- **190 features** extracted per flight (attitude, vibration, power, control loop, GPS, EKF, failsafe, timing)
- **XGBoost classifier** with 5-fold stratified cross-validation
- **AUC 1.000** — perfect class separation on the training dataset
- **Top predictor**: maximum roll angle captures ~40% of model importance
- **Key finding**: autonomous mission mode crashes 62% more often than manual flight (42.9% vs 26.5%)
- **30.7% overall crash rate** across the community fleet

Full methodology and results: [goose.ing/research](https://goose.ing/research)

---

## Profiles

| Profile | For | Emphasizes |
|---------|-----|------------|
| **Racer** | FPV racers, performance tuners | Vibration, motor saturation, attitude tracking |
| **Research / University** | Academic and research labs | Log health, GPS, EKF consistency, estimator quality |
| **Shop / Repair** | Drone repair shops and triage | Crash detection, battery sag, motor, log health |
| **Factory / QA** | Manufacturing QA and acceptance | Log health, vibration, motors, attitude tracking |
| **Gov / Mil** | Public safety and mission operators | Crash, GPS, failsafes, EKF, full case metadata |
| **Advanced** | Power users | No defaults — full control |
| **Default** | General use | Balanced defaults |

Profiles bias which plugins are emphasized, which charts appear first, and which wording reports use. The underlying forensic artifact is identical across all profiles.

---

## Web GUI

```bash
goose serve
```

The web GUI at `http://localhost:8000` provides:

- Welcome screen with Quick Analysis / Investigation Case / Open Recent Case
- Profile selector (7 profiles)
- Case list, case creation, evidence upload with integrity verification
- Findings view with severity, confidence, and evidence references
- Parse diagnostics tab (stream coverage, confidence scores, warnings)
- Hypothesis view with supporting/contradicting finding links
- 27+ interactive uPlot telemetry charts with synchronized zoom/pan
- SVG flight path visualization
- Audit trail viewer
- Export and replay verification

---

## CLI Reference

```bash
goose crash flight.ulg              # Crash diagnosis with root cause
goose analyze flight.ulg            # Full plugin analysis
goose serve                         # Launch web GUI
goose doctor                        # Verify installation
goose plugins list                  # List installed plugins
goose analyze flight.ulg --plugin vibration   # Run specific plugin
goose analyze flight.ulg --format json        # JSON output
```

See [docs/cli-reference.md](docs/cli-reference.md) for full documentation.

---

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/quick-analysis` | POST | Session-only triage (no case persisted) |
| `/api/cases` | GET/POST | List or create cases |
| `/api/cases/{id}/evidence` | POST | Ingest evidence into a case |
| `/api/cases/{id}/analyze` | POST | Run analysis on case evidence |
| `/api/profiles` | GET | List available user profiles |
| `/api/plugins` | GET | List installed plugins |
| `/api/cases/{id}/exports/bundle` | POST | Create a replayable export bundle |
| `/api/cases/{id}/diff` | POST | Structured diff between two analysis runs |
| `/api/cases/{id}/exports/reports/*` | GET | Mission summary, forensic case, and crash reports |
| `/api/runs/recent` | GET | Recent analysis runs across all cases |
| `/api/health` | GET | Health check |

All `/api/*` endpoints require a `Bearer` token (generated at startup). See [docs/api-reference.md](docs/api-reference.md) for full API documentation.

---

## Architecture

```
Log File (.ulg / .bin / .log / .csv)
     |
     v
  [ Parser Framework ]
     |
     v
 [ ParseResult: Flight + ParseDiagnostics + Provenance ]
     |
     v
 [ Plugin Engine ]  <-- Tuning Profile (thresholds)
  |    |    |    |    ... (17 analyzers)
  v    v    v    v
 [ ForensicFinding + EvidenceReference + PluginDiagnostics ]
     |
     v
 [ Hypothesis evaluation ]
     |
     +--> [ Quick Analysis session ]   (in-memory only)
     |
     +--> [ Investigation Case ]  -->  [ Audit Log ]
              |
              v
        [ Web GUI / CLI / Report export ]
```

Built on FastAPI + uvicorn with a vanilla JS frontend using uPlot for charting. The forensic subsystem (`src/goose/forensics/`) manages cases, evidence, manifests, canonical models, tuning profiles, and audit trails. Parsers return structured `ParseResult` tuples. Plugins operate on the canonical `Flight` object, not raw log data.

See [docs/architecture/](docs/architecture/) for the full architecture documentation.

---

## Hosted Version

A hosted version with team collaboration features is in development at [goose.ing](https://goose.ing). The marketing site and research findings live in the [Goose-Nest](https://github.com/Goose-Flight/Goose-Nest) repository.

---

## Product Tiers

| Tier | Status | Scope |
|------|--------|-------|
| **OSS Core** | Available now | Local-first, free. Full case system, all 17 analyzers, Quick Analysis, profiles, GUI and CLI. |
| **Local Pro** | Coming | Advanced local workflows — MAVLink TLog parsing, extended reporting. |
| **Hosted / Team** | Planned | Shared cases, org-level audit, team collaboration. |

The open-source core is never crippled. Feature gating lives behind a scaffold (`goose.features.FeatureGate`) and no billing or remote-call logic exists in the core build.

---

## Contributing

Contributions are welcome — bug reports, new plugins, parser implementations, and documentation improvements.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing requirements, and the PR process.

---

## License

Apache 2.0. See [LICENSE](LICENSE).
