# Version Locations — Single Source of Truth

Current version: **1.3.4** (defined in `pyproject.toml`)

## Every place version must be updated on a version bump

| File | Line | Context | Status |
|------|------|---------|--------|
| `pyproject.toml` | 7 | `version = "1.3.4"` | ✅ correct |
| `src/goose/__init__.py` | 3 | `__version__ = "1.3.4"` | ✅ correct |
| `src/goose/web/static/index.html` | 1715 | `<span class="version-badge">v1.3.4</span>` | ✅ correct |
| `src/goose/web/static/index.html` | 2428 | `<span>GOOSE v1.3.4</span>` | ✅ correct |
| `src/goose/web/app.py` | 113 | `version=_goose_pkg.__version__` | ✅ correct (dynamic — reads from `__init__.py`) |
| `src/goose/reports/json_report.py` | 56 | `"goose_version": goose.__version__` | ✅ correct (dynamic — reads from `__init__.py`) |
| `docs/api-reference.md` | 59 | `"version": "1.3.4"` | ✅ correct (fixed) |
| `docs/api-reference.md` | 72 | `# {'status': 'ok', 'version': '1.3.4'}` | ✅ correct (fixed) |
| `docs/getting-started.md` | 81 | `🪿 Goose v1.3.4 — Crash Analysis` | ✅ correct (fixed) |
| `src/goose/forensics/replay.py` | 240 | `engine_version: str = "1.3.4"` | ✅ correct |
| `src/goose/validation/harness.py` | 209 | `engine_version: str = "1.3.4"` | ✅ correct |
| `docs/architecture/audit.md` | 18 | `Goose-Core v1.3.4 is a functional flight analysis engine` | ✅ correct (architecture doc describing current state) |
| `docs/architecture/migration-plan.md` | 7, 9 | `Migration Plan: v1.3.4 → Forensic Architecture` | ✅ correct (architecture planning doc) |

## Version strings that are intentionally NOT 1.3.4

The following use `"1.0.0"` or other values that are **not** the engine version and should NOT be updated on a version bump:

| File | Context | Why it stays at "1.0.0" |
|------|---------|--------------------------|
| `src/goose/plugins/*.py` (all plugins) | `version = "1.0.0"` in each plugin class | Each plugin has its own independent semantic version |
| `src/goose/parsers/csv_parser.py` | `VERSION = "1.0.0"` | Parser-level version, independent of engine |
| `src/goose/parsers/dataflash.py` | `PARSER_VERSION = "1.0.0"` | Parser-level version, independent of engine |
| `src/goose/forensics/models.py` | `tuning_profile_version: str = "1.0.0"` | Tuning profile schema version, independent |
| `src/goose/forensics/reports.py` | `"tuning_profile_version": "1.0.0"` | Tuning profile schema version, independent |
| `src/goose/forensics/tuning.py` | `version="1.0.0"` | Tuning profile schema version, independent |
| `src/goose/validation/harness.py` | `tuning_profile_version: str = "1.0.0"` | Tuning profile schema version, independent |
| `docs/developer/adding_a_plugin.md` | `version = "1.0.0"` | Example plugin starter code — intentional |
| `docs/developer/adding_a_parser.md` | `VERSION = "1.0.0"` | Example parser starter code — intentional |
| `docs/developer/building_pro_extensions.md` | `version = "1.0.0"` | Example extension starter code — intentional |
| `src/goose/web/static/index.html` | `plugin.version \|\| '1.0.0'` | Default fallback for unversioned plugins in UI |
| `src/goose/web/static/index.html` | `Tuning Profile: default v1.0.0` | Tuning profile display version, independent |
| `tests/**` | Various `"1.0.0"` in test fixtures | Test data for plugin/parser/tuning versions — intentional |
| `docs/developer/building_pro_extensions.md` | `"goose-flight>=1.3.0"` | Minimum compatible Core version in example extension — intentional |

## Inconsistencies found and fixed

| File | Issue | Fix Applied |
|------|-------|-------------|
| `src/goose/reports/json_report.py` | `"goose_version": "1.0.0"` — engine version hardcoded to 1.0.0 in generated report output | Changed to `goose.__version__` (dynamic) |
| `src/goose/web/app.py` | `version="1.0.0"` — FastAPI OpenAPI version was stale | Changed to `_goose_pkg.__version__` (dynamic) |
| `docs/api-reference.md` | Example `/api/health` response showed `"version": "1.0.0"` | Updated to `"1.3.4"` |
| `docs/getting-started.md` | CLI example output showed `Goose v1.0.0` | Updated to `v1.3.4` |

## Fix on every version bump

1. Update `pyproject.toml` `version = "X.Y.Z"` — this is the canonical source
2. Update `src/goose/__init__.py` `__version__ = "X.Y.Z"` — runtime source
3. Update `src/goose/web/static/index.html` — two UI badge occurrences (lines 1715, 2428)
4. Update `src/goose/forensics/replay.py` default arg `engine_version: str = "X.Y.Z"`
5. Update `src/goose/validation/harness.py` default arg `engine_version: str = "X.Y.Z"`
6. Update `docs/api-reference.md` example response version value
7. Update `docs/getting-started.md` CLI example version label

**Do NOT update** `docs/architecture/*.md` version references unless the docs are being revised to describe a different version baseline.

Run to find all hits after bumping:
```bash
grep -rn "1\.3\.4" . --include="*.md" --include="*.toml" --include="*.py" --include="*.html" --include="*.yml"
```
Replace `1\.3\.4` with the old version you are bumping from.
