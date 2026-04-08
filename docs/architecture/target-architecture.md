---
title: Goose-Core Target Architecture
version: v2.0 (NEW MISSION)
status: draft
---

# Goose-Core Target Architecture

This document defines the target architecture for Goose-Core as specified by
the NEW MISSION spec pack. It is the architectural north star for all sprints.

---

## Core Principle

Goose is a **case-oriented, evidence-preserving, replayable flight forensic system**.

Every analysis must be traceable. Every conclusion must cite evidence.
Every run must be replayable. Uncertainty must be surfaced, not hidden.

---

## Layer Model

```
Layer 4: Enterprise / Hardened Controls (future)
Layer 3: Connected Portal Features (Sprint 11+)
Layer 2: GUI Application (primary product surface)
Layer 1: Core Forensic Engine (all other layers call this)
```

All layers call the same Layer 1 forensic services.
No layer bypasses the case model.

---

## Subsystem Map

```
src/goose/
├── forensics/                  # Layer 1 — Core Forensic Engine
│   ├── case.py                 # Case, CaseStatus, AnalysisRun models
│   ├── evidence.py             # EvidenceItem, EvidenceManifest models
│   ├── provenance.py           # Provenance model
│   ├── audit.py                # AuditEntry, AuditLog (write-once)
│   ├── manifest.py             # EvidenceManifest generation
│   ├── hashing.py              # SHA-256/SHA-512 utilities
│   └── case_service.py         # Case directory management, ingest, storage
│
├── parsers/                    # Layer 1 — Parser Subsystem
│   ├── base.py                 # EXTENDED: ParseResult contract
│   ├── diagnostics.py          # ParseDiagnostics, SignalQuality models
│   ├── detect.py               # EXTENDED: magic-byte + extension detection
│   ├── ulog.py                 # ADAPTED: returns ParseResult
│   ├── dataflash.py            # DISABLED until real implementation
│   ├── tlog.py                 # DISABLED until real implementation
│   └── csv_parser.py           # DISABLED until real implementation
│
├── core/                       # Layer 1 — Canonical Data Model
│   ├── flight.py               # EXTENDED: provenance_id, signal_quality
│   ├── finding.py              # EXTENDED: finding_id, plugin_version,
│   │                           #   confidence, evidence_references,
│   │                           #   contradicting_metrics, assumptions
│   ├── hypothesis.py           # NEW: Hypothesis model
│   ├── evidence_ref.py         # NEW: EvidenceReference model
│   ├── signal_quality.py       # NEW: SignalQuality model
│   ├── phases.py               # PRESERVE
│   ├── crash_detector.py       # PRESERVE (heuristic helper only)
│   ├── scoring.py              # EXTEND
│   └── narrative.py            # MIGRATE → reports/narrative.py
│
├── analysis/                   # Layer 1 — Analysis Engine
│   ├── engine.py               # NEW: orchestrates plugin execution
│   ├── correlation.py          # NEW: cross-plugin finding correlation
│   ├── hypothesis_builder.py   # NEW: builds Hypothesis objects
│   └── timeline.py             # NEW: timeline artifact generation
│
├── plugins/                    # Layer 1 — Plugin Subsystem
│   ├── base.py                 # EXTENDED: manifest, PluginResult contract
│   ├── manifest.py             # NEW: PluginManifest, TrustState models
│   ├── trust.py                # NEW: trust policy engine, allowlist
│   ├── registry.py             # EXTENDED: trust-aware loading
│   └── [11 plugin files]       # CONVERTED to new contract
│
├── replay/                     # Layer 1 — Replay and Export
│   ├── bundle.py               # NEW: case bundle serialization
│   ├── exporter.py             # NEW: export to JSON case bundle
│   └── replayer.py             # NEW: replay from case bundle
│
├── reports/                    # Layer 1 — Report Subsystem
│   ├── json_report.py          # EXTEND: case-bundle-aware
│   ├── mission_summary.py      # NEW: MissionSummaryReport
│   ├── crash_report.py         # NEW: CrashMishapReport
│   ├── anomaly_report.py       # NEW: AnomalyReport
│   ├── narrative.py            # MOVED from core/
│   └── html_report.py          # EXTEND
│
├── web/                        # Layer 2 — GUI Application
│   ├── app.py                  # REFACTORED: case-oriented routes
│   ├── api/
│   │   ├── cases.py            # NEW: case CRUD routes
│   │   ├── evidence.py         # NEW: evidence ingest routes
│   │   ├── analysis.py         # NEW: analysis run routes
│   │   ├── findings.py         # NEW: findings query routes
│   │   ├── plugins.py          # EXTEND: trust-aware plugin routes
│   │   └── legacy.py           # COMPAT: /api/analyze shim (temporary)
│   └── static/
│       ├── index.html          # REFACTORED: case-oriented SPA
│       ├── cockpit.js          # PRESERVE: embed in case workspace
│       └── cockpit.css         # PRESERVE
│
├── cli/                        # Layer 2 (secondary) — CLI
│   ├── main.py                 # EXTEND: case commands
│   ├── cases.py                # NEW: case create/list/open
│   ├── analyze.py              # EXTEND: case-aware
│   ├── serve.py                # PRESERVE
│   └── ...
│
├── config/                     # Policy and Trust
│   ├── settings.py             # EXTEND: deployment mode, trust policy
│   ├── policy.py               # NEW: PluginPolicy, DeploymentMode
│   └── tuning.py               # NEW: TuningProfile, versioned configs
│
└── telemetry/                  # PRESERVE as-is
```

