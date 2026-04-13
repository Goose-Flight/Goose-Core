"""Evidence ingest and retrieval routes.

Extracted from cases_api.py during API modularization sprint.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evidence"])


def _serialize_evidence(ev: Any) -> dict[str, Any]:
    """Serialize evidence metadata — stored_path deliberately excluded (H-1)."""
    return {
        "evidence_id": ev.evidence_id,
        "filename": ev.filename,
        "content_type": ev.content_type,
        "size_bytes": ev.size_bytes,
        "sha256": ev.sha256,
        "sha512": ev.sha512,
        "source_acquisition_mode": ev.source_acquisition_mode,
        "acquired_at": ev.acquired_at.isoformat(),
        "acquired_by": ev.acquired_by,
        "immutable": ev.immutable,
        "notes": ev.notes,
    }


@router.post("/{case_id}/evidence", status_code=201)
async def ingest_evidence(
    case_id: str,
    file: UploadFile = File(...),  # noqa: B008 — FastAPI Depends/File pattern
    notes: str = "",
) -> JSONResponse:
    """Ingest a file as immutable evidence into the case."""
    from goose.web.config import settings

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Extension allowlist — only known flight log formats accepted
    suffix = Path(file.filename).suffix.lower()
    if suffix not in settings.allowed_log_extensions:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Accepted: {sorted(settings.allowed_log_extensions)}",
        )

    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid case identifier") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")  # noqa: TRY301

        # Enforce upload size limit
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(  # noqa: TRY301
                status_code=413,
                detail=f"File exceeds maximum upload size of {settings.max_upload_mb} MiB",
            )

        ev = svc.ingest_evidence_bytes(
            case_id=case_id,
            filename=Path(file.filename).name,  # strip any directory components
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
    except Exception as exc:  # noqa: BLE001
        logger.exception("Evidence ingest failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/{case_id}/evidence")
async def list_evidence(case_id: str) -> JSONResponse:
    """List all evidence items attached to a case."""
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        case = svc.get_case(case_id)
        return JSONResponse(
            {
                "ok": True,
                "evidence": [_serialize_evidence(ev) for ev in case.evidence_items],
                "count": len(case.evidence_items),
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid case identifier") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list evidence for case %s", case_id)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
