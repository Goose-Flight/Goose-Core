---
title: Goose-Core Architecture Audit
version: Sprint 3 (updated)
date: 2026-04-08
status: current
---

# Goose-Core Architecture Audit

This document captures the current state of Goose-Core against the NEW MISSION
spec pack. Originally written as the Sprint 0 baseline, updated after Sprint 3
completion to reflect current state.

---

## 1. Current Architecture Summary

Goose-Core v1.3.4 is a functional flight analysis engine with:

- **ULog parser** (PX4 `.ulg`) — real implementation via pyulog
- **Stub parsers** — DataFlash, TLog, CSV exist in code but are not fully implemented
- **11 analysis plugins** registered via entry points
- **FastAPI web app** — single-page upload → analyze → display flow
- **CLI** — analyze, serve, crash, doctor, plugins commands
- **uPlot charts** — altitude, battery, motors, attitude, vibration, GPS, velocity
- **SVG flight path** with zoom/pan
- **Narrative engine** — dynamic plain-English flight summaries
- **Scoring engine** — weighted per-plugin, missing data excluded
- **Telemetry subsystem** — opt-in, anonymized, consent-gated

### Module map

```
src/goose/
├── core/
│   ├── flight.py          # Flight, FlightMetadata, FlightPhase, ModeChange, FlightEvent
│   ├── finding.py         # Finding dataclass
│   ├── phases.py          # Phase detection logic
│   ├── crash_detector.py  # Simple altitude-drop crash heuristic
│   ├── scoring.py         # Weighted score computation
│   └── narrative.py       # Dynamic narrative generation
├── parsers/
│   ├── base.py            # BaseParser ABC
│   ├── detect.py          # Extension-based format detection
│   ├── ulog.py            # PX4 ULog — REAL
│   ├── dataflash.py       # ArduPilot DataFlash — STUB
│   ├── tlog.py            # MAVLink TLog — STUB
│   └── csv_parser.py      # Generic CSV — STUB
├── plugins/
│   ├── base.py            # Plugin ABC
│   ├── registry.py        # Entry-point discovery
│   └── [11 plugin files]  # crash_detection, vibration, battery_sag,
│                          #   gps_health, motor_saturation, ekf_consistency,
│                          #   rc_signal, attitude_tracking, position_tracking,
│                          #   failsafe_events, log_health
├── web/
│   ├── app.py             # FastAPI app factory — temp-file-first workflow
│   ├── api.py             # Legacy route shim
│   └── static/
│       ├── index.html     # Single-page app (3000+ lines)
│       ├── cockpit.js     # uPlot chart builders
│       └── cockpit.css    # Chart styles
├── reports/
│   ├── json_report.py     # JSON export
│   ├── html_report.py     # Jinja2 HTML report
│   └── pdf_report.py      # WeasyPrint PDF (optional dep)
├── cli/
│   └── [analyze, serve, crash, doctor, plugins commands]
├── telemetry/
│   └── [collector, anonymizer, sender, consent]
└── config/
    └── [settings, defaults]
```

---

## 2. Gap Analysis Against Spec Pack

### 2.1 Case Subsystem — COMPLETE (Sprint 1)

**Required:** Case model, EvidenceItem, EvidenceManifest, case directory service,
case status, analysis run history, export history.

**Current:** Implemented in `src/goose/forensics/`. Case model with evidence
inventory, analysis runs, exports, and audit trail. Case directory structure:
`cases/CASE-YYYY-NNNNNN/{evidence/, manifests/, parsed/, analysis/, audit/, exports/}`.

**Status:** Shipped in Sprint 1.

---

### 2.2 Evidence Subsystem — COMPLETE (Sprint 1)

**Required:** Immutable ingest, SHA-256/SHA-512 hashing, evidence manifest,
provenance tracking, immutable original storage.

**Current:** Immutable evidence ingest with SHA-256 + SHA-512 hashing. Evidence
files set read-only after copy. Evidence manifest (JSON) written per case.
Provenance model tracks full lineage with `contract_version: "1.0"`.

**Status:** Shipped in Sprint 1.

---

### 2.3 Parser Subsystem — COMPLETE (Sprint 3)

**Required:** Parser ID, parser version, ParseDiagnostics, Provenance output,
format confidence, corruption surfacing, missing-stream reporting.

**Current:**
- `ParseResult` contract: `(Flight | None, ParseDiagnostics, Provenance)` --
  `parse()` never raises
- `ParseDiagnostics`: parser identity, format confidence, parse confidence,
  stream coverage (20 streams), warnings, errors, corruption indicators,
  timebase anomalies, assumptions, parse timing
- `diagnostics_version: "1.0"`, `confidence_scope: "parser_parse_quality"`
- `Provenance`: full lineage record with `contract_version: "1.0"`
- ULogParser adapted to return ParseResult with real diagnostics
- Stub parsers (DataFlash, TLog, CSV): `implemented=False`, return honest
  unsupported-format errors
