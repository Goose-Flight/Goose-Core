# Goose Pro — Architecture Plan

**Status:** Planning  
**Last updated:** 2026-04-09  
**Author:** Goose Flight / Paperclip

---

## Proposed `goose-pro` Repo Structure

```
goose_pro/
  plugins/         # Premium analyzers (Phase 2 payload, mission-scoring, fleet norms)
  parsers/         # Premium parser packs (DataFlash, TLog/MAVLink)
  reports/         # Premium report formats (HTML/PDF, regulatory export)
  exports/         # Premium export packs (CSV bundles, XLSX, KML track exports)
  workflows/       # Advanced local workflow tools (batch multi-run, watchfolder)
  capabilities/    # Pro capability registrations (entry_point declarations)
  integration/     # Core seam connections (plugin entry_points, parser seam hookup)
  tests/           # Pro-specific tests
```

`goose-pro` is a **separate installable package** (`pip install goose-pro`) that
registers itself into Core's extension seams via `entry_points`. It never modifies
Core source files. It never carries billing, auth, or hosted-team logic — those are
the hosted product's concern, not a local package's.

---

## Classification of Each Major Area

Classification key:
- **PRO NOW** — Ready to build in `goose-pro` immediately; seam exists, Core won't break.
- **NEEDS SEAM** — Cannot move until Core ships the relevant extension point.
- **KEEP IN CORE** — Permanently belongs in open-source Core (forensic truth path, not features).
- **KEEP IN CORE FOR NOW** — In Core today; may qualify for Pro once a seam exists.
- **HOSTED/TEAM ONLY** — Never local; belongs to the hosted product tier.

---

### Parsers

| Component | Classification | Reasoning |
|-----------|---------------|-----------|
| **ULog parser** | **KEEP IN CORE** | PX4 is the primary supported platform; removing it would break Core. Core's forensic truth path depends on it. |
| **CSV parser** | **KEEP IN CORE** | Generic, broadly useful, needed for test fixtures and validation harness. |
| **DataFlash parser** (.log/.bin) | **PRO NOW** | Fully implemented, ArduPilot-ecosystem specialist. The parser extension seam (entry_points `goose.parsers`) exists and the `can_parse()` contract is clean. Move to `goose_pro/parsers/dataflash.py` and register via `goose.parsers` entry_point. Core retains the `BaseParser` contract and detect.py seam. |
| **TLog parser** (.tlog) | **PRO NOW** | Currently a stub (`implemented = False`). MAVLink telemetry parsing is ArduPilot/MAVLink ecosystem specialist work. A minimal honest implementation (binary framing, HEARTBEAT/ATTITUDE/GPS extraction) belongs in Pro, not Core. The seam is ready. |

---

### Plugins

All 11 Core plugins use the `goose.plugins` entry_point seam (`pyproject.toml`
`[project.entry-points."goose.plugins"]`). The seam is production-ready.

| Plugin | Classification | Reasoning |
|--------|---------------|-----------|
| `crash_detection` | **KEEP IN CORE** | Primary forensic truth anchor. Every investigation starts here. Removing it would gut Core's usefulness. |
| `battery_sag` | **KEEP IN CORE** | Essential baseline. Battery failure is the #1 crash cause class; Core needs it for credibility. |
| `vibration` | **KEEP IN CORE** | Motor/propeller health is always relevant; broad applicability across all platforms and users. |
| `gps_health` | **KEEP IN CORE** | GPS health is fundamental to all outdoor operations; belongs in the free tier. |
| `motor_saturation` | **KEEP IN CORE** | Directly implicated in crashes; essential diagnostic for any frame type. |
| `ekf_consistency` | **KEEP IN CORE** | EKF state is the backbone of PX4/ArduPilot navigation; removing this would blind Core. |
| `rc_signal` | **KEEP IN CORE** | RC loss is a top-3 crash scenario; must remain in the free forensic path. |
| `attitude_tracking` | **KEEP IN CORE** | Attitude divergence is the canonical crash signature; Core must be able to detect it. |
| `position_tracking` | **KEEP IN CORE** | Core location analysis, needed for basic flight reconstruction. |
| `failsafe_events` | **KEEP IN CORE** | Failsafe event detection is a free-tier must; every crash investigation checks failsafes. |
| `log_health` | **KEEP IN CORE** | Meta-quality check on the log itself; needed before any other analysis runs. |
| `payload_change_detection` | **PRO NOW** | Specialist: contraband, delivery, tactical payload events. Phase 1 candidate detector already complete. Narrow use case outside general forensics. |
| `mission_phase_anomaly` | **PRO NOW** | Adds phase-level context to findings. Valuable for operators, shops, and enterprise. Not a crash-cause detector itself; enhances existing findings. |
| `operator_action_sequence` | **PRO NOW** | Sensitive analysis (attributing actions to an operator). Appropriate as a Pro feature with clear investigator-review framing. Already conservative in design. |
| `environment_conditions` | **PRO NOW** | Weather/RF environment correlation — useful but not core forensics. Shops and ops teams value it; free-tier users get the basics from gps_health and vibration. |
| `damage_impact_classification` | **PRO NOW** | Distinguishing pre-impact cause from post-impact artifact is a deep forensic capability. Requires expertise to interpret correctly; best surfaced to Pro investigators. |
| `link_telemetry_health` | **KEEP IN CORE FOR NOW** | RC loss detection overlaps with `rc_signal`. Once the distinction is clean (link quality vs. signal presence), the quality analysis can move Pro. For now, keep in Core to avoid forensic gap. |

