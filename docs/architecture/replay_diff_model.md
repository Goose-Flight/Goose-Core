# Replay and Run Diff Model

## Purpose

Replay and run diff are the reproducibility and audit mechanisms for the forensic engine. They answer two questions:

- **Replay**: "If I re-run analysis on this evidence with the current engine, do I get the same findings?"
- **Run diff**: "How do two analysis runs on the same case differ?"

## Replay (`replay.py`)

`execute_replay(case_id, source_run_id, case_dir)`:
1. Loads the source run from `case.json`.
2. Re-runs `parse_file()` on the original evidence.
3. Re-runs all plugins via `forensic_analyze()`.
4. Computes a `ReplayDifferenceSummary` (findings added/removed/changed, hypothesis counts, version drift).
5. Classifies the result:
   - `EXACT_MATCH` — no version drift, no output drift
   - `EXPECTED_DRIFT` — version drift detected (engine/parser/plugin versions changed) → output drift is expected
   - `UNEXPECTED_DRIFT` — no version drift but outputs differ → investigate
6. Writes a `ReplayVerificationRecord` to `exports/replay_{replay_id}.json`.
7. Records the replay in the audit log.

The `set(drift_cats)` conversion in the drift classification logic (line 438) was added in Convergence Sprint 1 to fix a `TypeError` when `drift_cats` was a list.

## Run Diff (`diff.py`)

`compare_runs(case_dir, run_a_id, run_b_id)`:
1. Loads `findings_{run_a_id}.json` and `findings_{run_b_id}.json` (falls back to `findings.json` with run_id match check).
2. Loads `hypotheses_{run_a_id}.json` and `hypotheses_{run_b_id}.json`.
3. Computes `FindingDifference`, `HypothesisDifference`, `PluginExecutionDifference`.
4. Returns a `RunComparison` with structured diff output.

Run diff is designed for comparing two runs within the same case (e.g., before and after re-tuning). For cross-case comparison, use replay.

## Evidence Reference Integrity

Neither replay nor run diff re-hash evidence files. The `EvidenceItem.sha256` and `sha512` fields in `case.json` serve as the integrity reference. Any tooling that wants to verify evidence integrity should check the stored hash against the file at `ev.stored_path`.

## Version Drift Categories

`DriftCategory` enum (in `replay.py`):
- `ENGINE_VERSION` — goose package version changed
- `PARSER_VERSION` — parser version changed
- `PLUGIN_VERSION` — any plugin version changed
- `TUNING_PROFILE` — tuning profile ID changed
- `SCHEMA_VERSION` — schema version changed (rare)
- `EVIDENCE_MISSING` — evidence file no longer accessible
- `FINDINGS_CHANGED` — output findings differ
- `CONFIDENCE_SHIFTED` — hypothesis confidence changed