- Detection module: `parse_file()`, `detect_parser()`, `supported_formats()`
- Parse diagnostics tab in GUI case workspace

**Status:** Shipped in Sprint 3.

---

### 2.4 Canonical Data Model — PARTIAL

**Required:** SignalQuality, EvidenceReference, expanded Finding (finding_id,
plugin_version, confidence, evidence_references, contradicting_metrics),
Hypothesis model, Provenance linkage.

**Current `Finding`:**
```python
plugin_name, title, severity, score, description,
evidence: dict, phase, timestamp_start, timestamp_end
```

**Missing from Finding:** `finding_id`, `plugin_version`, `confidence`,
`evidence_references: list[EvidenceReference]`, `contradicting_metrics`,
`assumptions`.

**Missing entirely:** `SignalQuality`, `EvidenceReference`, `Hypothesis`,
`ParseDiagnostics`, `Provenance`, `AuditEntry`.

**Impact:** MEDIUM — current Finding works for display; extension is additive.

---

### 2.5 Analysis Subsystem — PARTIAL

**Required:** Deterministic plugin execution, plugin diagnostics, confidence
calculation, contradiction handling, timeline generation, hypothesis support.

**Current:** Plugins run deterministically. No contradiction handling. No
hypothesis generation. No confidence propagation. Plugin errors are logged but
don't produce structured diagnostics.

**Impact:** MEDIUM — existing execution is fine; needs enrichment.

---

### 2.6 Plugin Subsystem — PARTIAL

**Required:** Plugin manifest (plugin_id, version, author, category, supported
log/vehicle types, required/optional streams, trust metadata), formal output
contract, trust-state model, tuning profiles.

**Current `Plugin` base:**
```python
name, description, version, min_mode
analyze(flight, config) -> list[Finding]
applicable(flight) -> bool
```

**Missing:** `plugin_id`, `category`, `author`, `supported_log_types`,
`required_streams`, `optional_streams`, `config_schema`, output contract with
`plugin_diagnostics` and `confidence_notes`, trust metadata fields.

**Impact:** MEDIUM — the existing base works for analysis; needs extension.
All 11 plugins need manifest data added (non-breaking addition).

---

### 2.7 Replay and Export Subsystem — MISSING

**Required:** Case bundle export, case import/replay, replay verification,
version compatibility handling.

**Current:** `json_report.py` exports findings as JSON. No case bundle concept.
No replay. No version verification.

**Impact:** MEDIUM (Sprint 8 priority per spec).

---

### 2.8 Audit Subsystem — COMPLETE (Sprint 1)

**Required:** Write-once audit log, evidence access traces, parser/analyzer
execution traces, export traces.

**Current:** Append-only audit log (JSONL) per case. AuditEntry model with
event_id, timestamp, actor, action, object references, and error tracking.
Written on case creation, evidence ingest, parse, and analysis events.

**Status:** Shipped in Sprint 1.

---

### 2.9 GUI Workflow — PARTIAL (Sprints 2-3)

**Required:** Case-oriented workflow: create case -> ingest evidence -> parse ->
analyze -> findings -> timeline -> export. Case list, evidence view, parse
diagnostics, plugin inventory, hypothesis view, admin view.

**Current:** Case-oriented GUI with case list, case creation, evidence upload,
findings view, audit trail view, and parse diagnostics tab. Backward-compatible
`/api/analyze` shim preserved. Charts and SVG flight path embedded in case
workspace.

**Still missing:** Hypothesis view (Sprint 4+), plugin trust visibility
(Sprint 5+), full investigation workspace (Sprint 6).

---

### 2.10 CI/CD — COMPLETE (Sprint 0)

GitHub Actions pipeline in place: ruff, mypy, pytest (3.10/3.11/3.12 matrix),
bandit, pip-audit.

**Status:** Shipped in Sprint 0. 389 tests passing.

---

## 3. What Must Be Preserved

These components are working and should be migrated (not replaced):

| Component | Location | Preserve |
|-----------|----------|---------|
| Flight canonical model | `core/flight.py` | Yes — extend, not replace |
| ULog parser | `parsers/ulog.py` | Yes — wrap in new contract |
| 11 analysis plugins | `plugins/` | Yes — convert to new contract |
| uPlot charting | `static/cockpit.js` | Yes — embed in case workspace |
| SVG flight path | `static/index.html` | Yes — preserve in GUI |
| Narrative engine | `core/narrative.py` | Yes — move to report subsystem |
| Scoring engine | `core/scoring.py` | Yes — evolve |
| Telemetry subsystem | `telemetry/` | Yes — preserve |
| Test suite (389 tests) | `tests/` | Yes — extend |

