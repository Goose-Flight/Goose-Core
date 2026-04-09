# Goose Core vs Hosted Portal — Architecture Boundary

Status: v1 — v11 Strategy Sprint
Owner: Josh / Goose Flight
Applies to: `Goose-Core` (this repo) and the hosted portal (future)

This document defines what belongs in **Goose Core** (the open-source local
forensic engine) versus what belongs in the **Goose Hosted Portal** (the paid
cloud product). It is the single source of truth for routing new features.

---

## 1. Decision Rule

> **If it affects forensic truth → Core.**
> **If it affects collaboration, billing, or cloud delivery → Hosted.**

Forensic truth = the parser output, findings, hypotheses, timeline, evidence
hashes, and the replayability of a case. Any change that could alter what a
case "says" about a flight must live in Core so that offline, air-gapped, and
hosted users get bit-identical results for the same input.

Everything else — accounts, sharing, fleet dashboards, billing, retention
policy enforcement — lives in Hosted. Core never imports anything from Hosted
and never calls out to the network on a forensic code path.

---

## 2. What Belongs in Goose Core

Core is a **local, offline-first, open-source Python package** with an
embedded FastAPI server. It owns everything required to ingest a log, produce
a forensic record, and export a replayable bundle.

### Core owns:

- **Parsers** — ULog/PX4, future DataFlash, future MAVLink, JSON, CSV.
- **Canonical flight model** — `CanonicalFlight`, samples, streams, provenance.
- **Case lifecycle** — `CaseService`, case directories, evidence intake with
  SHA-256/SHA-512 hashing, immutable evidence store.
- **Plugin contract & registry** — base plugin class, trust states, manifest,
  community-plugin loading, plugin diagnostics.
- **Findings & hypotheses engine** — deterministic rule evaluation, tuning
  profiles, hypothesis synthesis.
- **Timeline reconstruction** — `TimelineEvent`, analysis/timeline.json.
- **Forensic reports** — all 9 report objects in `forensics/reports.py`
  (MissionSummaryReport, AnomalyReport, CrashMishapReport, ForensicCaseReport,
  EvidenceManifestReport, QuickAnalysisSummary, ServiceRepairSummary,
  QAValidationReport, ReplayVerificationReport).
- **Case bundle format** — `exports/bundle_*.json`, replay verification.
- **Profile system** — data-driven `ProfileConfig`, `WordingPack`. No UI
  branching — profiles are pure data.
- **Feature gate scaffolding** — `FeatureGate`, `FEATURE_TIER_MATRIX`.
  Core ships in `OSS_CORE` mode; higher tiers flip a flag but never call
  remote services.
- **Local web UI** — static HTML/JS served from `/static/`, consuming the
  same API the hosted portal eventually proxies.
- **Audit log** — per-case append-only `audit.log` JSONL.

### Core must never contain:

- Remote authentication, sessions, JWT issuance, OAuth, or user accounts.
- Billing, Stripe, or license key validation.
- Calls to any outside service on a forensic code path (no telemetry, no
  "phone home", no remote inference).
- Multi-tenancy logic, organization hierarchy, team permissions.
- Cloud storage adapters (S3, GCS) — only local filesystem.
- Anything that would change a finding based on who is running the analysis.

---

## 3. What Belongs in the Hosted Portal

The hosted portal is a **separate repository and deployment** (e.g. on
Vercel). It wraps one or more Core engines and adds the cloud-only concerns.

### Hosted owns:

- **Accounts and orgs** — Clerk/Auth0/NextAuth user model, team membership,
  invitations.
- **Shared case library** — tenant-scoped case lists, sharing links, comment
  threads, review status.
- **Hosted storage** — S3/Blob-backed case directories with signed URLs,
  tenant isolation at storage level.
- **Collaboration** — real-time presence, comments on findings, @mentions.
- **Fleet trend views** — cross-case aggregation, fleet dashboards, recurring
  issue detection across platforms.
- **Billing** — Stripe subscriptions, plan enforcement, usage metering.
- **Retention controls** — configurable hold/purge lifecycles per tenant.
- **Enterprise deployment controls** — plugin allowlists enforced at the
  control plane, SSO, audit export, compliance reports.
- **Upload pipeline** — direct browser → hosted storage → queue → Core
  worker, without the operator running a local server.
- **Marketing surface** — landing site, docs, pricing, signup.

### Hosted must never:

- Fork or reimplement a parser, finding rule, or hypothesis.
- Change a canonical flight model in a way Core cannot read back.
- Bypass Core to compute findings on its own — hosted dispatches to Core,
  it never duplicates Core.

---

## 4. API Boundaries

Core exposes a stable HTTP API under `/api/*`. Hosted is a consumer of that
API — nothing more.

### Core API surfaces:

- `/api/cases/*` — case CRUD, evidence upload, analysis runs, timeline,
  findings, hypotheses, exports, reports.
