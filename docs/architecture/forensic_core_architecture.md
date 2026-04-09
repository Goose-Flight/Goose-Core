# Forensic Core Architecture

Goose is a local-first, case-oriented, evidence-preserving, plugin-driven flight forensic and investigation platform. This document describes the current shape of the forensic core.

## Entry Paths

There are three primary entry paths into the forensic engine:

1. **Quick Analysis** (`POST /api/quick-analysis`) — session-only triage. A file is uploaded, parsed, and analyzed in memory. Results are returned immediately. Nothing is persisted to disk. The user may promote the result to a full Investigation Case with one click.

2. **Investigation Case** (`POST /api/cases` + `POST /api/cases/{id}/analyze`) — case-oriented workflow. Evidence is ingested with SHA-256/SHA-512 hashing into an immutable case directory. Analysis runs are recorded, findings and hypotheses are persisted per-run, and the full audit trail is maintained. Multiple analysis runs can be diffed and replayed.

3. **Open Recent Case** (`GET /api/cases` or `GET /api/runs/recent`) — reopens a previously created case from disk. All prior artifacts are available for review, re-analysis, or export.

## Analysis Flow

```
Log File (.ulg)
     |
     v
  [ Parser Framework ]  (src/goose/parsers/)
     |-- detect_parser() → ULogParser | DataFlashParser (stub) | TLogParser (stub) | CSVParser (stub)
     |-- parse() → ParseResult(Flight, ParseDiagnostics, Provenance)
     |
     v
  [ Flight Model ]  (src/goose/core/flight.py)
     |-- position, battery, motors, attitude, vibration, gps, ekf, rc_input, velocity
     |-- mode_changes, events, phases, metadata
     |
     v
  [ Plugin Engine ]  (src/goose/plugins/)
     |-- PLUGIN_REGISTRY (17 built-in analyzers)
     |-- Plugin.forensic_analyze(flight, evidence_id, run_id, config, diagnostics, tuning_profile)
     |-- Returns (list[ForensicFinding], PluginDiagnostics)
     |
     v
  [ Lifting Layer ]  (src/goose/forensics/lifting.py)
     |-- lift_findings() → ForensicFinding with EvidenceReference
     |-- generate_hypotheses() → list[Hypothesis]
     |-- build_signal_quality() → list[SignalQuality]
     |
     v
  [ Canonical Models ]  (src/goose/forensics/canonical.py)
     |-- ForensicFinding, EvidenceReference, Hypothesis, SignalQuality
     |-- Serializable, evidence-anchored, confidence-scoped
     |
     v
  [ Case System ]  (src/goose/forensics/case_service.py)
     |-- Persists findings_{run_id}.json, hypotheses_{run_id}.json, timeline.json
     |-- Appends to audit_log.jsonl (append-only)
     |-- Records AnalysisRun in case.json
```

## Key Invariants

- **Parser confidence ≠ finding confidence ≠ hypothesis confidence.** Each is scoped explicitly. `ParseDiagnostics.confidence_scope = "parser_parse_quality"`, `ForensicFinding.confidence_scope = "finding_analysis"`, `Hypothesis.confidence_scope = "hypothesis_root_cause"`. Conflating these corrupts forensic reasoning.
- **Every ForensicFinding must have at least one EvidenceReference.** Findings without evidence anchors are not forensically valid.
- **Facts, findings, and hypotheses are distinct types.** A hypothesis references finding_ids — it never embeds or replaces findings. Parser output is facts; plugin output is findings; the lifting layer produces hypotheses.
- **Profiles never change forensic truth.** They bias plugin ordering, chart presets, report wording, and visible fields. The same canonical model is produced regardless of profile.
- **Audit trail is append-only.** `audit_log.jsonl` is never truncated or rewritten.

## Thin-Finding Bridge

Plugins currently extend `goose.plugins.base.Plugin` and implement `analyze(flight, config) -> list[Finding]`. The `forensic_analyze()` method in `base.py` calls `analyze()` and converts thin `Finding` objects to `ForensicFinding` in-place using the plugin's `manifest.primary_stream` for evidence reference construction. This bridge exists to let the 12 plugins keep their existing analysis logic while emitting forensic-grade output. See `base.py` for the bridge comment.

## Profile System

See `profile_system.md` for full profile architecture.

## Run-Scoped Artifacts

See `run_artifact_model.md` for the run-scoped file convention.
