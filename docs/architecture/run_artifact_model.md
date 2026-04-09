# Run Artifact Model

Every analysis run produces a set of run-scoped artifacts in the case's `analysis/` directory. This document describes the artifact convention.

## Convention

Since Convergence Sprint 1, every run writes both:

1. A **run-specific archive**: `findings_{run_id}.json`, `hypotheses_{run_id}.json` — never overwritten after creation.
2. A **latest-run pointer**: `findings.json`, `hypotheses.json` — overwritten on each run for UI convenience.

This dual-file approach enables multi-run diff (`compare_runs()`) and replay (`execute_replay()`) while keeping the UI simple.

## Files per Run

```
analysis/
  findings.json               # Latest-run pointer (overwritten each run)
  findings_{run_id}.json      # Run-specific archive (append-only after write)
  hypotheses.json             # Latest-run pointer
  hypotheses_{run_id}.json    # Run-specific archive
  timeline.json               # Latest run timeline (overwritten)
  signal_quality.json         # Per-stream quality report for the latest run
  plugin_diagnostics.json     # Per-plugin execution records for the latest run
  tuning_profile.json         # Tuning thresholds used for the latest run
```

## Loading Semantics

`diff.py:_load_run_findings(analysis_dir, run_id)`:
1. Tries `findings_{run_id}.json` first.
2. Falls back to `findings.json` **only** when the bundle's `run_id` field matches the requested run_id.
3. Returns `[]` if neither succeeds.

This means old cases (pre-CS-1) can still be compared, but only their latest run is accessible for diff.

## Bundle Format

Each artifact file is a JSON bundle with the structure:

```json
{
  "findings_version": "2.0",
  "run_id": "RUN-XXXXXXXX",
  "evidence_id": "EV-0001",
  "generated_at": "2026-04-09T...",
  "findings": [...]
}
```

The `run_id` field in the bundle matches the `run_id` in `case.json`'s `analysis_runs[]` list, creating a navigable link from case metadata to run artifacts.

## Replay

`replay.py:execute_replay()` re-runs parsing and analysis against the same evidence file, producing a new run with a new `run_id`. The `ReplayVerificationRecord` captures version diffs (engine, parser, plugins, tuning profile) and finding diffs (added, removed, changed). Replay records are written to `exports/replay_{replay_id}.json`.

## Run Diff

`diff.py:compare_runs()` compares two runs within the same case using run-scoped artifact files. It produces a `RunComparison` with structured `FindingDifference`, `HypothesisDifference`, and `PluginExecutionDifference` records.
