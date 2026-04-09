# Getting Started — Developer Guide

## Prerequisites

- Python 3.10, 3.11, or 3.12
- `pyulog` for PX4 ULog parsing
- `numpy`, `pandas`, `fastapi`, `uvicorn` (see `pyproject.toml`)

## Install for Development

```bash
git clone https://github.com/Goose-Flight/Goose-Core.git
cd Goose-Core
pip install -e ".[dev]"
```

This installs in editable mode with test and lint dependencies.

## Running Locally

```bash
# Launch the web GUI (primary interface)
goose serve

# Or directly with uvicorn for development
uvicorn goose.web.app:app --reload --port 8000
```

The server starts at `http://localhost:8000`. The web GUI is the primary interface. The API is available at the same port.

## What the Endpoints Do

| Endpoint | Role |
|----------|------|
| `POST /api/quick-analysis` | Session-only analysis — no disk writes |
| `GET /api/cases` | List all cases from the cases/ directory |
| `POST /api/cases` | Create a new case (writes case.json + directory structure) |
| `POST /api/cases/{id}/evidence` | Ingest a file — hashes it, copies to `evidence/`, writes manifest |
| `POST /api/cases/{id}/analyze` | Run the parser + all plugins, persist artifacts |
| `GET /api/cases/{id}` | Fetch case metadata + analysis run history |
| `POST /api/cases/{id}/exports/bundle` | Create a replayable export bundle |
| `POST /api/cases/{id}/exports/verify-replay` | Compare bundle versions with current engine |
| `GET /api/cases/{id}/diff` | Diff two analysis runs |
| `GET /api/profiles` | List all user profiles |
| `GET /api/features` | Current feature gate state |
| `GET /api/runs/recent` | Recent runs across all cases |
| `POST /api/analyze` | Returns 410 Gone — use quick-analysis or cases instead |

## Running Tests

```bash
pytest tests/ -q
pytest tests/ -x           # stop on first failure
pytest tests/test_plugins/ # run just plugin tests
```

## Code Layout

```
src/goose/
  core/           # Flight model, Finding model, narrative, scoring
  parsers/        # Parser framework (ulog, dataflash, csv; tlog stub)
  plugins/        # 17 built-in analyzers + contract + registry
  forensics/      # Canonical models, case service, lifting, timeline, replay, diff
  web/            # FastAPI app, routes, static files (index.html)
  features.py     # Feature gate scaffold
  config/         # Configuration loading
```

## Environment

No environment variables are required for local development. All state lives in the `cases/` directory (default location is the current working directory). Use `goose.yaml` or the `--cases-dir` flag to change the cases directory.

## Linting

```bash
ruff check src/ tests/
mypy src/
bandit -r src/
```
