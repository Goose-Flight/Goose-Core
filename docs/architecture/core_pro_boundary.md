# Core / Pro Boundary Classification

This document classifies every major Goose subsystem into one of five tiers:

- **PERMANENT CORE** — always free and open-source; never gated or extracted
- **CORE WITH EXTENSION HOOK** — Core-owned, but Pro packages can extend via explicit seams
- **PRO CANDIDATE** — specialist feature; likely gated in a future Local Pro release
- **PRO LIKELY** — strong Pro signal; premium forensic capability or narrow specialist audience
- **HOSTED/TEAM LATER** — cloud/org feature; deferred until Hosted Team tier

Rule: Core must never import Pro. The boundary is enforced by code structure, not convention.

---

## Forensic / Model Layers

| Subsystem | Classification | Notes |
|-----------|---------------|-------|
| Case model (`forensics/models.py`) | PERMANENT CORE | Chain of custody, evidence items, audit log |
| Evidence model (`forensics/models.py`) | PERMANENT CORE | SHA-256/512 hashing, provenance, stored path |
| Audit trail (`forensics/models.py`) | PERMANENT CORE | Append-only; forensic integrity requirement |
| Canonical finding / ForensicFinding | PERMANENT CORE | Core output format; Pro plugins emit into this same model |
| Hypothesis model | PERMANENT CORE | Rule-based generation; same model for all tiers |
| Timeline model | PERMANENT CORE | TimelineEvent stream; persisted per run |
| Report object models (`forensics/reports.py`) | PERMANENT CORE | All nine report families defined in Core |
| Replay / diff model (`forensics/replay.py`, `diff.py`) | PERMANENT CORE | Deterministic replay is a forensic requirement |
| Tuning / profile system (architecture) | PERMANENT CORE | Profile definitions ship in Core |
| Tuning profile presets (Pro-specific) | PRO CANDIDATE | Per-airframe or OEM-specific threshold presets |
| Trust / policy model (`plugins/trust.py`) | CORE WITH EXTENSION HOOK | TrustPolicy is Core; enterprise key stores are Pro |
| Capability / feature system (`features.py`) | CORE WITH EXTENSION HOOK | Scaffold is Core; `register_capability()` lets Pro extend |

---

## Runtime Layers

| Subsystem | Classification | Notes |
|-----------|---------------|-------|
| Parser contract (`parsers/base.py`, `diagnostics.py`) | PERMANENT CORE | ParseResult / ParseDiagnostics contract is non-negotiable |
| Parser registry (`parsers/detect.py: _ALL_PARSERS`) | PERMANENT CORE | Core list; `register_parser()` is the Pro extension hook |
| Plugin contract (`plugins/contract.py`) | PERMANENT CORE | PluginManifest, PluginDiagnostics, AnalyzerPlugin |
| PLUGIN_REGISTRY (`plugins/__init__.py`) | PERMANENT CORE | Core built-in dict; never modified by Pro at runtime |
| `get_all_plugins()` (`plugins/__init__.py`) | CORE WITH EXTENSION HOOK | Merges Core + Pro; the one place Core+Pro combine |
| `discover_pro_plugins()` (`plugins/registry.py`) | CORE WITH EXTENSION HOOK | Entry-point scanner; Pro seam |
| Analysis orchestration (`web/routes/analysis.py`) | PERMANENT CORE | Forensic engine is always Core |
| Timeline / hypothesis / report generation | PERMANENT CORE | All generators are Core; Pro adds report formats via registry |
| Export generation | CORE WITH EXTENSION HOOK | JSON/ZIP exports are Core; Pro registers premium formats |
| Report format registry (`forensics/report_registry.py`) | CORE WITH EXTENSION HOOK | Core registers its generators; Pro extends with premium formats |

---

## Parser Inventory

| Parser | Classification | Rationale |
|--------|---------------|-----------|
| ULog (PX4 `.ulg`) | PERMANENT CORE | Primary supported format; baseline forensic capability |
| CSV | PERMANENT CORE | Universal fallback; needed for community-shared data |
| DataFlash (ArduPilot `.bin`/`.log`) | PRO CANDIDATE | ArduPilot is a distinct ecosystem; separate parser pack is natural |
| TLog (MAVLink `.tlog`) | PRO CANDIDATE | Telemetry logs carry operator/GCS context; niche audience |

DataFlash and TLog parsers currently exist as stubs in Core.  Their stub presence
allows format detection to identify the format and return a structured
"not supported" message.  Actual parse implementation can be moved to a Pro parser
pack without breaking Core's format-detection layer.

---

## Analyzer / Plugin Inventory

### PERMANENT CORE — Baseline Forensic Capability

These 11 analyzers cover the fundamental safety and forensic checklist that any
drone investigation requires.  Gating them would cripple the open-source product.

| Plugin ID | Rationale |
|-----------|-----------|
| `crash_detection` | Primary forensic signal; must be free |
| `vibration` | Baseline IMU health; near-universal diagnostic |
| `battery_sag` | Power system failure is the most common crash cause |
| `gps_health` | Navigation health; essential for any outdoor flight |
| `motor_saturation` | Control authority loss; core crash signal |
| `ekf_consistency` | State estimator health; PX4 fundamental |
| `rc_signal` | RC link is a safety-critical layer |
| `attitude_tracking` | Control quality; fundamental diagnostic |
| `position_tracking` | Navigation accuracy; fundamental diagnostic |
| `failsafe_events` | Safety system audit; must be free |
| `log_health` | Evidence integrity check; required for forensic validity |

### PRO CANDIDATE — Specialist Detection

These 5 analyzers provide deeper or more specialist analysis.  They are natural
Local Pro features: useful for professional operators and investigators but not
required for basic forensic triage.

| Plugin ID | Classification | Rationale |
|-----------|---------------|-----------|
| `payload_change_detection` | PRO CANDIDATE | Specialist; relevant only to payload-equipped platforms |
| `mission_phase_anomaly` | PRO CANDIDATE | Requires structured mission data; advanced phase intelligence |
| `operator_action_sequence` | PRO CANDIDATE | Operator behavior analysis; useful for training/investigation |
| `environment_conditions` | PRO CANDIDATE | Environmental inference; adds analytical depth, not baseline safety |
| `link_telemetry_health` | PRO CANDIDATE | Link quality analysis; overlaps with rc_signal (Core) at basic level |

### PRO LIKELY — Premium Crash Forensics

| Plugin ID | Classification | Rationale |
|-----------|---------------|-----------|
| `damage_impact_classification` | PRO LIKELY | Premium crash forensics; detailed impact damage taxonomy |

---

## Extension Seams Summary

Three explicit extension hooks exist in Core for Pro integration:

1. **Plugin seam** — `discover_pro_plugins()` + `get_all_plugins()` in `plugins/`
   Pro installs entry_points under `goose.plugins`; Core merges them into the
   analysis run automatically.

2. **Parser seam** — `register_parser()` in `parsers/detect.py`
   Pro parser packs call this at import time to add parsers to the detection order.

3. **Report seam** — `report_registry.py` in `forensics/`
   Core registers its report generators; Pro extends with additional formats.

4. **Feature/capability seam** — `register_capability()` in `features.py`
   Pro packages declare their feature names and required entitlement levels.

---

## Boundary Rule

> Core must never import Pro.

Pro packages may import Core freely.  The boundary is enforced by:
- `PLUGIN_REGISTRY` never being modified by Pro at runtime
- `discover_pro_plugins()` being the only Core code that touches entry_points
- No Pro package names appearing anywhere in the Core source tree

Last updated: Sprint 3 (2026-04-09)