- `/api/quick-analysis` — one-shot parse + plugin run without creating a case.
- `/api/plugins/*` — plugin inventory, diagnostics, trust state.
- `/api/profiles`, `/api/profiles/{id}` — profile registry.
- `/api/features` — current `FeatureGate` state including `FEATURE_TIER_MATRIX`.
- `/api/cases/{id}/exports/reports/*` — all report objects.
- `/api/cases/{id}/exports/bundle`, `/api/cases/{id}/exports/verify-replay`.

### Contract guarantees:

- **Versioned schemas** — every report object has `report_type` and
  `report_version`. Breaking shape changes bump the version.
- **Stable IDs** — `case_id`, `evidence_id`, `finding_id`, `hypothesis_id`,
  `run_id`, `bundle_id` are Core-assigned and opaque to Hosted.
- **Deterministic output** — given the same inputs, same engine version,
  same tuning profile, the same findings and hypotheses are produced.
- **Forward compatibility** — unknown fields in serialized models are ignored
  (`from_dict` filters to known field names).

### Hosted consumes Core via:

1. **Worker mode** — Hosted runs Core as a background worker, passing case
   directories on shared storage; Core writes artifacts, Hosted reads them.
2. **HTTP API** — Hosted proxies `/api/*` to a tenant-isolated Core instance.
3. **Bundle format** — Hosted can download a bundle from Core and re-ingest
   it elsewhere; the bundle is the canonical interchange format.

---

## 5. Shared Concepts — Must Not Diverge

Some concepts exist in both Core and Hosted and must stay in lockstep. These
live in Core and are re-exported (never redefined) by Hosted.

| Concept | Defined in | Consumed by |
|---|---|---|
| `EntitlementLevel` enum | `goose.features` | Hosted billing layer |
| `FEATURE_TIER_MATRIX` | `goose.features` | Hosted plan gating UI |
| `ProfileConfig` / `WordingPack` | `goose.forensics.profiles` | Hosted UI |
| Report object schemas | `goose.forensics.reports` | Hosted report viewer |
| `CanonicalFlight`, `TimelineEvent` | `goose.forensics.canonical` | Hosted chart layer |
| Case bundle format (`bundle_version`) | `goose.web.routes.exports` | Hosted import |
| `finding_id` / `hypothesis_id` format | Core plugins | Hosted permalink |

If Hosted needs a new field, it is added to Core first, shipped, then consumed
by Hosted. Hosted never patches Core's output after the fact.

---

## 6. Feature Tier Matrix Enforcement

The tier matrix in `src/goose/features.py::FEATURE_TIER_MATRIX` lives in Core
but is enforced at two layers:

- **Core (soft enforcement)** — `FeatureGate.is_enabled_for_level()` gates
  capability *visibility*. In `OSS_CORE` mode, Core still runs every plugin
  and produces every report — the feature gate only hides higher-tier
  entry points from the local UI. Forensic truth is never gated.
- **Hosted (hard enforcement)** — the hosted portal enforces billing plans,
  quota, and retention at its own layer before requests reach Core.

This preserves the rule that **forensic correctness is never a paid feature**.
OSS users on `OSS_CORE` get the same findings, hypotheses, and bundle format
as a hosted enterprise customer. What changes across tiers is the surrounding
workflow: batch analysis, hosted storage, sharing, compliance tooling.

---

## 7. Repo Layout Implications

```
Goose-Core/                 <- this repo, OSS, AGPL or similar
  src/goose/                <- forensic engine + local web UI
  tests/                    <- Core unit and integration tests
  docs/architecture/        <- this file
  docs/plugins/             <- plugin contract docs

Goose-Hosted/               <- separate repo, private
  apps/portal/              <- Next.js hosted UI
  apps/worker/              <- Core-as-worker dispatcher
  packages/sdk/             <- thin client for Core HTTP API
  packages/shared/          <- types mirrored from Core (generated)

Goose-Nest/                 <- marketing site, public
```

Core never imports from `Goose-Hosted`. Hosted only imports from Core via
its HTTP API or by running Core as a Python subprocess/worker.

---

## 8. Decision Log Template

When unsure where a new feature lands, answer these four questions:

1. Does this change what a finding or hypothesis says for the same input log?
   → **Core**.
2. Does this require remote storage, accounts, or network calls?
   → **Hosted**.
3. Is this pure presentation (chart layout, color scheme, layout)?
   → Core local UI for the OSS build; Hosted portal UI for the cloud build.
   Data-driven via `ProfileConfig` if it needs to vary by user class.
4. Does this enforce a paid-plan limit?
   → **Hosted**. Core only knows the matrix; Core does not enforce billing.

If two of the answers point to Core, it lives in Core. If any answer points
to Hosted, the user-visible feature lives in Hosted but may require a Core
change first to expose the data it needs.