---

## Data Flow

```
User (GUI or CLI)
    │
    ▼
CaseService.create_case()
    │
    ▼
CaseService.ingest_evidence(file)
    ├── hash (SHA-256 + SHA-512)
    ├── store immutably in cases/CASE-ID/evidence/
    ├── write EvidenceManifest
    └── write AuditEntry

    │
    ▼
ParserFramework.parse(evidence_item)
    ├── detect format
    ├── select parser
    ├── parse → (Flight, ParseDiagnostics, Provenance)
    ├── store in cases/CASE-ID/parsed/
    └── write AuditEntry

    │
    ▼
AnalysisEngine.run(case, plugins, config)
    ├── for each plugin:
    │   ├── check trust policy
    │   ├── execute deterministically
    │   ├── receive PluginResult (findings, diagnostics, confidence)
    │   └── write AuditEntry
    ├── correlate findings → Hypotheses
    ├── generate Timeline
    └── store in cases/CASE-ID/analysis/

    │
    ▼
GUI renders:
    ├── Case Workspace
    ├── Evidence View (hashes, provenance)
    ├── Parse Diagnostics View
    ├── Findings View (evidence-linked)
    ├── Timeline View
    ├── Chart Workspace (uPlot)
    ├── Hypothesis View
    └── Export / Reports
```

---

## Case Directory Structure

```
cases/
  CASE-2026-000001/
    case.json                  # Case model (id, metadata, status, runs, exports)
    evidence/
      EV-0001-flight.ulg       # Immutable original
    manifests/
      evidence_manifest.json   # Hashes + acquisition metadata
    parsed/
      canonical_flight.json    # Serialized Flight
      parse_diagnostics.json   # ParseDiagnostics
      provenance.json          # Provenance
    analysis/
      findings.json            # All Finding objects
      hypotheses.json          # Hypothesis objects
      timeline.json            # Timeline artifacts
      plugin_diagnostics.json  # Per-plugin diagnostics
    audit/
      audit_log.jsonl          # Append-only AuditEntry records
    exports/
      case_bundle_v1.json      # Replayable export
```

---

## Key Contracts (Sprint Targets)

### ParseResult (Sprint 3)
```python
@dataclass
class ParseResult:
    flight: Flight
    diagnostics: ParseDiagnostics
    provenance: Provenance
    artifacts: dict[str, Any] = field(default_factory=dict)
```

### PluginResult (Sprint 5)
```python
@dataclass
class PluginResult:
    findings: list[Finding]
    plugin_diagnostics: PluginDiagnostics
    confidence_notes: list[str]
    contradiction_flags: list[str]
    execution_metadata: dict[str, Any]
```

### Extended Finding (Sprint 4)
Added fields: `finding_id`, `plugin_version`, `confidence: float`,
`evidence_references: list[EvidenceReference]`, `contradicting_metrics`,
`assumptions: list[str]`.

---

## Deployment Modes

| Mode | Plugin Policy | Network | Storage |
|------|--------------|---------|---------|
| Local Solo | unsigned allowed | disabled | local filesystem |
| Connected Team | unsigned with warning | opt-in | local + sync |
| Controlled Enterprise | allowlist only | managed | managed |
| Hardened / Isolated | signed + allowlisted | disabled | local isolated |
