# Goose Claude Pack 05 - Sprint Plan and Acceptance Criteria

## Purpose

This document tells Claude how to execute the work.
It breaks the foundational build into implementation sprints, defines milestone acceptance criteria, and gives a practical sequence for building Goose correctly.

Claude should use this as the project execution plan.

---

## 1. Execution Strategy

Claude should not try to build everything at once.
The right approach is to build the forensic substrate first, then expose it through the GUI, then expand plugin depth, replay, and connected capabilities.

Claude should prefer:
- small, reviewable refactors
- explicit contracts
- testable intermediate states
- honest support claims

---

## 2. Sprint 0 - Audit and Stabilization

### Goal
Understand the current codebase and remove ambiguity before major refactor.

### Deliverables
- code path audit of CLI, API, parser, plugin, GUI, and report flows
- list of doc/code mismatches
- target module map
- migration risks
- behaviors that must be preserved during refactor

### Acceptance criteria
- current state is clearly documented
- known mismatch areas are identified
- first refactor sequence is planned

---

## 3. Sprint 1 - Case and Evidence Foundation

### Goal
Create the true forensic substrate.

### Deliverables
- Case model
- EvidenceItem model
- EvidenceManifest model
- Provenance model
- AuditEntry model
- case directory service
- evidence hashing service
- immutable evidence ingest flow
- ingest tests and immutability tests

### Acceptance criteria
- a case can be created
- evidence can be ingested into a case
- evidence is hashed and written to a manifest
- original evidence is preserved immutably
- audit entries are written

---

## 4. Sprint 2 - Case-Oriented GUI and API Refactor

### Goal
Make the web GUI and API use the case-based forensic workflow as the primary user path.

### Deliverables
- case create flow in GUI
- evidence ingest flow in GUI
- case-oriented API routes
- compatibility layer for old direct-analysis routes if needed
- removal or deprecation plan for temp-file-first workflow

### Acceptance criteria
- a normal user can create a case and ingest evidence entirely through the GUI
- the GUI uses case-based APIs
- temp-file paths are no longer the source of truth

---

## 5. Sprint 3 - Parser Framework and Diagnostics

### Goal
Formalize parsing as a real forensic subsystem.

### Deliverables
- parser base contract
- parser detection module
- parse result contract
- ParseDiagnostics model
- adaptation of existing ULog parser to new contract
- parser tests including corruption and missing-data cases

### Acceptance criteria
- ULog parsing runs through the new contract
- parse diagnostics are always returned
- corruption and missing-data conditions surface clearly
- unsupported formats fail honestly

---

## 6. Sprint 4 - Canonical Model Completion

### Goal
Make the data model truly forensic-ready.

### Deliverables
- SignalQuality model
- EvidenceReference model
- expanded Finding model
- Hypothesis model
- provenance linkage across parsed and analyzed artifacts
- serialization support for exports

### Acceptance criteria
- findings can cite evidence clearly
- hypotheses can link supporting and contradicting findings
- parsed and analyzed artifacts are traceable back to evidence

---

## 7. Sprint 5 - Analyzer Contract and First Plugin Conversion

### Goal
Turn plugins into formal analyzers with trust-aware metadata.

### Deliverables
- analyzer contract
- plugin manifest schema
- plugin diagnostics model
- trust-state representation
- conversion of first built-in analyzers to new contract
- GUI plugin inventory basics

### Acceptance criteria
- plugins have formal metadata
- findings record plugin version and trust state
- GUI shows plugin inventory and trust state
- converted plugins emit evidence-backed findings

---

## 8. Sprint 6 - GUI Investigation Workspace

### Goal
Make the GUI feel like a real forensic workstation.

### Deliverables
- case workspace
- evidence panel
- parse diagnostics view
- findings view
- timeline view
- charting workspace
- hypothesis view

### Acceptance criteria
- users can move between evidence, diagnostics, findings, timeline, and charts within the case workspace
- findings link to chart windows and evidence references
- diagnostics and uncertainty are visible in the GUI

