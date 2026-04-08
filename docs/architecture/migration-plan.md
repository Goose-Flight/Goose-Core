---
title: Goose-Core Migration Plan
version: Sprint 3 (updated)
status: active
---

# Migration Plan: v1.3.4 → Forensic Architecture

This document defines how to migrate from the current v1.3.4 codebase to the
target forensic architecture without breaking the working product.

---

## Guiding Principles

1. **Additive first** — add new subsystems before removing old ones
2. **Compatibility shim** — keep `/api/analyze` working during Sprint 2 transition
3. **Tests gate every PR** — no sprint PR merges without passing CI
4. **Preserve charts** — cockpit.js is not touched until Sprint 6
5. **No big-bang refactors** — each sprint produces a deployable state

---

## Sprint 0 — COMPLETE (Governance)

- [x] Phase 0 architecture audit (`docs/architecture/audit.md`)
- [x] Target architecture doc (`docs/architecture/target-architecture.md`)
- [x] This migration plan
- [x] CI/CD pipelines (`.github/workflows/ci.yml`) -- ruff, mypy, pytest, bandit, pip-audit
- [ ] GitHub labels, milestones, and issues
- [ ] Updated PR and issue templates
- [ ] CODEOWNERS and contributing guide

**Output:** CI/CD pipeline and governance foundation shipped.

---

## Sprint 1 — COMPLETE (Case and Evidence Foundation)

**New module:** `src/goose/forensics/`

What was built:
- [x] `Case`, `EvidenceItem`, `EvidenceManifest`, `Provenance`, `AuditEntry` models
- [x] `CaseService` -- case directory management, evidence ingest, SHA-256/SHA-512 hashing
- [x] Immutable evidence storage (read-only after ingest)
- [x] Evidence manifest (JSON) per case
- [x] Append-only audit log (JSONL) per case
- [x] Case directory structure: `cases/CASE-YYYY-NNNNNN/{evidence/, manifests/, parsed/, analysis/, audit/, exports/}`
- [x] Tests for all of the above

**Output:** Forensic case foundation shipped.

---

## Sprint 2 — COMPLETE (Case-Oriented GUI and API)

**Refactored:** `src/goose/web/`

What was built:
- [x] Case-oriented API routes: `/api/cases` family
- [x] GUI: case list, case creation, evidence upload, findings view, audit trail view
- [x] Backward-compatible `/api/analyze` shim preserved
- [x] All chart code (`cockpit.js`) preserved

**Output:** Web GUI is now the primary product surface with case-oriented workflow.

---

## Sprint 3 — COMPLETE (Parser Contract Refactor)

**Refactored:** `src/goose/parsers/`

What was built:
- [x] `ParseResult` contract: `(Flight | None, ParseDiagnostics, Provenance)`
- [x] `ParseDiagnostics`: parser identity, format/parse confidence, stream coverage
  (20 streams), warnings, errors, corruption indicators, timebase anomalies,
  assumptions, parse timing
- [x] `diagnostics_version: "1.0"`, `confidence_scope: "parser_parse_quality"`
- [x] `Provenance`: full lineage record with `contract_version: "1.0"`
- [x] ULogParser adapted to return ParseResult with real diagnostics
- [x] Stub parsers: `implemented=False`, honest unsupported-format errors
- [x] Detection module: `parse_file()`, `detect_parser()`, `supported_formats()`
- [x] Parse diagnostics tab in GUI case workspace

**Output:** Parser framework with full diagnostic output shipped.

---

## Sprint 4 — IN PROGRESS (Extended Finding and Canonical Model)

**Extended:** `src/goose/core/finding.py` and new models

What is being built:
- `Finding` gains new optional fields: `finding_id`, `plugin_version`, `confidence`,
  `evidence_references`, `contradicting_metrics`, `assumptions`
- New models: `ForensicFinding`, `EvidenceReference`, `Hypothesis`, `SignalQuality`
- Evidence-linked findings and hypothesis generation
- All new fields are **optional with defaults** -- existing plugins emit valid
  Findings without changes

**Risk:** LOW -- additive only. Existing plugins continue to work.

---

## Sprint 5 — Plugin Contract and Trust Scaffolding

**Extended:** `src/goose/plugins/`

What changes:
- `Plugin.analyze()` return type evolves to `PluginResult`
- `Plugin` base gets new metadata fields: `plugin_id`, `category`, `author`,
  `required_streams`, `optional_streams`
- `PluginManifest` and `TrustState` models added
- All 11 built-in plugins converted to new contract

What is preserved:
- Plugin logic — only the interface wrapper changes

**Risk:** MEDIUM — all 11 plugins need updates. Tests must be updated.

---

## Sprint 6 — GUI Investigation Workspace

**Rebuilt:** `src/goose/web/static/`

What changes:
- `index.html` rebuilt around case-oriented workflow
- Case list, evidence view, parse diagnostics, plugin trust visible in GUI
- Chart workspace (`cockpit.js`) embedded within case workspace — preserved

What is preserved:
- All chart rendering logic
- SVG flight path renderer

**Risk:** HIGH — large frontend change. Mitigation: build new GUI pages
  alongside existing one; swap only when fully working.

---

## Sprint 7—11 — Progressive Enhancement

Remaining sprints are additive:
- Sprint 7: correlation + hypothesis engine
- Sprint 8: export bundle + replay
- Sprint 9: plugin trust policy + tuning profiles
- Sprint 10: format truthfulness + parser support matrix
- Sprint 11: portal alignment

Each sprint leaves the system deployable.

---

## Compatibility Shim Lifecycle

| Route | Sprint 0-1 | Sprint 2-3 (current) | Sprint 6+ |
|-------|-----------|---------|-----------|
| `POST /api/analyze` | Active | Shim (preserved for backward compat) | Deprecated |
| `POST /api/cases` | Missing | **Active** | Active |
| `GET /api/cases` | Missing | **Active** | Active |
| `POST /api/cases/{id}/evidence` | Missing | **Active** | Active |
| `POST /api/cases/{id}/analyze` | Missing | **Active** | Active |

The case-oriented API routes are the primary interface as of Sprint 2. The
`/api/analyze` shim is preserved for backward compatibility.
