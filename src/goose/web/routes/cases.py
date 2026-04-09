"""Case CRUD routes.

Extracted from cases_api.py during API modularization sprint.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from goose.forensics import CaseService, CaseStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cases"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateCaseRequest(BaseModel):
    created_by: str = "gui"
    tags: list[str] = []
    notes: str = ""


class UpdateStatusRequest(BaseModel):
    status: str
    actor: str = "gui"


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_evidence(ev: Any) -> dict[str, Any]:
    return {
        "evidence_id": ev.evidence_id,
        "filename": ev.filename,
        "content_type": ev.content_type,
        "size_bytes": ev.size_bytes,
        "sha256": ev.sha256,
        "sha512": ev.sha512,
        "source_acquisition_mode": ev.source_acquisition_mode,
        "stored_path": ev.stored_path,
        "acquired_at": ev.acquired_at.isoformat(),
        "acquired_by": ev.acquired_by,
        "immutable": ev.immutable,
        "notes": ev.notes,
    }


def _serialize_case_summary(case: Any) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "created_at": case.created_at.isoformat(),
        "created_by": case.created_by,
        "status": case.status.value,
        "tags": case.tags,
        "notes": case.notes,
        "engine_version": case.engine_version,
        "evidence_count": len(case.evidence_items),
        "analysis_run_count": len(case.analysis_runs),
        "export_count": len(case.exports),
    }


def _serialize_case_detail(case: Any) -> dict[str, Any]:
    summary = _serialize_case_summary(case)
    summary["evidence_items"] = [_serialize_evidence(ev) for ev in case.evidence_items]
    summary["analysis_runs"] = [r.to_dict() for r in case.analysis_runs]
    summary["exports"] = [x.to_dict() for x in case.exports]
    return summary


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/", status_code=201)
async def create_case(body: CreateCaseRequest) -> JSONResponse:
    """Create a new forensic case and return its metadata."""
    try:
        from goose.web.cases_api import get_service
        svc = get_service()
        case = svc.create_case(
            created_by=body.created_by,
            tags=body.tags,
            notes=body.notes,
        )
        return JSONResponse({"ok": True, "case": _serialize_case_detail(case)}, status_code=201)
    except Exception as exc:
        logger.exception("Failed to create case")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/")
async def list_cases() -> JSONResponse:
    """Return all cases (summary only) sorted by creation time descending."""
    try:
        from goose.web.cases_api import get_service
        svc = get_service()
        cases = svc.list_cases()
        return JSONResponse({
            "ok": True,
            "cases": [_serialize_case_summary(c) for c in cases],
            "count": len(cases),
        })
    except Exception as exc:
        logger.exception("Failed to list cases")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}")
async def get_case(case_id: str) -> JSONResponse:
    """Return full case detail including evidence items and analysis runs."""
    try:
        from goose.web.cases_api import get_service
        svc = get_service()
        case = svc.get_case(case_id)
        return JSONResponse({"ok": True, "case": _serialize_case_detail(case)})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    except Exception as exc:
        logger.exception("Failed to get case %s", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/{case_id}/status")
async def update_case_status(case_id: str, body: UpdateStatusRequest) -> JSONResponse:
    """Update the status of a case."""
    try:
        status = CaseStatus(body.status)
    except ValueError:
        valid = [s.value for s in CaseStatus]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Valid values: {valid}",
        )
    try:
        from goose.web.cases_api import get_service
        svc = get_service()
        case = svc.update_status(case_id, status, actor=body.actor)
        return JSONResponse({"ok": True, "case": _serialize_case_summary(case)})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