---

## 9. Sprint 7 - Correlation and Reconstruction

### Goal
Move from isolated findings to structured forensic reasoning.

### Deliverables
- correlation engine
- contradiction handling
- corroboration scoring
- timeline reconstruction helpers
- hypothesis support scoring

### Acceptance criteria
- multiple findings can be correlated into structured hypotheses
- contradictions are visible
- timeline artifacts reflect analyzed findings

---

## 10. Sprint 8 - Export and Replay

### Goal
Make cases portable and reproducible.

### Deliverables
- JSON case bundle export
- replay service
- replay verification logic
- export history in case metadata
- replay controls in GUI

### Acceptance criteria
- a case can be exported and replayed later
- replay shows whether it matches the original analysis conditions
- GUI can trigger and inspect replay

---

## 11. Sprint 9 - Plugin Trust and Tuning Foundations

### Goal
Add real structure to plugin policy and tuning.

### Deliverables
- plugin hash/fingerprint tracking
- trust-policy engine
- allowlist support
- tuning profile model
- analysis recording of plugin/tuning versions
- GUI trust state visibility improvements

### Acceptance criteria
- plugin trust decisions are visible and auditable
- analysis output records plugin and tuning context
- different deployment modes can enforce different plugin policies

---

## 12. Sprint 10 - Format Truthfulness and Breadth

### Goal
Make supported formats honest and extensible.

### Deliverables
- either real implementation or hard-disable for non-ULog parser paths
- support matrix in GUI/docs
- unsupported-format diagnostics
- parser confidence visibility

### Acceptance criteria
- Goose does not imply unsupported parser coverage
- GUI and docs reflect actual support correctly

---

## 13. Sprint 11 - Connected Portal Alignment

### Goal
Support future cloud-connected workflows without corrupting the local forensic architecture.

### Deliverables
- opt-in upload and sync hooks around case objects
- explicit portal adapter layer
- telemetry-sharing policy controls
- no bypass around evidence/case rules

### Acceptance criteria
- portal flows still produce the same kind of forensic case objects
- connected features are optional and do not replace local core logic

---

## 14. Global Acceptance Criteria

Claude should use these as final quality gates.

### Gate A - forensic integrity
- evidence is preserved immutably
- manifests and hashes exist
- provenance is retained

### Gate B - GUI completeness
- important workflows are fully usable from the GUI
- GUI is not dependent on hidden CLI-only capability

### Gate C - parser honesty
- parse diagnostics are visible
- unsupported formats fail clearly
- missing data is not hidden

### Gate D - plugin trustability
- plugin source, version, and trust state are visible
- plugin execution is auditable

### Gate E - replayability
- cases can be exported and replayed later
- replay conditions are visible

### Gate F - architecture portability
- local, GUI, CLI, and future portal paths all use the same core case-oriented services

---

## 15. Suggested Initial PR Sequence

### PR 1
- case/evidence/provenance/audit models
- case storage utilities
- hashing and manifest generation
- tests

### PR 2
- GUI case creation and evidence ingest
- case-oriented API routes
- compatibility wrapper for legacy analysis path if needed

### PR 3
- parser base and parse result contracts
- ULog adaptation
- parse diagnostics and detection module

### PR 4
- canonical evidence reference and hypothesis models
- expanded finding model

### PR 5
- plugin manifest schema
- analyzer contract
- conversion of first analyzers
- plugin trust-state model

### PR 6
- case workspace and diagnostics/finding GUI views
- chart/timeline integration basics

### PR 7
- export bundle and replay flow
- replay tests

### PR 8
- correlation and hypothesis engine improvements
- trust policy engine
- tuning profile model

---

## 16. Final Instruction to Claude

Execute this in disciplined phases.
Do not jump ahead to flashy features until the forensic substrate is real.
The build should feel like a serious investigation platform from the inside out.
