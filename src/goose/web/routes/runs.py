"""Analysis run tracking and retrieval routes.

Hardening Sprint — Run-Centered Investigation Flow
Advanced Forensic Validation Sprint — Replay + run comparison
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])


class CompareRunsRequest(BaseModel):
    run_a_id: str
    run_b_id: str


@router.get("/{case_id}/runs")
async def list_runs(case_id: str) -> JSONResponse:
    """Return all analysis runs for a case."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

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
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

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
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass

    # Get findings count for this run
    hypotheses_count = 0
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
            if bundle.get("run_id") == run_id:
                hypotheses_count = len(bundle.get("hypotheses", []))
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass

    result = run.to_dict()
    result["plugin_statuses"] = plugin_statuses
    result["hypotheses_count"] = hypotheses_count

    return JSONResponse({"ok": True, "run": result})


@router.post("/{case_id}/runs/{run_id}/replay")
async def replay_run(case_id: str, run_id: str) -> JSONResponse:
    """Trigger a deterministic replay of a prior run.

    Re-runs parse and analysis, compares to the original run, and persists
    a ReplayVerificationRecord.
    """
    from goose.forensics.replay import execute_replay
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    # Verify source run exists
    source_run = next((r for r in case.analysis_runs if r.run_id == run_id), None)
    if source_run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    case_dir = svc.case_dir(case_id)
    try:
        record = execute_replay(case_dir, run_id)
    except Exception as exc:
        logger.exception("Replay execution failed for case %s run %s", case_id, run_id)
        raise HTTPException(status_code=500, detail=f"Replay failed: {exc}") from exc

    return JSONResponse({"ok": True, "replay": record.to_dict()})


@router.get("/{case_id}/runs/{run_id}/replay-verification")
async def get_replay_verification(case_id: str, run_id: str) -> JSONResponse:
    """Return the most recent replay verification record for a run, if any."""
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    exports_dir = svc.case_dir(case_id) / "exports"
    if not exports_dir.exists():
        return JSONResponse({"ok": True, "replay": None})

    # Find replay files for this source run
    latest_record: dict[str, Any] | None = None
    latest_verified_at = ""
    for fp in exports_dir.glob("replay_*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if data.get("source_run_id") == run_id:
                va = data.get("verified_at", "")
                if va > latest_verified_at:
                    latest_verified_at = va
                    latest_record = data
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            continue

    return JSONResponse({"ok": True, "replay": latest_record})


@router.post("/{case_id}/compare-runs")
async def compare_runs_endpoint(case_id: str, body: CompareRunsRequest) -> JSONResponse:
    """Compare two runs within a case, persist the comparison, and return the structured diff."""
    from goose.forensics.diff import compare_runs, save_comparison
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    case_dir = svc.case_dir(case_id)
    try:
        comparison = compare_runs(case_dir, body.run_a_id, body.run_b_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Run comparison failed")
        raise HTTPException(status_code=500, detail=f"Compare failed: {exc}") from exc

    # Persist the comparison so it can be retrieved later without re-computing
    try:
        save_comparison(case_dir, comparison)
    except OSError as exc:
        logger.warning("Failed to persist comparison %s — returning result anyway: %s", comparison.comparison_id, exc)

    return JSONResponse({"ok": True, "comparison": comparison.to_dict()})


@router.get("/{case_id}/comparisons")
async def list_comparisons_endpoint(case_id: str) -> JSONResponse:
    """Return the index of all saved run comparisons for a case."""
    from goose.forensics.diff import list_comparisons
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    case_dir = svc.case_dir(case_id)
    entries = list_comparisons(case_dir)
    return JSONResponse({"ok": True, "comparisons": entries, "count": len(entries)})


@router.get("/{case_id}/comparisons/{comparison_id}")
async def get_comparison_endpoint(case_id: str, comparison_id: str) -> JSONResponse:
    """Return a saved comparison by ID."""
    from goose.forensics.diff import load_comparison
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    case_dir = svc.case_dir(case_id)
    comparison = load_comparison(case_dir, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail=f"Comparison not found: {comparison_id}")

    return JSONResponse({"ok": True, "comparison": comparison.to_dict()})
