## Purpose

Brief description of what this PR does and why.

## Linked Issue

Closes #

## Sprint / Milestone

Sprint: <!-- 0, 1, 2, ... -->
Subsystem: <!-- forensics, parser, plugins, gui, api, canonical, replay, reporting, ci, docs -->

## Type of Change

- [ ] New feature
- [ ] Refactor / contract change
- [ ] Bug fix
- [ ] Documentation
- [ ] Infrastructure / CI
- [ ] Other: ___

## Scope

**In scope:**
- 

**Out of scope:**
- 

## Forensic Architecture Checklist

For PRs touching the forensic core — skip inapplicable items with N/A:

- [ ] Evidence is not mutated — original files preserved if ingest is involved
- [ ] New models serialize/deserialize correctly (JSON round-trip tested)
- [ ] Findings include evidence references where applicable
- [ ] Parser changes return `ParseDiagnostics` alongside `Flight`
- [ ] Plugin changes record `plugin_version` in findings
- [ ] Audit entries written for any case/evidence/analysis actions
- [ ] Uncertainty / missing data surfaced (not silently hidden)
- [ ] No logic path bypasses the case model (GUI calls same services as CLI)

## Testing Performed

- [ ] `pytest tests/ -q` passes locally
- [ ] `ruff check src/ tests/` passes
- [ ] `mypy src/goose` passes (or pre-existing errors noted)
- [ ] Tested with a real `.ulg` flight log
- [ ] New tests added for new behavior
- [ ] Edge cases covered (missing data, corruption, empty streams)

## Migration / Breaking Changes

- [ ] No breaking changes
- [ ] Breaking change — describe impact and migration path:

## Screenshots (GUI changes only)

## Docs Updated

- [ ] Relevant docs in `docs/` updated
- [ ] ADR created if this is a significant architectural decision
