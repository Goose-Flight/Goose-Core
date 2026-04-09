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

Goose is an open-source, **local-first flight forensic and investigation platform for UAV logs**. It is built for the whole workflow from a quick "what happened on this run?" question to a multi-day forensic investigation with evidence custody, structured findings, and auditable reports.

Two entry paths cover the full range:

- **Quick Analysis** — drag a log in, pick a profile, get findings, hypotheses, and a summary. Session-only, nothing persisted. Perfect for a fast triage pass or a one-off question. Promote to a full investigation case with one click.
- **Investigation Cases** — case-oriented workflow with evidence ingest, SHA-256/SHA-512 hashing, chain of custody, append-only audit log, and saved analysis runs. Built for deeper work that you want to keep, share, or revisit.

The same forensic engine — same parsers, same plugins, same canonical models — powers both paths. Profiles only tailor defaults and wording. They never change forensic truth.

---

## Profiles and Roles

Goose ships with data-driven **profiles** that tailor defaults for different operator classes without forking the engine:

| Profile | For | Emphasizes |
|---------|-----|------------|
| **Racer** | FPV racers, performance tuners | Vibration, motor saturation, attitude tracking |
| **Research / University** | Academic and research labs | Log health, GPS, EKF consistency, estimator quality |
| **Shop / Repair** | Drone repair shops and triage | Crash detection, battery sag, motor, log health |
| **Factory / QA** | Manufacturing QA and acceptance | Log health, vibration, motors, attitude tracking |
| **Gov / Mil** | Public safety and mission operators | Crash, GPS, failsafes, EKF, full case metadata |
| **Advanced** | Power users | No defaults — full control |
| **Default** | General use | Balanced defaults |

Profiles bias which plugins are emphasized, which charts appear first, which case metadata fields are prominent, and which wording the reports use ("Run" vs "Case" vs "Sortie" vs "Test"). The underlying forensic artifact is identical across profiles — same parser, same plugins, same canonical models. See `GET /api/profiles`.

> **Note:** Goose is evidence-preserving and structured, with hashed ingest, append-only audit logs, and canonical finding/hypothesis models. It does **not** claim formal military or regulatory compliance certification.

---

## Key Capabilities

**Forensic case system** — Create cases, ingest evidence with SHA-256/SHA-512 hashing, maintain chain of custody with append-only audit logs. Case directory structure preserves evidence integrity from ingest through analysis.

**Quick Analysis** — Session-only triage flow for users who need findings without creating a case. Upload a log, pick a profile, get findings + hypotheses + summary. Promote to a full Investigation Case with one click. See `POST /api/quick-analysis`.

**Parser framework with diagnostics** — `ParseResult` contract returns `(Flight, ParseDiagnostics, Provenance)` for every parse operation. Diagnostics include format confidence, parse confidence, stream coverage across 20 telemetry streams, corruption indicators, and timebase anomaly detection. The parser never raises — it always returns structured output.

**17 built-in analyzers** — crash_detection, battery_sag, gps_health, vibration, motor_saturation, attitude_tracking, ekf_consistency, rc_signal, position_tracking, failsafe_events, log_health, payload_change_detection, mission_phase_anomaly, operator_action_sequence, environment_conditions, damage_impact_classification, and link_telemetry_health. Each plugin emits findings with severity, scores, and confidence, and declares a formal `PluginManifest` with required streams, trust state, and output finding types.

**Plugin trust model** — Every plugin declares a `PluginManifest` with a `PluginTrustState` (`builtin_trusted`, `local_signed`, `community`, etc.). Runtime `PluginDiagnostics` report execution status (`RAN` / `SKIPPED` / `BLOCKED`), missing streams, and warnings per run.

**Findings, hypotheses, and canonical models** — Plugins emit `ForensicFinding` objects with evidence references linking each finding back to a specific time range and stream. Hypotheses are a distinct type with their own evaluation state (`candidate` / `supported` / `refuted` / `inconclusive`), so parser confidence, finding confidence, and root-cause certainty never get conflated.

**User profiles** — Data-driven profile configurations (Racer, Research, Shop/Repair, Factory/QA, Gov/Mil, Advanced, Default) bias defaults, plugin selection, chart presets, and report wording without forking the forensic engine.

