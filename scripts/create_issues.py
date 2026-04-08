"""Script to create Sprint 0-2 GitHub issues for the Goose-Core NEW MISSION."""

import json
import subprocess


def get_pat():
    result = subprocess.run(
        ["bash", "-c", "cat ~/.git-credentials-goose | sed 's|https://goose-flight:||' | sed 's|@github.com||'"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def create_issue(pat, title, body, labels, milestone):
    payload = json.dumps({"title": title, "body": body, "labels": labels, "milestone": milestone})
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: Bearer {pat}",
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        "https://api.github.com/repos/Goose-Flight/Goose-Core/issues",
        "-d", payload
    ], capture_output=True, text=True)
    d = json.loads(result.stdout)
    num = d.get("number", "ERR")
    url = d.get("html_url", "")
    err = d.get("message", "")
    status = f"  #{num}: {title}"
    if err:
        status += f" [ERROR: {err}]"
    else:
        status += f"\n    {url}"
    print(status)
    return num


def main():
    pat = get_pat()

    # ── Sprint 0 (milestone 1) ────────────────────────────────────────────
    print("\n=== Sprint 0: Audit & Stabilization ===")

    create_issue(
        pat,
        "Set up CI/CD pipeline (lint, typecheck, tests, coverage, security)",
        (
            "## Objective\n"
            "Set up GitHub Actions CI pipeline so every PR is gated by automated checks.\n\n"
            "## Scope\n"
            "- Ruff linting + format check\n"
            "- Mypy type checking\n"
            "- Pytest with coverage (Python 3.10, 3.11, 3.12 matrix)\n"
            "- Bandit security scan\n"
            "- pip-audit dependency check\n\n"
            "## Acceptance Criteria\n"
            "- [ ] `.github/workflows/ci.yml` runs on push/PR to main\n"
            "- [ ] Ruff check passes on `src/` and `tests/`\n"
            "- [ ] Mypy runs without errors\n"
            "- [ ] All existing tests pass in CI\n"
            "- [ ] Coverage report is generated"
        ),
        ["area:ci", "type:infra", "priority:p0", "sprint:0"],
        1,
    )

    create_issue(
        pat,
        "Write Sprint 0 architecture audit and gap analysis docs",
        (
            "## Objective\n"
            "Document the current Goose-Core architecture vs the NEW MISSION spec.\n\n"
            "## Scope\n"
            "- `docs/architecture/audit.md` — current state audit\n"
            "- `docs/architecture/target-architecture.md` — target architecture\n"
            "- `docs/architecture/migration-plan.md` — migration strategy\n"
            "- `docs/adr/README.md` — ADR index and template\n\n"
            "## Acceptance Criteria\n"
            "- [ ] audit.md covers all 10 subsystems\n"
            "- [ ] Gap analysis identifies all missing models\n"
            "- [ ] Migration plan defines compatibility shim strategy\n"
            "- [ ] Target architecture defines new module map"
        ),
        ["area:docs", "type:docs", "priority:p0", "sprint:0"],
        1,
    )

    create_issue(
        pat,
        "Create GitHub label taxonomy, milestones, and issue templates",
        (
            "## Objective\n"
            "Set up GitHub labels, milestones, and issue templates for all Sprint work.\n\n"
            "## Scope\n"
            "- area:* labels (forensics, gui, plugins, parser, api, ci, docs, security, replay, reporting, canonical)\n"
            "- type:* labels (feature, refactor, bug, docs, infra)\n"
            "- priority:* labels (p0, p1, p2)\n"
            "- risk:* and sprint:* labels\n"
            "- Milestones for Sprints 0-11\n"
            "- Updated PR template with forensic architecture checklist\n"
            "- Feature, bug, and ADR issue templates\n\n"
            "## Acceptance Criteria\n"
            "- [ ] All label groups created\n"
            "- [ ] Milestones 0-11 created\n"
            "- [ ] PR template updated\n"
            "- [ ] Issue templates updated"
        ),
        ["area:ci", "type:infra", "priority:p0", "sprint:0"],
        1,
    )

    create_issue(
        pat,
        "Set up branch protection and contributing guide",
        (
            "## Objective\n"
            "Establish engineering hygiene so all Sprint work is done consistently.\n\n"
            "## Scope\n"
            "- Branch protection on main (require PR + CI passing)\n"
            "- CONTRIBUTING.md with forensic architecture rules and definition of done\n"
            "- CODEOWNERS file\n\n"
            "## Acceptance Criteria\n"
            "- [ ] main branch requires passing CI before merge\n"
            "- [ ] CONTRIBUTING.md covers setup, forensic rules, definition of done\n"
            "- [ ] CODEOWNERS covers core modules"
        ),
        ["area:ci", "area:docs", "type:infra", "priority:p1", "sprint:0"],
        1,
    )

    # ── Sprint 1 (milestone 2) ────────────────────────────────────────────
    print("\n=== Sprint 1: Case & Evidence Foundation ===")

    create_issue(
        pat,
        "Implement forensic case models: Case, EvidenceItem, EvidenceManifest, Provenance, AuditEntry",
        (
            "## Objective\n"
            "Create the foundational data models for the forensic case system in a new `src/goose/forensics/` module.\n\n"
            "## Models\n"
            "- `Case` — case_id, created_at, status, tags, notes, engine_version, analysis_runs[], evidence_items[], exports[]\n"
            "- `EvidenceItem` — evidence_id, filename, size_bytes, sha256, sha512, stored_path, acquired_at, immutable flag\n"
            "- `EvidenceManifest` — manifest_version, case_id, evidence list, hash info, acquisition metadata\n"
            "- `Provenance` — source evidence ID, parser name/version, transformation chain, timestamps\n"
            "- `AuditEntry` — event_id, timestamp, actor, action_type, object_type, object_id, details, success\n\n"
            "## Acceptance Criteria\n"
            "- [ ] All models are typed dataclasses\n"
            "- [ ] JSON round-trip serialization tested\n"
            "- [ ] No circular imports with existing `core/` modules\n"
            "- [ ] `tests/test_forensics/test_models.py` added\n\n"
            "## Out of Scope\n"
            "Storage service (separate issue). GUI (Sprint 2).\n\n"
            "## Risk: HIGH\n"
            "Foundational — all other forensic subsystems depend on these models."
        ),
        ["area:forensics", "type:feature", "priority:p0", "sprint:1", "risk:high"],
        2,
    )

    create_issue(
        pat,
        "Implement CaseService: case directory management, immutable evidence ingest, hashing, audit trail",
        (
            "## Objective\n"
            "Implement `src/goose/forensics/case_service.py` — the service that manages case directories "
            "and handles immutable evidence ingest with SHA-256/SHA-512 hashing.\n\n"
            "## API\n"
            "- `CaseService.create_case(created_by, tags, notes)` -> Case\n"
            "- `CaseService.ingest_evidence(case_id, filepath)` -> EvidenceItem\n"
            "  - copies file to `cases/CASE-ID/evidence/` (read-only)\n"
            "  - computes SHA-256 + SHA-512\n"
            "  - writes EvidenceManifest\n"
            "  - appends AuditEntry to `audit/audit_log.jsonl`\n"
            "- `CaseService.get_case(case_id)` -> Case\n"
            "- `CaseService.list_cases()` -> list[Case]\n\n"
            "## Case Directory Structure\n"
            "```\n"
            "cases/CASE-2026-000001/\n"
            "  case.json\n"
            "  evidence/EV-0001-flight.ulg  (read-only)\n"
            "  manifests/evidence_manifest.json\n"
            "  parsed/\n"
            "  analysis/\n"
            "  audit/audit_log.jsonl  (append-only)\n"
            "  exports/\n"
            "```\n\n"
            "## Acceptance Criteria\n"
            "- [ ] Evidence is copied immutably (original not modified)\n"
            "- [ ] Stored copy is read-only\n"
            "- [ ] SHA-256 in manifest\n"
            "- [ ] AuditEntry written on ingest\n"
            "- [ ] Case persists across restarts\n"
            "- [ ] `tests/test_forensics/test_case_service.py` with immutability + hash + persistence tests\n\n"
            "## Dependencies\n"
            "Forensic case models issue must be merged first."
        ),
        ["area:forensics", "type:feature", "priority:p0", "sprint:1", "risk:high"],
        2,
    )

    # ── Sprint 2 (milestone 3) ────────────────────────────────────────────
    print("\n=== Sprint 2: GUI/API Case Workflow ===")

    create_issue(
        pat,
        "Add case-oriented API routes: POST /api/cases, evidence ingest, case analysis",
        (
            "## Objective\n"
            "Add case-based API routes to `src/goose/web/` so the GUI drives the forensic case workflow. "
            "Keep `/api/analyze` working as a compatibility shim.\n\n"
            "## New Routes\n"
            "- `POST /api/cases` — create case\n"
            "- `GET /api/cases` — list cases\n"
            "- `GET /api/cases/{case_id}` — get case detail\n"
            "- `POST /api/cases/{case_id}/evidence` — ingest evidence (uses CaseService)\n"
            "- `GET /api/cases/{case_id}/evidence` — list evidence\n"
            "- `POST /api/cases/{case_id}/analyze` — run analysis\n"
            "- `GET /api/cases/{case_id}/findings` — get findings\n\n"
            "## Compatibility Shim\n"
            "`POST /api/analyze` must continue to work — creates a case internally, returns same response shape.\n\n"
            "## Acceptance Criteria\n"
            "- [ ] All routes return correct status codes\n"
            "- [ ] `/api/analyze` shim still works (existing frontend unbroken)\n"
            "- [ ] Evidence ingest uses CaseService (immutable + hashed)\n"
            "- [ ] Analysis runs against case evidence, not a temp file\n"
            "- [ ] `tests/test_web/test_case_api.py` added\n\n"
            "## Dependencies\n"
            "CaseService must be merged first."
        ),
        ["area:api", "area:forensics", "type:feature", "priority:p0", "sprint:2", "risk:medium"],
        3,
    )

    create_issue(
        pat,
        "Add case workflow to GUI: case list, create case, evidence upload with hash display",
        (
            "## Objective\n"
            "Add minimum GUI surfaces for case-based workflow while preserving existing charts, findings, and timeline.\n\n"
            "## Scope\n"
            "Changes to `src/goose/web/static/index.html`:\n"
            "- Dashboard / case list view\n"
            "- Case creation form\n"
            "- Evidence upload tied to a case\n"
            "- Evidence integrity display (SHA-256, file size, acquisition time)\n"
            "- Analyze button within case context\n\n"
            "## Acceptance Criteria\n"
            "- [ ] User can create a case from the GUI\n"
            "- [ ] User can upload evidence into a case\n"
            "- [ ] GUI shows evidence SHA-256 and metadata\n"
            "- [ ] User can trigger analysis from within a case\n"
            "- [ ] Existing charts, findings, and timeline still work\n\n"
            "## Out of Scope\n"
            "Parse diagnostics view (Sprint 6). Plugin trust display (Sprint 5). Full case workspace (Sprint 6).\n\n"
            "## Dependencies\n"
            "Case API routes must be merged first."
        ),
        ["area:gui", "type:feature", "priority:p1", "sprint:2", "risk:medium"],
        3,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
