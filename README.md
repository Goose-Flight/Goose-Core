```
   _____
  / ___ \
 / /   \ \   GOOSE
| |     | |  Flight Forensics & Investigation Platform
| |     | |
 \ \___/ /   Local-first. Evidence-preserving. Profile-aware.
  \_____/
```

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PyPI](https://img.shields.io/badge/pip%20install-goose--flight-blue)](https://pypi.org/project/goose-flight/)
[![CI](https://github.com/Goose-Flight/Goose-Core/actions/workflows/ci.yml/badge.svg)](https://github.com/Goose-Flight/Goose-Core/actions)

---

Goose is an open-source drone flight forensics platform — not just a crash analyzer. It turns ULog, DataFlash, TLog, and CSV flight logs into structured case files with evidence chains, ranked hypotheses, and PDF/JSON exports. The platform pairs a FastAPI backend with a React 19 frontend, ships 16 built-in analysis plugins covering crash detection through environmental inference, and includes a full case management system with chain-of-custody audit trails — all running locally, with nothing leaving your machine. [Goose Pro](https://github.com/Goose-Flight/Goose-Pro) extends it with GPS-denied navigation validation, MIL-STD-810H compliance reporting, fleet management, and RBAC via Core's public seams.

---

## Supported Log Formats

| Format | Notes |
|--------|-------|
| **ULog** (`.ulg`) | PX4 firmware — full telemetry extraction across 20+ streams |
| **DataFlash** (`.bin`, `.log`) | ArduPilot firmware — message-level extraction |
| **TLog** (`.tlog`) | MAVLink telemetry stream — Core stub; full parser in Goose Pro |
| **CSV** (`.csv`) | Generic tabular logs — stream heuristics for column mapping |

---

## 16 Core Plugins

### Crash & Impact

| Plugin | What It Does |
|--------|-------------|
| `crash_detection` | Detects crash events and classifies root cause (motor failure, power loss, GPS loss, impact, mechanical, pilot error) with probabilistic confidence scoring |
| `failsafe_events` | Catalogs every failsafe trigger, emergency mode transition, and classifies failsafe vs pilot-initiated actions |
| `damage_impact_classification` | Classifies post-impact damage signatures from IMU and attitude data |

### Power

| Plugin | What It Does |
|--------|-------------|
| `battery_sag` | Monitors voltage sag under load, per-cell thresholds, brownout risk, and temperature |
| `log_health` | Validates log integrity, stream coverage, sensor dropout, and data-rate continuity |

### Navigation

| Plugin | What It Does |
|--------|-------------|
| `gps_health` | Tracks fix quality, satellite count, HDOP, position drift, dropout events, and jamming indicators |
| `ekf_consistency` | Evaluates EKF innovation ratios, magnetometer consistency, reset events, and estimator fault flags |
| `position_tracking` | Measures horizontal position error (Haversine), vertical altitude error, and hover drift |

### Mechanical

| Plugin | What It Does |
|--------|-------------|
| `vibration` | Computes IMU vibration RMS/peak per axis, accelerometer clipping counts, and bearing degradation trends |
| `motor_saturation` | Detects motor output saturation, cross-axis asymmetry, failure signatures, and headroom |
| `attitude_tracking` | Measures roll/pitch/yaw tracking error vs setpoint and detects PID oscillation |

### Operator & Comms

| Plugin | What It Does |
|--------|-------------|
| `rc_signal` | Monitors RSSI, dropout duration, stuck channels, and RC failsafe triggers |
| `link_telemetry_health` | Assesses telemetry link quality, dropout events, and RSSI degradation trends |
| `operator_action_sequence` | Reconstructs operator input patterns — mode switches, arm/disarm cycles, RC command sequences |

### Environment & Payload

| Plugin | What It Does |
|--------|-------------|
| `environment_conditions` | Infers wind speed, direction, and GPS multipath indicators from flight telemetry |
| `payload_change_detection` | Identifies candidate mid-flight payload or mass-change events from dynamics signatures |
| `mission_phase_anomaly` | Flags anomalous behavior within detected mission phases (takeoff, cruise, landing) |

---

## ML / Forensics Engine

- **Anomaly scoring** — weighted confidence scoring across multiple signal dimensions; each finding carries an explicit confidence value scoped to its evidence window
- **Ranked root cause hypotheses** — a hypothesis engine aggregates plugin findings into ranked causal explanations with supporting and contradicting evidence chains
- **Canonical finding normalization** — all plugins emit `ForensicFinding` objects with `EvidenceReference` links; findings are never raw strings
- **Validation corpus** — ground truth labels and a structured test corpus back the anomaly scoring thresholds
- **Per-vehicle tuning profiles** — seven data-driven profiles (Racer, Research, Shop/Repair, Factory/QA, Gov/Mil, Advanced, Default) adjust plugin emphasis and report wording without touching forensic truth

---

## Installation

```bash
pip install goose-flight

goose --help
goose analyze <file>
```

To verify a fresh install:

```bash
goose doctor
```

---

## Web UI

```bash
goose serve
```

Opens at `http://localhost:8080`. Subsystem pages:

- **Motors** — per-motor output, saturation, asymmetry
- **Battery** — voltage, current, sag events
- **GPS / Nav** — fix quality, HDOP, dropout map
- **Vibration** — IMU RMS/peak, clipping counts
- **Control** — attitude / rate / position tracking error
- **Environment** — wind estimate, multipath indicators
- **Flight Path 3D** — interactive 3D trajectory from GPS + altitude
- **Anomaly Timeline** — all findings across the full flight timeline

Additional views: case management, evidence chain with SHA-256 hashes, hypothesis ranking, and PDF/JSON report export.

---

## Extending Goose

Goose exposes four public seams for adding capabilities without forking Core:

| Seam | How to Use |
|------|-----------|
| `goose.plugins` entry point | Register analysis plugins via `pyproject.toml` entry_points |
| `register_parser()` | Add support for new log formats |
| `register_report_generator()` | Add new report output types (PDF, HTML, JSON, etc.) |
| `register_capability()` | Declare optional capabilities that the UI and CLI can discover |

Goose Pro uses these seams. Core never imports Pro. Any extension that registers through these seams is automatically discovered at startup — no Core edits required.

---

## Goose Pro

Goose Pro is a paid local-install extension that adds GPS-denied navigation validation (CEP/R95/R99 accuracy metrics, NAV-001 through NAV-012 standardized test matrix, 20 dedicated plugins), RINEX 2.x/3.x ground truth ingestion with ECEF-to-WGS-84 conversion, MIL-STD-810H compliance reports, fleet management with per-drone nav system profiles, and role-based access control. See [flygoose.dev/pro](https://flygoose.dev/pro).

---

## Architecture Boundary

> Goose Pro extends Goose Core via Core's public seams. Core never imports Pro. Installing Pro alongside Core is additive — uninstalling returns Core to its open-source behavior with zero residue.

```
Log File (.ulg / .bin / .log / .tlog / .csv)
     |
     v
  [ Parser Framework ]   <-- register_parser() seam
     |
     v
 [ ParseResult: Flight + ParseDiagnostics + Provenance ]
     |
     v
 [ Plugin Engine ]  <-- goose.plugins entry_points
  |    |    |    |    ... (16 Core + N Pro plugins)
  v    v    v    v
 [ ForensicFinding + EvidenceReference ]
     |
     v
 [ Hypothesis Engine ]
     |
     +--> [ Quick Analysis session ]   (in-memory)
     |
     +--> [ Investigation Case ]  -->  [ Audit Log ]
              |
              v
       [ Web UI / CLI ]
              |
              v
       [ Report Generator ]   <-- register_report_generator() seam
```

---

## License

Apache 2.0. See [LICENSE](LICENSE).
