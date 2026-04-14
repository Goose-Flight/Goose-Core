"""Case-oriented API routes for Goose forensic workflow.

Hardening Sprint: modularized into route sub-modules under goose.web.routes/
This file now serves as the router aggregator and CaseService provider.

All route modules import get_service() from here for shared state.

Routes (all under /api/cases prefix):
  POST /api/cases                                — create case
  GET  /api/cases                                — list cases
  GET  /api/cases/{case_id}                      — get case detail
  POST /api/cases/{case_id}/evidence             — ingest evidence (multipart)
  GET  /api/cases/{case_id}/evidence             — list evidence items
  POST /api/cases/{case_id}/analyze              — run analysis on case evidence
  GET  /api/cases/{case_id}/findings             — get findings from last analysis
  GET  /api/cases/{case_id}/hypotheses           — get hypotheses
  GET  /api/cases/{case_id}/diagnostics          — get parse diagnostics
  GET  /api/cases/{case_id}/audit                — get audit log entries
  GET  /api/cases/{case_id}/plugins              — get plugin manifests + diagnostics
  PATCH /api/cases/{case_id}/status              — update case status
  GET  /api/cases/{case_id}/timeline             — timeline events
  GET  /api/cases/{case_id}/charts/data          — chart time-series data
  GET  /api/cases/{case_id}/exports              — list exports
  POST /api/cases/{case_id}/exports/bundle       — create case bundle
  GET  /api/cases/{case_id}/exports/files/{name} — download export file
  POST /api/cases/{case_id}/exports/verify-replay — verify replay compatibility
  GET  /api/cases/{case_id}/exports/reports/mission-summary — mission summary report
  GET  /api/cases/{case_id}/exports/reports/anomaly         — anomaly report
  GET  /api/cases/{case_id}/exports/reports/crash           — crash/mishap report
  GET  /api/cases/{case_id}/runs                 — list analysis runs
  GET  /api/cases/{case_id}/runs/{run_id}        — get run detail
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from goose.forensics import CaseService
from goose.web.routes.cases import CreateCaseRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cases", tags=["cases"])

# Module-level CaseService — initialized once when the module loads.
# Uses a `cases/` directory relative to the current working directory.
# Can be overridden in tests by replacing this reference.
_service: CaseService | None = None


def get_service() -> CaseService:
    global _service
    if _service is None:
        _service = CaseService()
    return _service


def _set_service(svc: CaseService) -> None:
    """For test injection."""
    global _service
    _service = svc


# Register all route sub-modules
from goose.web.routes import register_routes  # noqa: E402

register_routes(router)

# ---------------------------------------------------------------------------
# Root-level routes registered directly on the parent router so they resolve
# to /api/cases (no trailing slash).  This avoids the Starlette redirect_slashes
# interaction with the SPA GET /{full_path:path} catch-all, which causes 405
# Method Not Allowed when a POST /api/cases (no trailing slash) is received.
#
# The sub-router routes in goose.web.routes.cases still register /api/cases/
# (with trailing slash) for backward compatibility — both paths work.
# ---------------------------------------------------------------------------


@router.post("", status_code=201, include_in_schema=False)
async def _create_case_no_slash(body: CreateCaseRequest) -> JSONResponse:
    from goose.web.routes.cases import create_case

    return await create_case(body)


@router.get("", include_in_schema=False)
async def _list_cases_no_slash() -> JSONResponse:
    from goose.web.routes.cases import list_cases

    return await list_cases()
