"""Evidence ingest and retrieval routes.

Extracted from cases_api.py during API modularization sprint.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evidence"])


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


@router.post("/{case_id}/evidence", status_code=201)
async def ingest_evidence(
    case_id: str,
    file: UploadFile = File(...),
    notes: str = "",
) -> JSONResponse:
    """Ingest a file as immutable evidence into the case."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        ev = svc.ingest_evidence_bytes(
            case_id=case_id,
            filename=file.filename,
            content=content,
            acquired_by="gui",
            notes=notes,
        )
        return JSONResponse(
            {"ok": True, "evidence": _serialize_evidence(ev)},
            status_code=201,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Evidence ingest failed for case %s", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}/evidence")
async def list_evidence(case_id: str) -> JSONResponse:
    """List all evidence items attached to a case."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
        return JSONResponse({
            "ok": True,
            "evidence": [_serialize_evidence(ev) for ev in case.evidence_items],
            "count": len(case.evidence_items),
        })
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    except Exception as exc:
        logger.exception("Failed to list evidence for case %s", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
