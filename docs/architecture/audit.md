---
title: Goose-Core Architecture Audit
version: Sprint 0
date: 2026-04-07
status: baseline
---

# Goose-Core Architecture Audit — Sprint 0 Baseline

This document captures the current state of Goose-Core as of v1.3.4 against
the NEW MISSION spec pack. It is the authoritative Sprint 0 deliverable.

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

### 2.1 Case Subsystem — MISSING

**Required:** Case model, EvidenceItem, EvidenceManifest, case directory service,
case status, analysis run history, export history.

**Current:** No case concept exists. All analysis is stateless and ephemeral.
Each API call creates a temp file, analyzes it, and discards it.

**Impact:** HIGH — foundational. All other forensic subsystems depend on this.

---

### 2.2 Evidence Subsystem — MISSING

**Required:** Immutable ingest, SHA-256/SHA-512 hashing, evidence manifest,
provenance tracking, immutable original storage.

**Current:** `tempfile.NamedTemporaryFile(delete=False)` is the ingest path.
Files are deleted after analysis. No hashing. No manifest. No provenance.

**Impact:** CRITICAL. Violates the #1 non-negotiable from the Master Brief.

---

### 2.3 Parser Subsystem — PARTIAL

**Required:** Parser ID, parser version, ParseDiagnostics, Provenance output,
format confidence, corruption surfacing, missing-stream reporting.

**Current:**
- `BaseParser.parse()` returns only `Flight` (no diagnostics, no provenance)
- `can_parse()` is extension-only (no magic-byte detection)
- No `ParseDiagnostics` model exists
- No `Provenance` model exists
- DataFlash/TLog/CSV stubs exist and `can_parse()` returns True for matching
  extensions — this is a truthfulness violation per spec Section 6

**Impact:** HIGH — parser contract must change before Sprint 3.
Note: `docs/supported-formats.md` already marks non-ULog as "Planned" (good).
But the stubs still `can_parse()` = True and attempt to parse, which can mislead.

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

### 2.8 Audit Subsystem — MISSING

**Required:** Write-once audit log, evidence access traces, parser/analyzer
execution traces, export traces.

**Current:** Python `logging` module used throughout. No structured audit trail.

**Impact:** MEDIUM — foundational for enterprise/government credibility.

---

### 2.9 GUI Workflow — DOES NOT MATCH SPEC

**Required:** Case-oriented workflow: create case → ingest evidence → parse →
analyze → findings → timeline → export. Case list, evidence view, parse
diagnostics, plugin inventory, hypothesis view, admin view.

**Current:** Single-page upload-and-display. No case concept. Analysis is
one-shot stateless. No evidence integrity display. No parse diagnostics view.
No plugin trust visibility. No hypothesis view.

**Impact:** HIGH — the entire GUI workflow must be rebuilt around the case model.
The existing charts, timeline, and findings display can be preserved and embedded
into the case workspace.

---

### 2.10 CI/CD — MISSING

No `.github/workflows/` exists. No automated linting, formatting checks, type
checking, test runs, coverage, or security scanning.

**Impact:** HIGH — must be in place before Sprint 1 coding begins.

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
| Test suite (~258 tests) | `tests/` | Yes — extend |

---

## 4. What Conflicts and Must Change

| Current Behavior | Required Behavior | Risk |
|-----------------|-------------------|------|
| Temp-file ingest in `/api/analyze` | Immutable case evidence ingest | HIGH |
| `BaseParser.parse()` → `Flight` only | `parse()` → `(Flight, ParseDiagnostics, Provenance)` | HIGH |
| `Plugin.analyze()` → `list[Finding]` | `analyze()` → `PluginResult` with diagnostics | MEDIUM |
| Stateless single-page GUI | Case-oriented multi-view GUI | HIGH |
| No case/evidence/audit models | Full forensic case lifecycle | CRITICAL |
| DataFlash/TLog/CSV `can_parse()` = True | Disable stubs OR implement honestly | MEDIUM |

---

## 5. Doc/Code Mismatches

| Document | Claim | Reality |
|----------|-------|---------|
| `docs/supported-formats.md` | DataFlash/TLog/CSV are "Planned" | Code has stub parsers that can_parse() = True and attempt to parse |
| `docs/api-reference.md` | Documents `/api/analyze` as main path | Spec requires case-oriented API |
| `docs/writing-plugins.md` | Shows Plugin base class interface | Missing manifest, trust, output contract |
| README | Lists all 4 formats | Only ULog is real |

---

## 6. Recommended Implementation Order

Following the sprint plan from spec doc 05:

1. **Sprint 0** (now): CI/CD, GitHub governance, this audit document
2. **Sprint 1**: Case + Evidence + Audit models and services (PR 1)
3. **Sprint 2**: Case-oriented GUI and API refactor (PR 2)
4. **Sprint 3**: Parser contract + ParseDiagnostics + ULog adaptation (PR 3)
5. **Sprint 4**: Expanded Finding + EvidenceReference + Hypothesis (PR 4)
6. **Sprint 5**: Plugin manifest + analyzer contract + trust scaffolding (PR 5)
7. **Sprint 6**: GUI investigation workspace (PR 6)
8. **Sprint 7**: Correlation + reconstruction engine
9. **Sprint 8**: Export bundle + replay (PR 7)
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
| 258 existing tests may fail after contract changes | MEDIUM | Run CI on every PR; fix as part of each sprint |
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
