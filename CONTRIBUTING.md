# Contributing to Goose-Core

Goose-Core is being built into a top-tier open-source flight forensic platform.
All contributions must respect the forensic architecture principles in `docs/architecture/`.

---

## Development Setup

```bash
# Clone and install in editable mode with dev deps
git clone https://github.com/Goose-Flight/Goose-Core.git
cd Goose-Core
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify setup:
```bash
pytest tests/ -q         # Should pass all tests
ruff check src/ tests/   # Should report no issues
mypy src/goose           # Should pass
```

---

## Running the Local Server

```bash
python -m uvicorn goose.web.app:app --host 0.0.0.0 --port 8001 --reload
```

Open `http://localhost:8001` in your browser.

---

## Project Architecture

Before contributing, read:
- `docs/architecture/audit.md` — current state baseline
- `docs/architecture/target-architecture.md` — where we're going
- `docs/architecture/migration-plan.md` — how we get there

The core principle: **Goose is a case-oriented, evidence-preserving, replayable
forensic platform**. Every significant feature must respect this.

---

## Branch Naming

```
feat/<short-description>       # New feature
fix/<short-description>        # Bug fix
refactor/<short-description>   # Refactoring
docs/<short-description>       # Documentation
ci/<short-description>         # CI/CD changes
sprint<N>/<short-description>  # Sprint-scoped work
```

Examples:
- `feat/case-evidence-models`
- `sprint1/case-service`
- `fix/ulog-parser-crash`

---

## Commit Style

Follow conventional commits:

```
feat: add Case and EvidenceItem models
fix: handle missing timestamp in ULog parser
refactor: wrap ULog parser in ParseResult contract
docs: add Sprint 0 architecture audit
ci: add GitHub Actions CI pipeline
test: add immutability tests for CaseService
```

---

## Definition of Done

A feature is done when:

- [ ] Code is written and linted (`ruff check` passes)
- [ ] Type annotations are correct (`mypy` passes)
- [ ] Tests cover the new behavior (including edge cases)
- [ ] CI passes on the PR branch
- [ ] Relevant docs are updated
- [ ] PR template is filled out completely
- [ ] No forensic architecture rules are violated (see PR template checklist)

---

## Forensic Architecture Rules (Non-Negotiable)

1. **Evidence integrity** — original evidence must not be mutated
2. **Findings must cite evidence** — no finding without an evidence basis
3. **No bypasses** — GUI, CLI, and portal must call the same core services
4. **Parser honesty** — unsupported formats must fail clearly, not silently
5. **Explicit uncertainty** — missing data and parser warnings must be surfaced
6. **No LLMs in evidentiary core** — LLMs may summarize but not decide forensic truth
7. **Deterministic analysis** — same input + same plugin version = same output

---

## Writing Plugins

Quick summary:
- Plugins receive canonical `Flight` data (not raw log bytes)
- Plugins must declare a `PluginManifest` (id, version, category, required streams)
- Plugins must return `PluginResult` (findings, diagnostics, confidence notes)
- Findings must include `evidence_references` where possible
- Plugins must fail gracefully with diagnostics if required data is missing

See `docs/plugins/` for the full plugin development guide.

---

## Questions?

Open a GitHub issue with the `type:docs` label if something is unclear.