**Rich case metadata** — Cases carry full operational context (mission/sortie ids, operator and unit, platform and firmware, customer/ticket info, damage and corrective actions) so investigation output is forensically complete for every profile.

**Attachments** — Non-telemetry attachments (photos, videos, GCS logs, notes, report appendices, checklists) are hashed and stored per-case with a manifest.

**Structured timeline** — Typed `TimelineEvent` stream built from parser output (flight phases, mode changes, failsafes) and plugin findings. Persisted per analysis run at `analysis/timeline.json`.

**Replay and export** — Cases can be exported as replayable bundles for sharing, archival, or reproducing a past run with the exact evidence, parser, and tuning profile that produced it.

**Feature gate scaffold** — `goose.features.FeatureGate` provides capability checks for future tiering. The open-source build runs at `OSS_CORE` (free, local-first) with **Local Pro coming** for advanced workflows. No billing logic lives in the core.

**Web GUI** — Welcome screen with the Quick Analysis vs Investigation Case choice, profile selector, case list, case creation, evidence upload, findings view, audit trail view, parse diagnostics tab, telemetry charts (uPlot), and SVG flight path visualization. The GUI is the primary product surface.

**CLI** — Full command-line interface for analysis, case management, and server operation.

**CI/CD** — GitHub Actions pipeline: ruff, mypy, pytest (Python 3.10/3.11/3.12 matrix), bandit, pip-audit.

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

The web GUI runs at `http://localhost:8000`. No data leaves your machine.

On first launch the welcome screen asks you to pick **Quick Analysis** or **Investigation Case** and choose a profile. You can change profiles at any time.

---

## Supported Formats

| Format | Status |
|--------|--------|
| PX4 ULog (`.ulg`) | **Supported** |
| ArduPilot DataFlash (`.bin`, `.log`) | **Supported** (basic message extraction) |
| MAVLink telemetry (`.tlog`) | Core stub only — real parser in Goose Pro |
| Generic CSV (`.csv`) | **Supported** (stream heuristics) |

Goose parses **PX4 ULog, ArduPilot DataFlash, and generic CSV** natively. A stub parser exists for MAVLink TLog in Core; the real TLog parser ships in Goose Pro. See [docs/supported-formats.md](docs/supported-formats.md) for format-specific extraction details.

---

## Case System

Goose organizes investigation work around forensic cases:

```
cases/
  CASE-2026-000001/
    case.json                  # Case metadata, status, run history
    evidence/
      EV-0001-flight.ulg       # Immutable original (SHA-256 + SHA-512 verified)
    manifests/
      evidence_manifest.json   # Hashes, acquisition metadata
    parsed/
      canonical_flight.json    # Parsed Flight object
      parse_diagnostics.json   # Full parse quality report
      provenance.json          # Parser lineage record
    analysis/
      findings.json            # Latest run findings (pointer)
      findings_{run_id}.json   # Run-specific archive (for diff/replay)
      hypotheses.json          # Latest run hypotheses (pointer)
      hypotheses_{run_id}.json # Run-specific archive
      timeline.json            # Typed timeline events
      signal_quality.json      # Per-stream signal quality report
      plugin_diagnostics.json  # Per-plugin execution records
    audit/
      audit_log.jsonl          # Append-only audit trail
    exports/
```

Evidence files are set read-only immediately after ingest. The audit log is append-only and never truncated. Case metadata is the only mutable file.

Quick Analysis runs do not create any of these directories — they run in memory and are discarded when the session ends, unless you promote them to a full case.

---

## Web GUI

```bash
goose serve
```

The web GUI at `http://localhost:8000` provides:

- Welcome screen with Quick Analysis / Investigation Case / Open Recent Case
- Profile selector (Racer, Research, Shop/Repair, Factory/QA, Gov/Mil, Advanced, Default)
- Case list and case creation
- Evidence upload with integrity verification
- Findings view with severity and confidence
- Parse diagnostics tab (stream coverage, confidence scores, warnings)
- Audit trail viewer
- Telemetry charts (altitude, battery, motors, attitude, vibration, GPS, velocity)
- SVG flight path with zoom/pan

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

