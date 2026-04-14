"""Goose embedded web UI — FastAPI application factory."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import goose as _goose_pkg

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_FRONTEND_DIR = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"

# Timeseries extraction shared with Quick Analysis cockpit


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


# ── Security middleware ────────────────────────────────────────────────────────

_SECURITY_HEADERS = {
    # Block clickjacking
    "X-Frame-Options": "DENY",
    # Prevent MIME sniffing of served files
    "X-Content-Type-Options": "nosniff",
    # Block cross-site scripting in legacy browsers
    "X-XSS-Protection": "1; mode=block",
    # Referrer policy — don't leak URLs to external sites
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Content Security Policy:
    #   - Scripts: same origin only (+ inline needed for SPA)
    #   - Styles: same origin only (+ inline needed for embedded CSS)
    #   - No framing
    #   - Fonts/images: same origin
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none';"
    ),
}

_CASE_ID_PATTERN = __import__("re").compile(r"^CASE-\d{4}-(?:\d{6}|[0-9A-F]{8})$")


def _validate_case_id(case_id: str) -> str:
    """Raise 400 if case_id doesn't match expected format, else return it."""
    if not _CASE_ID_PATTERN.match(case_id):
        raise HTTPException(status_code=400, detail="Invalid case identifier format")
    return case_id