---

### Reports and Exports

| Component | Classification | Reasoning |
|-----------|---------------|-----------|
| JSON report (`json_report.py`) | **KEEP IN CORE** | Machine-readable canonical output; free-tier essential. |
| HTML report (not yet built) | **PRO NOW** | Human-facing rich report. Build in `goose_pro/reports/html_report.py`. |
| PDF report (not yet built) | **PRO NOW** | Regulatory/insurance/legal export. High value, justifies Pro tier. |
| KML/GPX track export (not yet built) | **PRO NOW** | Geographic visualization of flight path; specialist use case. |
| XLSX/CSV bundle export (not yet built) | **PRO NOW** | Fleet operations analytics export. |
| Regulatory export templates (not yet built) | **HOSTED/TEAM ONLY** | Requires jurisdiction-specific customization; better as a hosted service feature. |

---

### Workflow Tools

| Component | Classification | Reasoning |
|-----------|---------------|-----------|
| Saved templates/presets | **PRO CANDIDATE** | Custom tuning profiles per organization. Needs Core tuning profile seam to be stable first. |
| Batch/multi-run workflows | **PRO CANDIDATE** | Run analysis across a folder of logs; watchfolder daemon. Seam exists (CLI + API), but batch orchestration layer not yet built. |
| Advanced local trust/policy controls | **PRO CANDIDATE** | Plugin signing, verified-bundle enforcement, custom trust registries. Core currently has a basic TrustPolicy; Pro could extend it without modifying Core. |
| Fleet norm computation (not yet built) | **HOSTED/TEAM ONLY** | Requires multi-user data aggregation. Cannot be local-only. |
| Comparative fleet dashboards (not yet built) | **HOSTED/TEAM ONLY** | Team-level analytics; requires backend. |

---

## First Recommended Pro Work (Top 5 Deliverables)

These are the highest-value items that can be built in `goose-pro` **right now**,
given the current seam architecture:

### 1. DataFlash Parser (`goose_pro/parsers/dataflash.py`)
Move the existing fully-implemented DataFlash parser from Core to Pro via the
parser extension seam. Highest signal-to-effort ratio: the code already exists
and the seam is production-ready. ArduPilot users become a Pro acquisition channel.

### 2. Pro Plugin Pack — Phase 2 Analyzers
Bundle the five Pro-classified plugins (`payload_change_detection`,
`mission_phase_anomaly`, `operator_action_sequence`, `environment_conditions`,
`damage_impact_classification`) into `goose_pro/plugins/`. Register them via
`goose.plugins` entry_points. These are already implemented in Core today;
the migration is a packaging task.

### 3. HTML Report Generator (`goose_pro/reports/html_report.py`)
Build on `ForensicCaseReport` from the report registry seam. A well-structured
HTML report is the #1 most-requested feature from professional operators and shops.
Self-contained, no backend needed, immediately shippable.

