"""Attachment routes (v11 Strategy Sprint).

Non-telemetry attachments (photos, videos, notes, GCS logs, checklists,
report appendices, etc.) are uploaded per-case and stored alongside the
primary evidence. Each attachment is hashed, recorded in a per-case
``attachments/manifest.json``, and served back by a stable ``attachment_id``.

Storage layout
--------------
    cases/{case_id}/attachments/{attachment_id}_{filename}
    cases/{case_id}/attachments/manifest.json

The manifest is a JSON list of ``Attachment.to_dict()`` entries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from goose.forensics.models import Attachment, AttachmentType

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attachments"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:200] or "attachment"


def _attachments_dir(case_id: str) -> Path:
    from goose.web.cases_api import get_service
    svc = get_service()
    svc.get_case(case_id)  # raises FileNotFoundError if unknown
    d = svc.case_dir(case_id) / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path(case_id: str) -> Path:
    return _attachments_dir(case_id) / "manifest.json"


def _load_manifest(case_id: str) -> list[dict]:
    p = _manifest_path(case_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("Corrupt attachment manifest for case %s: %s", case_id, exc)
    return []


def _save_manifest(case_id: str, entries: list[dict]) -> None:
    p = _manifest_path(case_id)
    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _new_attachment_id() -> str:
    return f"ATT-{uuid.uuid4().hex[:8].upper()}"


def _parse_attachment_type(raw: str) -> AttachmentType:
    if not raw:
        return AttachmentType.OTHER
    try:
        return AttachmentType(raw)
    except ValueError:
        return AttachmentType.OTHER


# ---------------------------------------------------------------------------
# Routes — mounted under /api/cases via cases_api router
# ---------------------------------------------------------------------------

@router.post("/{case_id}/attachments", status_code=201)
async def upload_attachment(
    case_id: str,
    file: UploadFile = File(...),
    attachment_type: str = Form("other"),
    notes: str = Form(""),
    related_evidence_id: str | None = Form(None),
    related_timeline_time: float | None = Form(None),
    provenance_summary: str | None = Form(None),
    uploaded_by: str = Form("gui"),
) -> JSONResponse:
    """Upload a non-telemetry attachment to a case."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    try:
        att_dir = _attachments_dir(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        attachment_id = _new_attachment_id()
        safe = _sanitize_filename(file.filename)
        stored_name = f"{attachment_id}_{safe}"
        stored_path = att_dir / stored_name

        # Write bytes (non-empty guaranteed above)
        stored_path.write_bytes(content)

        sha256 = hashlib.sha256(content).hexdigest()
        sha512 = hashlib.sha512(content).hexdigest()

        content_type = file.content_type or (
            mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
        )

        att = Attachment(
            attachment_id=attachment_id,
            case_id=case_id,
            filename=file.filename,
            content_type=content_type,
            size_bytes=len(content),
            sha256=sha256,
            attachment_type=_parse_attachment_type(attachment_type),
            stored_path=str(stored_path.resolve()),
            uploaded_at=datetime.now().replace(microsecond=0).isoformat(),
            uploaded_by=uploaded_by,
            sha512=sha512,
            immutable=True,
            notes=notes,
            related_evidence_id=related_evidence_id,
            related_timeline_time=related_timeline_time,
            provenance_summary=provenance_summary,
        )

        entries = _load_manifest(case_id)
        entries.append(att.to_dict())
        _save_manifest(case_id, entries)

        return JSONResponse({"ok": True, "attachment": att.to_dict()}, status_code=201)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Attachment upload failed for case %s", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}/attachments")
async def list_attachments(case_id: str) -> JSONResponse:
    try:
        _attachments_dir(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    entries = _load_manifest(case_id)
    return JSONResponse({
        "ok": True,
        "attachments": entries,
        "count": len(entries),
    })


@router.get("/{case_id}/attachments/{attachment_id}")
async def get_attachment_metadata(case_id: str, attachment_id: str) -> JSONResponse:
    try:
        _attachments_dir(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    for entry in _load_manifest(case_id):
        if entry.get("attachment_id") == attachment_id:
            return JSONResponse({"ok": True, "attachment": entry})
    raise HTTPException(status_code=404, detail=f"Attachment not found: {attachment_id}")


@router.get("/{case_id}/attachments/{attachment_id}/file")
async def get_attachment_file(case_id: str, attachment_id: str) -> FileResponse:
    try:
        _attachments_dir(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    for entry in _load_manifest(case_id):
        if entry.get("attachment_id") == attachment_id:
            stored_path = entry.get("stored_path")
            if not stored_path or not Path(stored_path).exists():
                raise HTTPException(status_code=404, detail="Attachment file missing on disk")
            return FileResponse(
                stored_path,
                media_type=entry.get("content_type") or "application/octet-stream",
                filename=entry.get("filename") or "attachment",
            )
    raise HTTPException(status_code=404, detail=f"Attachment not found: {attachment_id}")
