```
   _____
  / ___ \
 / /   \ \   GOOSE
| |     | |  Flight Forensic Platform
| |     | |
 \ \___/ /   Case-oriented. Evidence-preserving. GUI-first.
  \_____/
```

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/Goose-Flight/Goose-Core/actions/workflows/ci.yml/badge.svg)](https://github.com/Goose-Flight/Goose-Core/actions)

---

Goose is an open-source flight forensic platform for UAV/drone flight log investigation. It provides case-oriented, evidence-preserving analysis with a local web GUI as the primary interface. Every piece of evidence is hashed, every analysis run is audited, and every conclusion is traceable.

**This is not a log viewer.** Goose is a forensic investigation tool built around immutable evidence handling, structured diagnostic output, and auditable case management.

---

## Key Capabilities

**Forensic case system** -- Create cases, ingest evidence with SHA-256/SHA-512 hashing, maintain chain of custody with append-only audit logs. Case directory structure preserves evidence integrity from ingest through analysis.

**Parser framework with diagnostics** -- `ParseResult` contract returns `(Flight, ParseDiagnostics, Provenance)` for every parse operation. Diagnostics include format confidence, parse confidence, stream coverage across 20 telemetry streams, corruption indicators, and timebase anomaly detection. The parser never raises -- it always returns structured output.

**11 analysis plugins** -- crash_detection, battery_sag, gps_health, vibration, motor_saturation, attitude_tracking, ekf_consistency, rc_signal, position_tracking, failsafe_events, and log_health. Each plugin emits findings with severity levels and confidence scores.

**Web GUI** -- Case list, case creation, evidence upload, findings view, audit trail view, parse diagnostics tab, telemetry charts (uPlot), and SVG flight path visualization. The GUI is the primary product surface.

**CLI** -- Full command-line interface for analysis, case management, and server operation.

**CI/CD** -- GitHub Actions pipeline: ruff, mypy, pytest (Python 3.10/3.11/3.12 matrix), bandit, pip-audit.

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

---

## Supported Formats

| Format | Status |
|--------|--------|
| PX4 ULog (`.ulg`) | **Supported** |
| ArduPilot DataFlash (`.bin`, `.log`) | Not yet implemented (stub only) |
| MAVLink telemetry (`.tlog`) | Not yet implemented (stub only) |
| Generic CSV (`.csv`) | Not yet implemented (stub only) |

Goose currently parses **PX4 ULog files only**. Stub parsers exist for DataFlash, TLog, and CSV, but they are marked `implemented=False` and return honest unsupported-format errors. See [docs/supported-formats.md](docs/supported-formats.md) for details on what the ULog parser extracts.

---

## Case System

Goose organizes analysis around forensic cases:

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
      findings.json            # Plugin findings
    audit/
      audit_log.jsonl          # Append-only audit trail
    exports/
```

Evidence files are set read-only immediately after ingest. The audit log is append-only and never truncated. Case metadata is the only mutable file.

---

## Web GUI

```bash
goose serve
```

The web GUI at `http://localhost:8000` provides:

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

The API supports both the case-oriented workflow and a backward-compatible analysis endpoint:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cases` | GET | List all cases |
| `/api/cases` | POST | Create a new case |
| `/api/cases/{id}/evidence` | POST | Ingest evidence into a case |
| `/api/cases/{id}/analyze` | POST | Run analysis on case evidence |
| `/api/analyze` | POST | Legacy single-file analysis (compatibility shim) |
| `/api/health` | GET | Health check |
| `/api/plugins` | GET | List installed plugins |

See [docs/api-reference.md](docs/api-reference.md) for full API documentation.

---

## Plugins

Goose ships with 11 analysis plugins:

| Plugin | What It Checks |
|--------|---------------|
| `crash_detection` | Crash events, type (hard/soft), timestamp |
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

Plugins are discoverable via Python entry points. See [docs/writing-plugins.md](docs/writing-plugins.md) for the plugin development guide.

---

## Architecture

```
Log File (.ulg)
     |
     v
  [ Parser Framework ]
     |
     v
 [ ParseResult: Flight + ParseDiagnostics + Provenance ]
     |
     v
 [ Plugin Engine ]
  |    |    |    |    ... (11 plugins)
  v    v    v    v
 [ Findings with severity + confidence ]
     |
     v
 [ Case Storage ]  -->  [ Audit Log ]
  |            |
  v            v
[ Web GUI ]  [ CLI Report ]
```

The forensic subsystem (`src/goose/forensics/`) manages cases, evidence, manifests, and audit trails. Parsers return structured `ParseResult` tuples. Plugins operate on the canonical `Flight` object, not raw log data.

See [docs/architecture/](docs/architecture/) for the full architecture audit, target architecture, and migration plan.

---

## Development Status

Goose is under active development following a sprint-based plan.

| Sprint | Scope | Status |
|--------|-------|--------|
| Sprint 0 | CI/CD, governance, architecture audit | Complete |
| Sprint 1 | Forensic case system, evidence ingest, audit trail | Complete |
| Sprint 2 | Case-oriented API + GUI | Complete |
| Sprint 3 | Parser framework, ParseDiagnostics, Provenance | Complete |
| Sprint 4 | ForensicFinding, EvidenceReference, Hypothesis models | In progress |
| Sprint 5+ | Plugin trust, correlation engine, replay bundles | Planned |

**389 tests passing** across the full suite.

### Not yet built
- DataFlash, TLog, CSV parsers (stubs only)
- Replayable case bundles
- Plugin trust model / signing
- HTML/PDF report export
- Connected portal / fleet features

---

## Contributing

Contributions are welcome -- bug reports, new plugins, parser implementations, and documentation improvements.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing requirements, and the PR process.

---

## License

Apache 2.0. See [LICENSE](LICENSE).
