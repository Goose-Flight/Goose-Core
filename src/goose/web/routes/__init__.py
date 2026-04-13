"""Modular API route blueprints for Goose-Core.

Hardening Sprint — API Modularization

All case-oriented routes are split into focused modules:
- cases: case CRUD
- evidence: evidence ingest and retrieval
- analysis: analyze, findings, hypotheses, plugins, diagnostics
- timeline: timeline construction
- charts: chart data retrieval
- exports: exports, bundles, replay verification, report generation
- runs: analysis run tracking and retrieval
"""

from fastapi import APIRouter

from goose.web.routes.analysis import router as analysis_router
from goose.web.routes.attachments import router as attachments_router
from goose.web.routes.cases import router as cases_router
from goose.web.routes.charts import router as charts_router
from goose.web.routes.evidence import router as evidence_router
from goose.web.routes.exports import router as exports_router
from goose.web.routes.runs import router as runs_router
from goose.web.routes.timeline import router as timeline_router


def register_routes(parent_router: APIRouter) -> None:
    """Register all route sub-routers onto the parent cases router."""
    parent_router.include_router(cases_router)
    parent_router.include_router(evidence_router)
    parent_router.include_router(analysis_router)
    parent_router.include_router(timeline_router)
    parent_router.include_router(charts_router)
    parent_router.include_router(exports_router)
    parent_router.include_router(runs_router)
    parent_router.include_router(attachments_router)
