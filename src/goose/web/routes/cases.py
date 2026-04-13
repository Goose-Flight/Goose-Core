"""Case CRUD routes.

Extracted from cases_api.py during API modularization sprint.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from goose.forensics import CaseStatus
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
    # L-3: validate length and character set for audit-log fields
    from pydantic import Field as _Field
    created_by: str = _Field(default="gui", max_length=64, pattern=r"^[\w\-. @]+$")
    tags: list[str] = []
    notes: str = _Field(default="", max_length=4096)
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
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc
    except Exception as exc:
        logger.exception("Failed to get case %s", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}/completeness")
async def get_case_completeness(case_id: str) -> JSONResponse:
    """Return a structured completeness checklist for a case.

    Profile-aware:
    - gov_mil: requires evidence, analysis, attachments, metadata, and exports for a perfect score.
    - racer: only requires evidence and analysis.
    - default/other: balanced weighting.
    """
    try:
        from goose.web.cases_api import get_service
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc
    except Exception as exc:
        logger.exception("Failed to load case %s for completeness check", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    profile = getattr(case, "profile", "default") or "default"
    case_dir = svc.case_dir(case_id)
    analysis_dir = case_dir / "analysis"

    # -------------------------------------------------------------------------
    # Evidence section
    # -------------------------------------------------------------------------
    evidence_count = len(case.evidence_items)
    evidence_issues: list[str] = []
    if evidence_count == 0:
        evidence_issues.append("No evidence uploaded — upload a flight log to begin analysis")
    evidence_section = {
        "present": evidence_count > 0,
        "count": evidence_count,
        "issues": evidence_issues,
    }

    # -------------------------------------------------------------------------
    # Analysis section
    # -------------------------------------------------------------------------
    run_count = len(case.analysis_runs)
    analysis_issues: list[str] = []
    if run_count == 0:
        analysis_issues.append("No analysis run yet — run analysis on the uploaded evidence")
    analysis_section = {
        "present": run_count > 0,
        "run_count": run_count,
        "issues": analysis_issues,
    }

    # -------------------------------------------------------------------------
    # Attachments section
    # -------------------------------------------------------------------------
    attachments_dir = case_dir / "attachments"
    attachment_count = 0
    if attachments_dir.exists():
        attachment_count = len([
            f for f in attachments_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
        ])
    attachments_issues: list[str] = []
    if attachment_count == 0:
        attachments_issues.append(
            "No attachments uploaded — photos or video recommended for forensic completeness"
        )
    attachments_section = {
        "present": attachment_count > 0,
        "count": attachment_count,
        "issues": attachments_issues,
    }

    # -------------------------------------------------------------------------
    # Hypotheses section
    # -------------------------------------------------------------------------
    hyp_count = 0
    hyp_path = analysis_dir / "hypotheses.json"
    if hyp_path.exists():
        try:
            hyp_bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
            hyp_count = len(hyp_bundle.get("hypotheses", []))
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass
    hypotheses_issues: list[str] = []
    if hyp_count == 0 and run_count > 0:
        hypotheses_issues.append("No hypotheses generated — re-run analysis to produce root-cause candidates")
    hypotheses_section = {
        "present": hyp_count > 0,
        "count": hyp_count,
        "issues": hypotheses_issues,
    }

    # -------------------------------------------------------------------------
    # Timeline section
    # -------------------------------------------------------------------------
    timeline_path = case_dir / "timeline" / "timeline.json"
    event_count = 0
    if timeline_path.exists():
        try:
            tl_data = json.loads(timeline_path.read_text(encoding="utf-8"))
            event_count = len(tl_data.get("events", []))
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass
    timeline_issues: list[str] = []
    if event_count == 0 and run_count > 0:
        timeline_issues.append("No timeline events — timeline is built automatically during analysis")
    timeline_section = {
        "present": event_count > 0,
        "event_count": event_count,
        "issues": timeline_issues,
    }

    # -------------------------------------------------------------------------
    # Exports section
    # -------------------------------------------------------------------------
    export_count = len(case.exports)
    exports_issues: list[str] = []
    if export_count == 0:
        exports_issues.append(
            "No export bundle created — export recommended before case closure"
        )
    exports_section = {
        "present": export_count > 0,
        "count": export_count,
        "issues": exports_issues,
    }

    # -------------------------------------------------------------------------
    # Metadata section
    # -------------------------------------------------------------------------
    _key_metadata_fields = ["operator_name", "event_type", "platform_name", "platform_type"]
    missing_fields: list[str] = [
        f for f in _key_metadata_fields
        if not getattr(case, f, None)
    ]
    metadata_complete = len(missing_fields) == 0
    metadata_issues: list[str] = []
    if missing_fields:
        metadata_issues.append(f"Key contextual fields missing: {', '.join(missing_fields)}")
    metadata_section = {
        "complete": metadata_complete,
        "missing_fields": missing_fields,
        "issues": metadata_issues,
    }

    # -------------------------------------------------------------------------
    # Completeness score — profile-aware weighting
    # -------------------------------------------------------------------------
    # Each section contributes a weight; profile adjusts which sections are required.
    if profile in ("gov_mil", "enterprise_gov"):
        # Gov/mil: all sections required, exports and metadata are critical
        weights = {
            "evidence": 25,
            "analysis": 25,
            "attachments": 15,
            "hypotheses": 10,
            "timeline": 5,
            "exports": 10,
            "metadata": 10,
        }
    elif profile == "racer":
        # Racer: only evidence and analysis matter for completeness
        weights = {
            "evidence": 50,
            "analysis": 50,
            "attachments": 0,
            "hypotheses": 0,
            "timeline": 0,
            "exports": 0,
            "metadata": 0,
        }
    else:
        # Default/balanced
        weights = {
            "evidence": 20,
            "analysis": 20,
            "attachments": 10,
            "hypotheses": 15,
            "timeline": 10,
            "exports": 10,
            "metadata": 15,
        }

    section_scores = {
        "evidence": weights["evidence"] if evidence_section["present"] else 0,
        "analysis": weights["analysis"] if analysis_section["present"] else 0,
        "attachments": weights["attachments"] if attachments_section["present"] else 0,
        "hypotheses": weights["hypotheses"] if hypotheses_section["present"] else 0,
        "timeline": weights["timeline"] if timeline_section["present"] else 0,
        "exports": weights["exports"] if exports_section["present"] else 0,
        "metadata": weights["metadata"] if metadata_section["complete"] else 0,
    }
    completeness_score = sum(section_scores.values())

    # -------------------------------------------------------------------------
    # Recommendations
    # -------------------------------------------------------------------------
    recommendations: list[str] = []
    if not evidence_section["present"]:
        recommendations.append("Upload at least one flight log")
    if not analysis_section["present"] and evidence_section["present"]:
        recommendations.append("Run analysis on uploaded evidence")
    if not attachments_section["present"] and profile not in ("racer",):
        recommendations.append("Upload at least one photo attachment for visual context")
    if missing_fields:
        recommendations.append(f"Complete operator and event metadata: {', '.join(missing_fields)}")
    if not exports_section["present"] and run_count > 0:
        recommendations.append("Create an export bundle for archival before closing the case")

    return JSONResponse({
        "ok": True,
        "case_id": case_id,
        "profile": profile,
        "completeness_score": completeness_score,
        "sections": {
            "evidence": evidence_section,
            "analysis": analysis_section,
            "attachments": attachments_section,
            "hypotheses": hypotheses_section,
            "timeline": timeline_section,
            "exports": exports_section,
            "metadata": metadata_section,
        },
        "recommendations": recommendations,
    })


@router.get("/{case_id}/runs/compare")
async def compare_runs_get(
    case_id: str,
    run_a: str,
    run_b: str,
) -> JSONResponse:
    """Compare two analysis runs and return an investigator-friendly diff.

    Returns the RunComparison wrapped with an executive summary and recommendation.
    Query params: run_a={run_id}&run_b={run_id}
    """
    from goose.forensics.diff import compare_runs
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    case_dir = svc.case_dir(case_id)
    try:
        comparison = compare_runs(case_dir, run_a, run_b)
    except Exception as exc:
        logger.exception("Run comparison failed for case %s", case_id)
        raise HTTPException(status_code=500, detail=f"Compare failed: {exc}") from exc

    comp_dict = comparison.to_dict()

    # Build investigator-friendly executive summary
    risk = comparison.risk_assessment
    summary = comparison.summary

    recommendation: str
    if risk == "regression":
        sev_changes = [
            d for d in comparison.finding_differences
            if d.change_type == "severity_changed"
        ]
        plugin_area = ""
        if sev_changes:
            # Attempt to infer plugin from finding data
            plugin_area = f" — check findings: {', '.join(d.finding_id for d in sev_changes[:3])}"
        recommendation = (
            f"Run B shows regression in finding severity{plugin_area}. "
            "Review the escalated findings and compare plugin diagnostic output between runs."
        )
    elif risk == "improvement":
        recommendation = (
            "Run B shows improvement — one or more findings resolved to lower severity. "
            "Verify the improvement reflects a real fix and not a data quality reduction."
        )
    elif risk == "version_drift":
        recommendation = (
            "Only plugin version changes detected. No finding regressions. "
            "Update your baseline run to this version to avoid future false drift alerts."
        )
    else:
        recommendation = (
            "Runs are equivalent. No action required."
        )

    return JSONResponse({
        "ok": True,
        "comparison": comp_dict,
        "executive_summary": summary,
        "risk_assessment": risk,
        "recommendation": recommendation,
    })


@router.patch("/{case_id}/status")
async def update_case_status(case_id: str, body: UpdateStatusRequest) -> JSONResponse:
    """Update the status of a case."""
    try:
        status = CaseStatus(body.status)
    except ValueError as exc:
        valid = [s.value for s in CaseStatus]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Valid values: {valid}",
        ) from exc
    try:
        from goose.web.cases_api import get_service
        svc = get_service()
        case = svc.update_status(case_id, status, actor=body.actor)
        return JSONResponse({"ok": True, "case": _serialize_case_summary(case)})
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