### 4. TLog Parser — Minimal Honest Implementation (`goose_pro/parsers/tlog.py`)
Implement basic MAVLink binary framing: read message types, extract
HEARTBEAT/ATTITUDE/GPS/BATTERY_STATUS/SYS_STATUS fields. Even partial coverage
opens the MAVLink ecosystem (ArduPilot GCS logs, Mission Planner, QGC). The stub
in Core correctly signals "not implemented" — Pro ships the real parser.

### 5. Batch Workflow Tool (`goose_pro/workflows/batch_analyze.py`)
CLI and API wrapper that runs analysis over a directory of log files and produces
an aggregate summary. Needed by repair shops, QA teams, and fleet operators.
High conversion-from-free signal.

---

## What Stays in Core Permanently

These components are permanently part of the open-source forensic truth path and
must never move to Pro:

- **ULog parser** — PX4 is Core's primary platform.
- **CSV parser** — needed for testing and generic log support.
- **Crash detection plugin** — the anchor of every forensic investigation.
- **Battery sag, vibration, GPS health, motor saturation, EKF consistency, RC signal, attitude tracking, position tracking, failsafe events, log health** — the 11 foundational plugins that constitute a credible free forensic analysis.
- **Flight canonical model** (`core/flight.py`, `forensics/canonical.py`) — the shared type system both Core and Pro depend on.
- **Forensic lifting layer** (`forensics/lifting.py`) — converts findings to forensic artifacts; Pro plugins depend on this.
- **Timeline builder** (`forensics/timeline.py`) — shared structured event model.
- **Plugin and parser contracts** (`plugins/contract.py`, `plugins/base.py`, `parsers/base.py`) — extension seam definitions.
- **Case service** (`forensics/case_service.py`) — case persistence and chain of custody.
- **TuningProfile** (`forensics/tuning.py`) — threshold management.
- **JSON report** (`reports/json_report.py`) — machine-readable canonical output.
- **Trust policy** (`plugins/trust.py`) — safety foundation for plugin execution.
- **Web API** (`web/`) — the local UI; this is how users access Core.

---

## What Stays in Core For Now (But May Move to Pro)

| Component | Reasoning |
|-----------|-----------|
| `link_telemetry_health` plugin | Overlaps with `rc_signal`. Once the split is clean (link quality vs. signal presence), the quality-analysis portion can move Pro. Needs 1 more sprint to untangle. |
| DataFlash parser | Currently in Core. Should move to Pro once `goose-pro` repo is established and the parser extension seam is confirmed stable in production. Do not remove from Core until Pro ships it. |
| Profiles system (`forensics/profiles.py`) | Profile configuration itself stays Core; Pro can add custom profile packs. |
| Replay engine (`forensics/replay.py`) | Core replay stays Core. Pro could add enhanced replay with cross-run regression scoring. |
| Comparison persistence (`forensics/diff.py` + persistence layer) | Core diff engine and persistence stays Core. Pro could add richer diff reporting formats. |

---

## What Stays Hosted/Team-Only

These features require multi-user data or backend infrastructure and must never
be built into a local package:

- Fleet norm computation and population benchmarks
- Multi-user case sharing and collaboration
- Role-based access control (RBAC)
- Hosted compliance reporting with jurisdiction templates
- Crash rate trend analytics across a fleet
- Alert/notification routing (email, Slack, PagerDuty)
- Billing, licensing, and seat management
- SSO / enterprise identity provider integration
- API key management for SaaS integrations

---

## Extension Seam Summary

For `goose-pro` to integrate cleanly, the following seams must remain stable in Core:

| Seam | Mechanism | Status |
|------|-----------|--------|
| Plugin registration | `entry_points["goose.plugins"]` | Production-ready |
| Parser registration | `entry_points["goose.parsers"]` (via `detect.py`) | Ready — parser detection uses `can_parse()` contract |
| Report registry | `entry_points["goose.reports"]` (planned, see `report_registry.py`) | Needs Core seam finalization |
| Tuning profile config | `TuningProfile.get_config_for_plugin()` | Stable |
| ForensicFinding lifting | `forensics/lifting.py` API | Stable |
| PluginManifest contract | `plugins/contract.py` `PluginManifest` | Stable |
| BaseParser contract | `parsers/base.py` `BaseParser` | Stable |
