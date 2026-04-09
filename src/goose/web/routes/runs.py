"""Analysis run tracking and retrieval routes.

Hardening Sprint — Run-Centered Investigation Flow
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])


@router.get("/{case_id}/runs")
async def list_runs(case_id: str) -> JSONResponse:
    """Return all analysis runs for a case."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    return JSONResponse({
        "ok": True,
        "runs": [r.to_dict() for r in case.analysis_runs],
        "count": len(case.analysis_runs),
    })


@router.get("/{case_id}/runs/{run_id}")
async def get_run(case_id: str, run_id: str) -> JSONResponse:
    """Return detail for a specific analysis run."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    run = next((r for r in case.analysis_runs if r.run_id == run_id), None)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Enrich with plugin diagnostics if available
    case_dir = svc.case_dir(case_id)
    plugin_statuses: list[dict[str, Any]] = []
    diag_path = case_dir / "analysis" / "plugin_diagnostics.json"
    if diag_path.exists():
        try:
            bundle = json.loads(diag_path.read_text(encoding="utf-8"))
            if bundle.get("run_id") == run_id:
                plugin_statuses = bundle.get("plugin_diagnostics", [])
        except Exception:
            pass

    # Get findings count for this run
    findings_count = run.findings_count
    hypotheses_count = 0
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
            if bundle.get("run_id") == run_id:
                hypotheses_count = len(bundle.get("hypotheses", []))
        except Exception:
            pass

    result = run.to_dict()
    result["plugin_statuses"] = plugin_statuses
    result["hypotheses_count"] = hypotheses_count

    return JSONResponse({"ok": True, "run": result})
