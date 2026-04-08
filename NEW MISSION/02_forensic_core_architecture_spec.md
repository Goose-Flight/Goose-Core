# Goose Claude Pack 02 - Forensic Core Architecture Spec

## Purpose

This document defines the entire forensic framework Goose must be built on.
It describes the system architecture, case model, evidence handling, parser framework, findings model, replay model, reporting model, and assurance-oriented foundations needed for a serious flight forensic platform.

Claude should use this as the primary engineering specification for the forensic subsystem.

---

## 1. Architectural Objective

Goose must become a **case-oriented, evidence-preserving, replayable flight forensic system**.

The forensic core must be reusable across:
- local GUI workflows
- CLI and automation workflows
- future portal uploads and connected analysis
- future enterprise deployments
- future hardened or isolated deployments

This means the forensic core must not be tightly coupled to one UI, one deployment mode, or one ingestion path.

---

## 2. Core Forensic Lifecycle

Every investigation should follow the same core lifecycle:

1. create case
2. ingest evidence
3. hash and manifest evidence
4. detect format
5. parse into canonical model
6. record diagnostics and provenance
7. run analyzers/plugins
8. correlate findings
9. construct hypotheses and timeline
10. review in GUI
11. export case bundle and/or reports
12. replay later if needed

This lifecycle is the backbone of Goose.

---

## 3. Forensic Subsystems

Claude must design and build these subsystems explicitly.

### 3.1 Case subsystem
Responsible for:
- case creation
- case metadata
- case status
- case notes/tags
- analysis run history
- export history

### 3.2 Evidence subsystem
Responsible for:
- evidence ingest
- evidence storage
- hashing
- evidence manifest generation
- immutable original handling
- evidence provenance

### 3.3 Parser subsystem
Responsible for:
- format detection
- parser selection
- parse execution
- parse diagnostics
- parse provenance
- canonical output generation

### 3.4 Canonical data subsystem
Responsible for:
- normalized flight data model
- events and parameters
- signal quality representation
- evidence references
- findings and hypotheses structures

### 3.5 Analysis subsystem
Responsible for:
- deterministic plugin execution
- plugin diagnostics
- finding generation
- confidence calculation
- contradiction handling
- timeline generation
- hypothesis support

### 3.6 Replay and export subsystem
Responsible for:
- case bundle export
- case import/replay
- replay verification
- version compatibility handling

### 3.7 Audit subsystem
Responsible for:
- write-once analysis events
- evidence access traces
- export traces
- parser/analyzer execution traces
- policy-relevant activity logging

### 3.8 Report subsystem
Responsible for:
- machine-readable exports first
- structured mission/anomaly/crash report objects
- GUI-facing summary objects
- future HTML/PDF generation

---

## 4. Required Data Models

Claude must formalize and version the following models.

### 4.1 Case
Required fields:
- case_id
- created_at
- created_by
- status
- tags
- notes
- engine_version
- ruleset_version
- plugin_policy_version
- analysis_runs[]
- evidence_items[]
- exports[]

### 4.2 EvidenceItem
Required fields:
- evidence_id
- filename
- content_type
- size_bytes
- sha256
- sha512 optional but preferred
- source_acquisition_mode
- source_reference
- stored_path
- acquired_at
- acquired_by
- immutable flag
- notes

### 4.3 EvidenceManifest
Required fields:
- manifest_version
- case_id
- evidence list
- hash information
- acquisition metadata
- derived artifact map
- retention metadata

### 4.4 Provenance
Required fields:
- source evidence ID
- parser name/version
- transformation chain
- timestamps
- config references
- engine/build version
- plugin references where applicable

### 4.5 ParseDiagnostics
Required fields:
- parser selected
- parser version
- detected format
- format confidence
- parser confidence
- warnings
- errors
- missing streams/topics
- corruption indicators
- stream coverage summary
- timebase anomalies
- assumptions made

### 4.6 SignalQuality
Required fields:
- stream name
- completeness
- continuity
- corruption status
- reliability estimate
- notes

### 4.7 Finding
Required fields:
- finding_id
- plugin_id
- plugin_version
- title
- description
- severity
- score
- confidence
- phase
- start_time
- end_time
- evidence_references[]
- supporting_metrics
- contradicting_metrics
- assumptions

### 4.8 EvidenceReference
Required fields:
- evidence_id
- stream/topic name
- time range
- sample index range if available
- parameter reference if relevant
- summary of supporting basis

### 4.9 Hypothesis
Required fields:
- hypothesis_id
- statement
- supporting_findings[]
- contradicting_findings[]
- confidence
- status
- unresolved_questions[]
- analyst_notes optional

### 4.10 AuditEntry
Required fields:
- event_id
- timestamp
- actor
- action_type
- object_type
- object_id
- details
- success
- error optional

---

## 5. Evidence Handling Rules

