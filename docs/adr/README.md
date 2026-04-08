# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for Goose-Core.

An ADR captures a significant architectural decision: what was decided, why,
what alternatives were considered, and what the consequences are.

ADRs are immutable once accepted. If a decision changes, create a new ADR that
supersedes the old one.

## Index

| # | Title | Status | Date |
|---|-------|--------|------|
| [ADR-0001](0001-forensic-case-model.md) | Adopt forensic case model as primary architecture | Accepted | 2026-04-07 |
| [ADR-0002](0002-local-first-case-storage.md) | Use local filesystem for case storage (Sprint 1) | Accepted | 2026-04-07 |
| [ADR-0003](0003-parser-contract-change.md) | Parser contract returns ParseResult not Flight | Accepted | 2026-04-07 |
| [ADR-0004](0004-temp-file-compat-shim.md) | Keep /api/analyze as compatibility shim during Sprint 2 | Accepted | 2026-04-07 |

## Status Values

- **Proposed** — under discussion
- **Accepted** — decision made, implementation pending or in progress
- **Superseded** — replaced by a later ADR (link to new one)
- **Deprecated** — no longer applicable

## Template

Use `adr-template.md` when creating a new ADR.