The API supports the Quick Analysis flow, the full case-oriented workflow, and a backward-compatible analysis endpoint:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/quick-analysis` | POST | Session-only triage (no case persisted) |
| `/api/cases` | GET | List all cases |
| `/api/cases` | POST | Create a new case |
| `/api/cases/{id}/evidence` | POST | Ingest evidence into a case |
| `/api/cases/{id}/analyze` | POST | Run analysis on case evidence |
| `/api/profiles` | GET | List available user profiles |
| `/api/analyze` | POST | Removed — returns 410 Gone with redirect instructions |
| `/api/cases/{id}/exports/bundle` | POST | Create a replayable export bundle |
| `/api/cases/{id}/exports/verify-replay` | POST | Compare bundle versions with current engine |
| `/api/cases/{id}/diff` | POST | Structured diff between two analysis runs |
| `/api/cases/{id}/exports/reports/mission-summary` | GET | Mission summary report |
| `/api/cases/{id}/exports/reports/forensic-case` | GET | Full forensic case report |
| `/api/cases/{id}/exports/reports/crash` | GET | Crash/mishap report |
| `/api/runs/recent` | GET | Recent analysis runs across all cases |
| `/api/health` | GET | Health check |
| `/api/plugins` | GET | List installed plugins |

See [docs/api-reference.md](docs/api-reference.md) for full API documentation.

---

## Plugins

Goose ships with 17 built-in analyzers:

| Plugin | What It Checks |
|--------|---------------|
| `crash_detection` | Crash events, classification (motor failure, power loss, impact, etc.) |
| `vibration` | IMU vibration levels, clipping, resonance |
| `battery_sag` | Voltage sag under load, cell imbalance, brownout risk |
| `gps_health` | Fix quality, satellite count, HDOP, position drift |
| `motor_saturation` | Motor output saturation, asymmetry, control authority loss |
| `ekf_consistency` | EKF innovation consistency and divergence |
| `rc_signal` | RC link quality, signal loss events |
| `attitude_tracking` | Attitude tracking error between setpoint and actual |
| `position_tracking` | Position tracking accuracy |
| `failsafe_events` | Failsafe triggers and flight termination events |
| `log_health` | Log integrity, data gaps, sensor dropout |
| `payload_change_detection` | Candidate mid-flight payload / mass-change events (Phase 1) |
| `mission_phase_anomaly` | Anomalous behavior within mission phases (takeoff, cruise, landing) |
| `operator_action_sequence` | Operator input patterns — mode switches, arm/disarm, RC commands |
| `environment_conditions` | Environmental inference — wind estimation, GPS multipath indicators |
| `damage_impact_classification` | Post-impact damage signature classification |
| `link_telemetry_health` | Telemetry link quality, dropout events, RSSI degradation |

Plugins are discoverable via Python entry points and declare a formal `PluginManifest` (required streams, trust state, output finding types). See [docs/writing-plugins.md](docs/writing-plugins.md) for the plugin development guide.

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

The forensic subsystem (`src/goose/forensics/`) manages cases, evidence, manifests, canonical models, tuning profiles, and audit trails. Parsers return structured `ParseResult` tuples. Plugins operate on the canonical `Flight` object, not raw log data.

See [docs/architecture/](docs/architecture/) for the full architecture audit, target architecture, and migration plan.

---

## Product Tiers

| Tier | Status | Scope |
|------|--------|-------|
| **OSS Core** | Available today | Local-first, free. Full case system, all 17 built-in analyzers, Quick Analysis, profiles, GUI and CLI. |
| **Local Pro** | Coming | Advanced local workflows — reserved for future work. |
| **Hosted / Team** | Planned | Shared cases, org-level audit, team collaboration. |

The open-source core is never crippled. Feature gating lives behind a scaffold (`goose.features.FeatureGate`) and no billing or remote-call logic exists in the core build.

---

## Contributing

Contributions are welcome — bug reports, new plugins, parser implementations, and documentation improvements.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing requirements, and the PR process.

---

## License

Apache 2.0. See [LICENSE](LICENSE).
