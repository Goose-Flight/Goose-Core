"""Goose embedded web UI — FastAPI application factory."""

import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

# Timeseries extraction shared with Quick Analysis cockpit
from goose.web.timeseries_utils import extract_timeseries as _extract_timeseries  # noqa: E402

# Keep private aliases for any call sites inside this module
def _downsample(arr: list, max_points: int = 2000) -> list:
    from goose.web.timeseries_utils import downsample
    return downsample(arr, max_points)

def _safe_val(v: Any) -> Any:
    from goose.web.timeseries_utils import safe_val
    return safe_val(v)

def _df_to_series(df: Any, columns: list[str] | None = None, max_points: int = 2000) -> dict[str, list] | None:
    from goose.web.timeseries_utils import df_to_series
    return df_to_series(df, columns, max_points)


def _finding_to_dict(finding: Any) -> dict[str, Any]:
    """Serialize a Finding dataclass to a JSON-safe dict."""
    evidence = finding.evidence or {}
    # Walk evidence values and sanitize non-serializable types (numpy scalars, etc.)
    safe_evidence: dict[str, Any] = {}
    for k, v in evidence.items():
        try:
            import json
            json.dumps(v)
            safe_evidence[k] = v
        except (TypeError, ValueError):
            safe_evidence[k] = str(v)

    return {
        "plugin_name": finding.plugin_name,
        "title": finding.title,
        "severity": finding.severity,
        "score": int(finding.score),
        "description": finding.description,
        "evidence": safe_evidence,
        "phase": finding.phase,
        "timestamp_start": finding.timestamp_start,
        "timestamp_end": finding.timestamp_end,
    }


def _compute_overall_score(findings: list[Any]) -> int:
    """Compute a weighted overall score (0-100) from all findings."""
    from goose.core.scoring import compute_overall_score
    return compute_overall_score(findings)


def create_app():
    """Create and return the FastAPI application."""
    app = FastAPI(
        title="Goose Flight Analyzer",
        description="Drone flight log validation and crash analysis",
        version="1.0.0",
    )

    # ------------------------------------------------------------------
    # Static files
    # ------------------------------------------------------------------
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # ------------------------------------------------------------------
    # Case-oriented routes (Sprint 2+)
    # ------------------------------------------------------------------
    from goose.web.cases_api import router as cases_router
    app.include_router(cases_router)

    # Validation harness routes (Advanced Forensic Validation Sprint)
    from goose.web.routes.validation import router as validation_router
    app.include_router(validation_router)

    # v11 Strategy Sprint — profile + feature-gate routes (app-level, not under /api/cases)
    from goose.web.routes.profiles import router as profiles_router
    app.include_router(profiles_router)

    # v11 Strategy Sprint — Quick Analysis (session-only triage flow)
    from goose.web.routes.quick_analysis import router as quick_analysis_router
    app.include_router(quick_analysis_router)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        """Serve the single-page HTML application."""
        html_path = _STATIC_DIR / "index.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(
            str(html_path),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/api/runs/recent")
    async def recent_runs(limit: int = 20) -> JSONResponse:
        """Return the most recent analysis runs across all cases.

        Supports the 'Open Recent' UX entry path. Returns case_id, run_id,
        case_name, profile, severity summary, and timestamp — enough context
        for the user to select a run to reopen without loading full case data.

        Args:
            limit: Maximum number of runs to return (default 20, capped at 100).
        """
        from goose.forensics import CaseService
        import json as _json

        limit = max(1, min(limit, 100))

        try:
            from goose.web.cases_api import get_service
            svc = get_service()
            all_runs: list[dict] = []

            for case in svc.list_cases():
                # list_cases() returns Case objects directly
                case_id = case.case_id
                if not case_id:
                    continue

                case_name = (
                    getattr(case, "case_name", None)
                    or getattr(case, "title", None)
                    or case_id
                )
                profile = getattr(case, "profile", "default") or "default"

                for run in case.analysis_runs:
                    all_runs.append({
                        "case_id": case_id,
                        "case_name": case_name,
                        "run_id": run.run_id,
                        "profile": run.profile_id or profile,
                        "started_at": run.started_at.isoformat(),
                        "status": run.status,
                        "findings_count": run.findings_count,
                        "critical_count": run.critical_count,
                        "warning_count": run.warning_count,
                        "hypotheses_count": run.hypotheses_count,
                        "engine_version": run.engine_version,
                        "parser_name": run.parser_name,
                    })

            # Sort by most recent first
            all_runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
            all_runs = all_runs[:limit]

            return JSONResponse({
                "ok": True,
                "runs": all_runs,
                "count": len(all_runs),
                "limit": limit,
            })
        except Exception as exc:
            logger.exception("Failed to list recent runs")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/plugins")
    async def list_plugins() -> JSONResponse:
        """Return metadata for all discovered plugins."""
        try:
            from goose.plugins.registry import load_plugins
            plugins = load_plugins()
            return JSONResponse({
                "plugins": [
                    {
                        "name": p.name,
                        "description": p.description,
                        "version": p.version,
                        "min_mode": p.min_mode,
                    }
                    for p in plugins
                ],
                "count": len(plugins),
            })
        except Exception as exc:
            logger.exception("Failed to list plugins")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/analyze")
    async def analyze(file: UploadFile = File(...)) -> JSONResponse:
        """
        DEPRECATED — This endpoint is removed.

        It emitted thin findings without evidence references, audit trail, or
        tuning provenance and bypassed the case system entirely.

        Use instead:
          POST /api/quick-analysis          — session-only triage (no case created)
          POST /api/cases                   — create a persistent investigation case
          POST /api/cases/{id}/analyze      — run full forensic analysis on a case
        """
        # Consume the upload to avoid client-side connection errors
        await file.read()
        return JSONResponse(
            status_code=410,
            content={
                "error": "gone",
                "message": (
                    "POST /api/analyze is removed. It produced forensic results "
                    "without evidence references, audit trail, or tuning provenance. "
                    "Use POST /api/quick-analysis for session-only triage, or "
                    "POST /api/cases + POST /api/cases/{id}/analyze for a persistent "
                    "investigation case with full chain-of-custody."
                ),
                "alternatives": {
                    "quick_triage": "POST /api/quick-analysis",
                    "create_case": "POST /api/cases",
                    "analyze_case": "POST /api/cases/{case_id}/analyze",
                },
            },
        )

    return app


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if not math.isfinite(seconds) or seconds < 0:
        return "unknown"
    total_sec = int(round(seconds))
    hours, remainder = divmod(total_sec, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


# Module-level app instance for uvicorn ("goose.web.app:app")
app = create_app()