---

## 4. What Conflicts and Must Change (Sprint 0 baseline, updated Sprint 3)

| Sprint 0 Issue | Required Behavior | Status |
|---------------|-------------------|--------|
| Temp-file ingest in `/api/analyze` | Immutable case evidence ingest | RESOLVED (Sprint 1) |
| `BaseParser.parse()` -> `Flight` only | `parse()` -> `(Flight, ParseDiagnostics, Provenance)` | RESOLVED (Sprint 3) |
| `Plugin.analyze()` -> `list[Finding]` | `analyze()` -> `PluginResult` with diagnostics | OPEN (Sprint 5) |
| Stateless single-page GUI | Case-oriented multi-view GUI | PARTIAL (Sprint 2, Sprint 6 for full workspace) |
| No case/evidence/audit models | Full forensic case lifecycle | RESOLVED (Sprint 1) |
| DataFlash/TLog/CSV `can_parse()` = True | Disable stubs OR implement honestly | RESOLVED (Sprint 3, `implemented=False`) |

---

## 5. Doc/Code Mismatches (Sprint 0 baseline, updated Sprint 3)

| Document | Sprint 0 Issue | Sprint 3 Status |
|----------|---------------|-----------------|
| `docs/supported-formats.md` | Stub parsers that can_parse() = True | FIXED: stubs marked `implemented=False` |
| `docs/api-reference.md` | Documents `/api/analyze` as main path | FIXED: case-oriented API routes added (Sprint 2) |
| `docs/writing-plugins.md` | Missing manifest, trust, output contract | Still missing (Sprint 5) |
| README | Listed all 4 formats as if supported | FIXED: only ULog listed as supported |

---

## 6. Implementation Order

Following the sprint plan from spec doc 05:

1. **Sprint 0**: CI/CD, GitHub governance, this audit document -- COMPLETE
2. **Sprint 1**: Case + Evidence + Audit models and services -- COMPLETE
3. **Sprint 2**: Case-oriented GUI and API refactor -- COMPLETE
4. **Sprint 3**: Parser contract + ParseDiagnostics + ULog adaptation -- COMPLETE
5. **Sprint 4** (in progress): Expanded Finding + EvidenceReference + Hypothesis
6. **Sprint 5**: Plugin manifest + analyzer contract + trust scaffolding
7. **Sprint 6**: GUI investigation workspace
8. **Sprint 7**: Correlation + reconstruction engine
9. **Sprint 8**: Export bundle + replay
10. **Sprint 9**: Trust policy engine + tuning profiles
11. **Sprint 10**: Format truthfulness + parser support matrix
12. **Sprint 11**: Connected portal alignment

---

## 7. Risk Register

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Parser contract change breaks existing tests | HIGH | Add compatibility shim; update tests in Sprint 3 |
| GUI refactor loses existing working charts | HIGH | Preserve cockpit.js; embed in case workspace |
| Case model adds storage complexity | MEDIUM | Start with local filesystem; abstract storage layer |
| Temp-file removal breaks `/api/analyze` route | MEDIUM | Add compatibility wrapper during Sprint 2 transition |
| DataFlash/TLog stubs mislead users | MEDIUM | Hard-disable in Sprint 0 or Sprint 10 |
| 389 existing tests may fail after contract changes | MEDIUM | Run CI on every PR; fix as part of each sprint |
| `crashed` property is a heuristic on Flight | LOW | Move to CrashDetectionPlugin findings; keep as convenience only |

---

## 8. Proposed Repository Workstream Structure

```
Goose-Core/
├── src/goose/
│   ├── forensics/          # NEW: case, evidence, audit, provenance, manifest
│   ├── core/               # EXTEND: flight, finding, phases, scoring, narrative
│   ├── parsers/            # EXTEND: new contract, diagnostics
│   ├── plugins/            # EXTEND: manifest, trust, output contract
│   ├── analysis/           # NEW: engine, correlation, hypothesis
│   ├── replay/             # NEW: export, import, verification
│   ├── reports/            # EXTEND: case bundle, structured reports
│   ├── web/                # REFACTOR: case-oriented API + GUI
│   ├── cli/                # EXTEND: case commands
│   ├── telemetry/          # PRESERVE
│   └── config/             # EXTEND: policy, trust, tuning
├── docs/
│   ├── architecture/       # This file, target arch, migration plan
│   ├── adr/                # Architecture Decision Records
│   ├── forensics/          # Forensic model docs
│   ├── gui/                # GUI workflow docs
│   ├── plugins/            # Plugin development guide
│   └── dev/                # Contributing, setup, CI
└── .github/
    ├── workflows/           # CI/CD pipelines
    ├── ISSUE_TEMPLATE/     # Feature, bug, ADR templates
    └── pull_request_template.md
```