Claude must treat evidence handling as a core forensic primitive.

### Required rules
- original evidence must not be mutated
- evidence must be hashed immediately on ingest
- evidence must be attached to a case
- derived artifacts must be linked back to the source evidence
- evidence provenance must remain visible in the GUI and export artifacts
- evidence access and analysis must be auditable

### Storage rule
Do not use ad hoc temp storage as the source of truth for analysis.
A temporary working copy may exist, but only after immutable case evidence is established.

### Example case directory structure
```text
cases/
  CASE-2026-000001/
    case.json
    evidence/
      EV-0001-flight.ulg
    manifests/
      evidence_manifest.json
    parsed/
      canonical_flight.json
      parse_diagnostics.json
      provenance.json
    analysis/
      findings.json
      hypotheses.json
      timeline.json
      plugin_diagnostics.json
    audit/
      audit_log.jsonl
    exports/
      case_bundle_v1.json
```

---

## 6. Parser Architecture

Claude must define and enforce a formal parser framework.

### Every parser must provide
- parser ID and name
- parser version
- supported format declarations
- detection capability
- parse capability
- parse diagnostics
- provenance output

### Parser contract
Each parser should return a result shaped like:
- canonical Flight
- ParseDiagnostics
- Provenance
- optional supporting parse artifacts

### Parser truthfulness rules
- unsupported formats must fail clearly
- partial parses must still return diagnostics
- corruption must be surfaced
- missing topics/streams must be reported
- assumptions about timebase or ordering must be recorded

### Format support rule
If a format is not truly implemented, Claude must disable or hide that support everywhere until real implementation exists.
Do not imply support via UI or docs.

---

## 7. Canonical Model Objective

The canonical model is the layer that makes Goose extensible and trustworthy.

Parsers convert source-specific logs into canonical structures.
Plugins and reports operate on canonical structures, not parser-specific raw formats.

The canonical model must represent:
- telemetry streams
- flight phases
- mode changes
- events/faults/failsafes
- parameters
- battery/power state
- navigation state
- control inputs
- vibration state
- motor/propulsion signals
- health and signal quality

---

## 8. Findings, Correlation, and Hypotheses

Goose must not stop at isolated findings.
It should build toward structured forensic reasoning.

### Findings layer
Plugins emit findings.
Findings must be evidence-backed, confidence-scored, and time-bounded where possible.

### Correlation layer
The analysis engine should correlate findings across plugins.
Examples:
- GPS degradation + EKF divergence
- battery sag + power instability + crash signature
- vibration anomaly + attitude instability

### Hypothesis layer
Hypotheses are structured root-cause candidates built on top of findings.
They must show:
- supporting findings
- contradicting findings
- confidence
- unresolved questions

### Rule
Facts, findings, and hypotheses must remain distinct.
Do not blur raw evidence with interpretation.

---

## 9. Replay and Export

Replayability is foundational.

### Goose must support
- export of replayable case bundles
- later re-import/replay of a case
- verification of what engine/ruleset/plugin versions were used
- visibility into whether replay was exact-match or version-drifted

### Export priority order
1. machine-readable JSON case bundle
2. structured GUI-facing summary objects
3. future HTML report
4. future PDF report

### Required report object types
- MissionSummaryReport
- AnomalyReport
- CrashMishapReport
- ForensicCaseReport
- EvidenceManifestReport
- ReplayVerificationReport

---

## 10. Audit and Assurance Foundations

Claude must build in foundations now that matter for serious enterprise or government use later.

### Build in now
- evidence integrity and chain-of-custody style handling
- audit logs
- policy enforcement hooks
- role-aware access hooks
- trust-state visibility
- reproducibility mechanisms
- secure configuration handling
- export provenance
- contract versioning
- support path for SBOM and signed artifacts

### Do not claim yet
Goose should not claim formal compliance with military or regulatory systems unless later validated for them.
But it should be built in a way that later mapping is feasible.

---

## 11. API and Service Design Rule

The forensic core must be service-oriented and reused everywhere.

The GUI, CLI, and future portal must all call the same underlying case and analysis services.
Do not create separate logic that bypasses the forensic core.

---

## 12. First Foundational Milestone

Claude’s first major goal should be:

Take one real `.ulg` log and support the full path:
- create case
- ingest evidence immutably
- hash evidence
- write manifest
- parse into canonical model
- generate parse diagnostics
- run deterministic analyzers
- write findings and hypotheses
- show them in the GUI
- export replayable bundle
- replay it later

If Goose can do that cleanly, the foundation is real.

---

## 13. Final Instruction to Claude

Build the forensic core so it can support a top-tier open-source flight forensic platform now and a serious enterprise-grade investigation platform later.

Preserve evidence.
Parse honestly.
Analyze deterministically.
Cite everything.
Expose uncertainty.
Replay later.
Reuse the same core everywhere.