def create_app() -> FastAPI:
    """Create and return the FastAPI application."""
    import secrets as _secrets

    from goose.web.config import settings

    # ── Startup session token (C-1) ───────────────────────────────────────────
    # If GOOSE_API_TOKEN is explicitly set, use that. Otherwise, generate a
    # random token at startup and print it to the console. The token is:
    #   1. Printed once to stdout so the operator knows it
    #   2. Injected into the served index.html as window.GOOSE_TOKEN so the SPA
    #      can send it automatically — no login UI required
    #
    # This protects against other local processes (browser extensions, malware)
    # from calling the API, while remaining transparent to the operator.
    if settings.api_token:
        _session_token = settings.api_token
    else:
        _session_token = _secrets.token_urlsafe(32)
        print(  # noqa: T201 — intentional console output at startup
            f"\n  Goose session token: {_session_token}\n  (Set GOOSE_API_TOKEN env var to use a fixed token)\n"
        )
    # Store token in settings so verify_token() can read it
    settings.api_token = _session_token

    app = FastAPI(
        title="Goose Flight Analyzer",
        description="Drone flight log validation and crash analysis",
        version=_goose_pkg.__version__,
        # Never expose internal Python errors in OpenAPI error responses
        debug=settings.debug,
    )

    # ------------------------------------------------------------------
    # Security headers — added to every response
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Redirect /static/index.html → / so the token injection always fires.
        # StaticFiles would serve it without window.GOOSE_TOKEN, breaking auth.
        if request.url.path in ("/static/index.html", "/static/index.htm"):
            from fastapi.responses import RedirectResponse

            return RedirectResponse(url="/", status_code=302)
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    # ------------------------------------------------------------------
    # Bearer token auth — always enforced (token generated at startup)
    # ------------------------------------------------------------------
    async def verify_token(request: Request) -> None:
        # Static files and the SPA root are always public — the SPA itself
        # delivers the token to the browser via window.GOOSE_TOKEN injection.
        path = request.url.path
        if not path.startswith("/api/"):
            return
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        token = auth_header.removeprefix("Bearer ").strip()
        if not _secrets.compare_digest(token, _session_token):
            raise HTTPException(status_code=403, detail="Invalid token")

    # ------------------------------------------------------------------
    # CORS — explicit localhost-only policy (no allow_origins=["*"])
    # ------------------------------------------------------------------
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://127.0.0.1:{settings.port}",
            f"http://localhost:{settings.port}",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            # Vite dev server (React frontend)
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ------------------------------------------------------------------
    # Static files — React frontend build takes priority over legacy
    # ------------------------------------------------------------------
    if _FRONTEND_DIR.exists() and (_FRONTEND_DIR / "index.html").exists():
        _assets = _FRONTEND_DIR / "assets"
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="frontend-assets")
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # ------------------------------------------------------------------
    # Case-oriented routes (Sprint 2+)
    # ------------------------------------------------------------------
    from goose.web.cases_api import router as cases_router

    app.include_router(cases_router, dependencies=[Depends(verify_token)])

    # Validation harness routes
    from goose.web.routes.validation import router as validation_router

    app.include_router(validation_router, dependencies=[Depends(verify_token)])

    # Profile + feature-gate routes
    from goose.web.routes.profiles import router as profiles_router

    app.include_router(profiles_router, dependencies=[Depends(verify_token)])

    # Quick Analysis (session-only triage flow)
    from goose.web.routes.quick_analysis import router as quick_analysis_router

    app.include_router(quick_analysis_router, dependencies=[Depends(verify_token)])

    # ------------------------------------------------------------------
    # Settings endpoint — exposes current runtime config (no secrets)
    # ------------------------------------------------------------------
    @app.get("/api/settings", dependencies=[Depends(verify_token)])
    async def get_settings() -> JSONResponse:
        return JSONResponse({"ok": True, "settings": settings.as_dict()})

    # ------------------------------------------------------------------
    # Recent runs — must be registered before the SPA catch-all
    # ------------------------------------------------------------------
    @app.get("/api/runs/recent", dependencies=[Depends(verify_token)])
    async def recent_runs(limit: int = 20) -> JSONResponse:
        """Return the most recent analysis runs across all cases."""
        from goose.web.cases_api import get_service

        limit = max(1, min(limit, 100))

        try:
            svc = get_service()
            all_runs: list[Any] = []

            for case in svc.list_cases():
                case_id = case.case_id
                if not case_id:
                    continue

                case_name = getattr(case, "case_name", None) or getattr(case, "title", None) or case_id
                profile = getattr(case, "profile", "default") or "default"

                for run in case.analysis_runs:
                    all_runs.append(
                        {
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
                        }
                    )

            all_runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
            return JSONResponse(
                {
                    "ok": True,
                    "runs": all_runs[:limit],
                    "count": len(all_runs[:limit]),
                    "limit": limit,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to list recent runs")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    # ------------------------------------------------------------------
    # Plugin registry — must be registered before the SPA catch-all
    # ------------------------------------------------------------------
    @app.get("/api/plugins", dependencies=[Depends(verify_token)])
    async def list_plugins() -> JSONResponse:
        """Return metadata for all discovered plugins."""
        try:
            from goose.plugins.registry import load_plugins

            plugins = load_plugins()
            return JSONResponse(
                {
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
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to list plugins")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    # ------------------------------------------------------------------
    # Removed endpoint shim — POST /api/analyze (Convergence Sprint 1)
    # The old single-shot analyze endpoint was removed. All analysis now
    # goes through the case workflow:
    #   POST /api/cases → POST /api/cases/{id}/evidence → POST /api/cases/{id}/analyze
    # Return 410 Gone so clients receive a clear, actionable error.
    # ------------------------------------------------------------------
    @app.post("/api/analyze", dependencies=[Depends(verify_token)], status_code=410)
    async def analyze_gone(request: Request) -> JSONResponse:
        return JSONResponse(
            status_code=410,
            content={
                "error": "gone",
                "message": ("POST /api/analyze has been removed. Use the case-based workflow instead."),
                "alternatives": {
                    "create_case": "POST /api/cases",
                    "ingest_evidence": "POST /api/cases/{case_id}/evidence",
                    "run_analysis": "POST /api/cases/{case_id}/analyze",
                    "quick_analysis": "POST /api/quick-analysis",
                },
            },
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def _serve_spa(html_path: Path) -> Response:
        """Serve an SPA index.html with session token injected."""
        from fastapi.responses import HTMLResponse

        if not html_path.exists():
            raise HTTPException(status_code=404, detail="index.html not found")
        html = html_path.read_text(encoding="utf-8")
        injection = f'<script>window.GOOSE_TOKEN="{_session_token}";</script>'
        html = html.replace("<head>", f"<head>\n  {injection}", 1)
        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    # Determine which frontend to serve
    _use_react = _FRONTEND_DIR.exists() and (_FRONTEND_DIR / "index.html").exists()

    @app.get("/", include_in_schema=False)
    async def index() -> Response:
        """Serve the SPA with session token injected as window.GOOSE_TOKEN."""
        if _use_react:
            return _serve_spa(_FRONTEND_DIR / "index.html")
        return _serve_spa(_STATIC_DIR / "index.html")

    @app.get("/legacy", include_in_schema=False)
    async def legacy_index() -> Response:
        """Always serve the legacy vanilla JS frontend."""
        return _serve_spa(_STATIC_DIR / "index.html")

    # SPA catch-all — serves React index.html for all client-side routes
    if _use_react:

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_catchall(full_path: str) -> Response:
            # Don't catch API routes or static assets
            skip = ("api/", "static/", "assets/")
            if any(full_path.startswith(p) for p in skip):
                raise HTTPException(status_code=404)
            # Check if it's a real file in the frontend dist
            file_path = _FRONTEND_DIR / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            # Otherwise serve the SPA
            return _serve_spa(_FRONTEND_DIR / "index.html")

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
