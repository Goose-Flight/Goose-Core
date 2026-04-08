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

## Case Directory Schema (Sprint 1)

### Exact layout and ownership rules

```
cases/
  {CASE_ID}/                      # e.g. CASE-2026-000001
    case.json                     # OWNER: CaseService — written on create, updated on state changes
    evidence/
      {EV_ID}-{original_name}     # OWNER: CaseService — copied once, set read-only, never modified
                                  # e.g. EV-0001-flight.ulg
    manifests/
      evidence_manifest.json      # OWNER: CaseService — written after each evidence ingest
    parsed/
      canonical_flight.json       # OWNER: ParserFramework — written after successful parse
      parse_diagnostics.json      # OWNER: ParserFramework — always written (even on partial parse)
      provenance.json             # OWNER: ParserFramework — written alongside parse output
    analysis/
      findings.json               # OWNER: AnalysisEngine — written after analysis run
      hypotheses.json             # OWNER: AnalysisEngine (Sprint 7+)
      timeline.json               # OWNER: AnalysisEngine (Sprint 7+)
      plugin_diagnostics.json     # OWNER: AnalysisEngine — written after analysis run
    audit/
      audit_log.jsonl             # OWNER: AuditService — append-only, never overwritten
    exports/
      {EXPORT_ID}_bundle.json     # OWNER: ExportService (Sprint 8)
```

### Naming rules
- `CASE_ID`: `CASE-YYYY-{6-digit-sequence}`, e.g. `CASE-2026-000001`
- `EV_ID`: `EV-{4-digit-sequence}`, e.g. `EV-0001`
- Evidence filename: `{EV_ID}-{sanitized_original_filename}`
- No spaces in any path component — underscores only
- All JSON files use 2-space indentation
- `audit_log.jsonl`: one JSON object per line, never pretty-printed

### Immutability rules
- Evidence files in `evidence/` are set to read-only (mode 0o444) immediately after copy
- `audit_log.jsonl` is opened in append mode only — never truncated or rewritten
- `case.json` is the only file that changes after initial write (status, run history, export history)
- All other files are write-once per analysis run

---

## Sprint 1 Model Contracts

These are the exact typed contracts to implement in `src/goose/forensics/models.py`.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CaseStatus(str, Enum):
    OPEN = "open"
    ANALYZING = "analyzing"
    REVIEW = "review"
    CLOSED = "closed"
    ARCHIVED = "archived"


class AuditAction(str, Enum):
    CASE_CREATED = "case_created"
    EVIDENCE_INGESTED = "evidence_ingested"
    PARSE_STARTED = "parse_started"
    PARSE_COMPLETED = "parse_completed"
    PARSE_FAILED = "parse_failed"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    CASE_EXPORTED = "case_exported"
    EVIDENCE_ACCESSED = "evidence_accessed"


@dataclass
class EvidenceItem:
    evidence_id: str               # e.g. "EV-0001"
    filename: str                  # original filename
    content_type: str              # "application/octet-stream" or detected MIME
    size_bytes: int
    sha256: str                    # lowercase hex, always present
    sha512: str | None             # lowercase hex, preferred but optional
    source_acquisition_mode: str   # "upload" | "local_copy" | "remote_fetch"
    source_reference: str | None   # original path or URL if applicable
    stored_path: str               # absolute path to immutable copy in case dir
    acquired_at: datetime
    acquired_by: str               # "gui" | "cli" | "api"
    immutable: bool = True         # always True for stored evidence
    notes: str = ""


@dataclass
class EvidenceManifest:
    manifest_version: str = "1.0"
    case_id: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)
    evidence: list[EvidenceItem] = field(default_factory=list)
    # derived_artifacts maps evidence_id -> list of artifact paths produced from it
    derived_artifacts: dict[str, list[str]] = field(default_factory=dict)
    retention_policy: str = "indefinite"


@dataclass
class AnalysisRun:
    run_id: str
    started_at: datetime
    completed_at: datetime | None
    plugin_versions: dict[str, str]   # plugin_id -> version
    ruleset_version: str | None
    findings_count: int
    status: str                        # "completed" | "failed" | "in_progress"
    error: str | None = None


@dataclass
class CaseExport:
    export_id: str
    exported_at: datetime
    export_path: str
    bundle_version: str
    includes_replay: bool


@dataclass
class Case:
    case_id: str                                     # e.g. "CASE-2026-000001"
    created_at: datetime
    created_by: str                                  # "gui" | "cli" | actor identifier
    status: CaseStatus = CaseStatus.OPEN
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    engine_version: str = ""                         # goose package version
    ruleset_version: str | None = None
    plugin_policy_version: str | None = None
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    analysis_runs: list[AnalysisRun] = field(default_factory=list)
    exports: list[CaseExport] = field(default_factory=list)


@dataclass
class Provenance:
    source_evidence_id: str
    parser_name: str
    parser_version: str
    detected_format: str
    parsed_at: datetime
    transformation_chain: list[str] = field(default_factory=list)
    config_references: dict[str, str] = field(default_factory=dict)
    engine_version: str = ""
    build_hash: str | None = None
    assumptions: list[str] = field(default_factory=list)


@dataclass
class AuditEntry:
    event_id: str
    timestamp: datetime
    actor: str                    # "gui" | "cli" | "system" | user identifier
    action: AuditAction
    object_type: str              # "case" | "evidence" | "analysis" | "export"
    object_id: str                # case_id or evidence_id
    details: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None
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
