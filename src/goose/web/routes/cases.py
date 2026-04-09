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
from goose.forensics.profiles import get_profile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cases"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateCaseRequest(BaseModel):
    """Case creation body.

    v11 Strategy Sprint — all new optional metadata fields are accepted here
    and merged into the created ``Case`` before it is persisted. Extra/unknown
    keys at the HTTP layer are ignored by pydantic.
    """
    created_by: str = "gui"
    tags: list[str] = []
    notes: str = ""
    # --- v11 Strategy Sprint: profile + extended metadata ---
    profile: str = "default"
    # Operational context
    mission_id: str | None = None
    sortie_id: str | None = None
    operation_type: str | None = None
    event_type: str | None = None
    event_classification: str | None = None
    event_severity: str | None = None
    date_time_start: str | None = None
    date_time_end: str | None = None
    location_name: str | None = None
    operating_area: str | None = None
    environment_summary: str | None = None
    # Platform
    platform_name: str | None = None
    platform_type: str | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    hardware_config: str | None = None
    payload_config: str | None = None
    battery_config: str | None = None
    propulsion_notes: str | None = None
    recent_changes: str | None = None
    # Human / org
    operator_name: str | None = None
    team_name: str | None = None
    unit_name: str | None = None
    organization: str | None = None
    customer_name: str | None = None
    ticket_id: str | None = None
    technician_name: str | None = None
    tester_name: str | None = None
    # Investigation / outcome
    damage_summary: str | None = None
    loss_summary: str | None = None
    recommendations: str | None = None
    corrective_actions: str | None = None
    closure_notes: str | None = None


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
        # v11 Strategy Sprint — surface profile + selected metadata in summary
        "profile": getattr(case, "profile", "default"),
        "mission_id": getattr(case, "mission_id", None),
        "event_type": getattr(case, "event_type", None),
        "event_classification": getattr(case, "event_classification", None),
        "platform_name": getattr(case, "platform_name", None),
        "operator_name": getattr(case, "operator_name", None),
    }


def _serialize_case_detail(case: Any) -> dict[str, Any]:
    summary = _serialize_case_summary(case)
    summary["evidence_items"] = [_serialize_evidence(ev) for ev in case.evidence_items]
    summary["analysis_runs"] = [r.to_dict() for r in case.analysis_runs]
    summary["exports"] = [x.to_dict() for x in case.exports]
    # v11 Strategy Sprint — full extended metadata on detail view
    for f in (
        "mission_id", "sortie_id", "operation_type", "event_type",
        "event_classification", "event_severity", "date_time_start", "date_time_end",
        "location_name", "operating_area", "environment_summary",
        "platform_name", "platform_type", "serial_number", "firmware_version",
        "hardware_config", "payload_config", "battery_config", "propulsion_notes",
        "recent_changes",
        "operator_name", "team_name", "unit_name", "organization",
        "customer_name", "ticket_id", "technician_name", "tester_name",
        "damage_summary", "loss_summary", "recommendations",
        "corrective_actions", "closure_notes",
    ):
        summary[f] = getattr(case, f, None)
    return summary


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

_V11_METADATA_FIELDS = (
    "profile",
    "mission_id", "sortie_id", "operation_type", "event_type",
    "event_classification", "event_severity", "date_time_start", "date_time_end",
    "location_name", "operating_area", "environment_summary",
    "platform_name", "platform_type", "serial_number", "firmware_version",
    "hardware_config", "payload_config", "battery_config", "propulsion_notes",
    "recent_changes",
    "operator_name", "team_name", "unit_name", "organization",
    "customer_name", "ticket_id", "technician_name", "tester_name",
    "damage_summary", "loss_summary", "recommendations",
    "corrective_actions", "closure_notes",
)


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
        # v11 Strategy Sprint — merge extended metadata onto the new case
        # and re-save so it's persisted to case.json.
        touched = False
        for field_name in _V11_METADATA_FIELDS:
            value = getattr(body, field_name, None)
            if value is not None and value != "":
                setattr(case, field_name, value)
                touched = True
        if touched:
            svc.save_case(case)
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
    """Return full case detail including evidence items and analysis runs.

    v11 Strategy Sprint — also returns the resolved ``profile_config`` for
    the case so the GUI can apply profile-specific wording, case-field
    visibility, and chart presets without an extra round-trip.
    """
    try:
        from goose.web.cases_api import get_service
        svc = get_service()
        case = svc.get_case(case_id)
        detail = _serialize_case_detail(case)
        profile_cfg = get_profile(getattr(case, "profile", "default") or "default")
        return JSONResponse({
            "ok": True,
            "case": detail,
            "profile_config": profile_cfg.to_dict(),
        })
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
