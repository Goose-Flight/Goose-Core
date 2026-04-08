---
title: Goose-Core Migration Plan
version: Sprint 0
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

## Sprint 0 — Current Sprint (Governance)

Work done in Sprint 0 does NOT touch analysis code. It covers:

- [x] Phase 0 architecture audit (`docs/architecture/audit.md`)
- [x] Target architecture doc (`docs/architecture/target-architecture.md`)
- [x] This migration plan
- [ ] CI/CD pipelines (`.github/workflows/ci.yml`)
- [ ] GitHub labels, milestones, and issues
- [ ] Updated PR and issue templates
- [ ] CODEOWNERS and contributing guide

**Output:** Clean governance foundation. No code changes to analysis engine.

---

## Sprint 1 — Case and Evidence Foundation

**New module:** `src/goose/forensics/`

What gets added:
- `Case`, `EvidenceItem`, `EvidenceManifest`, `Provenance`, `AuditEntry` models
- `CaseService` — case directory management, evidence ingest, hashing
- Tests for all of the above

What does NOT change:
- `core/flight.py`, `core/finding.py`, `plugins/`, `parsers/`, `web/` — untouched

**Risk:** LOW — purely additive. Existing tests unaffected.

---

## Sprint 2 — Case-Oriented GUI and API

**Refactored:** `src/goose/web/`

What changes:
- New case-oriented API routes: `POST /api/cases`, `POST /api/cases/{id}/evidence`,
  `POST /api/cases/{id}/analyze`
- GUI gains: case create screen, case list, evidence view
- `/api/analyze` becomes a **compatibility shim** that creates a case internally
  and returns the same response shape as today

What is preserved:
- Existing `/api/analyze` response shape (so frontend still works during transition)
- All chart code (`cockpit.js`) — unchanged

**Risk:** MEDIUM — API refactor. Shim must be solid.

---

## Sprint 3 — Parser Contract Refactor

**Refactored:** `src/goose/parsers/`

What changes:
- `BaseParser.parse()` returns `ParseResult` (Flight + ParseDiagnostics + Provenance)
- ULog parser wrapped to return `ParseResult`
- `ParseDiagnostics` model added
- DataFlash/TLog/CSV stubs get `DISABLED` flag — `can_parse()` returns False
  (or they are removed from entry-point registration)

What is preserved:
- `Flight` model unchanged (same data, just now embedded in `ParseResult`)
- All plugins — they still receive `Flight`, not `ParseResult`

**Risk:** HIGH — parser contract change cascades to web API and CLI.
  Mitigation: update `_try_all_parsers()` in `web/app.py` to unwrap `ParseResult`.

---

## Sprint 4 — Extended Finding and Canonical Model

**Extended:** `src/goose/core/finding.py` and new models

What changes:
- `Finding` gets new optional fields: `finding_id`, `plugin_version`, `confidence`,
  `evidence_references`, `contradicting_metrics`, `assumptions`
- New models: `EvidenceReference`, `Hypothesis`, `SignalQuality`
- All new fields are **optional with defaults** — existing plugins emit valid
  Findings without changes

**Risk:** LOW — additive only. Existing plugins continue to work.

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

| Route | Sprint 0-1 | Sprint 2 | Sprint 6+ |
|-------|-----------|---------|-----------|
| `POST /api/analyze` | Active (current) | Shim (creates case internally) | Deprecated |
| `POST /api/cases` | Missing | Active | Active |
| `GET /api/cases` | Missing | Active | Active |
| `POST /api/cases/{id}/evidence` | Missing | Active | Active |
| `POST /api/cases/{id}/analyze` | Missing | Active | Active |

The shim in Sprint 2 ensures the existing single-page GUI continues to work
while the new case-oriented GUI is built in Sprint 6.
