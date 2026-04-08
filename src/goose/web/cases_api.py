"""Case-oriented API routes for Goose forensic workflow.

These routes are the real analysis path from Sprint 2 forward.
All evidence is ingested immutably through CaseService.

Routes:
  POST /api/cases                          — create case
  GET  /api/cases                          — list cases
  GET  /api/cases/{case_id}                — get case detail
  POST /api/cases/{case_id}/evidence       — ingest evidence (multipart)
  GET  /api/cases/{case_id}/evidence       — list evidence items
  POST /api/cases/{case_id}/analyze        — run analysis on case evidence
  GET  /api/cases/{case_id}/findings       — get findings from last analysis
  GET  /api/cases/{case_id}/audit          — get audit log entries
  PATCH /api/cases/{case_id}/status        — update case status

Sprint 2 — GUI/API Case Workflow
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from goose.forensics import CaseService, CaseStatus
from goose.forensics.models import AnalysisRun

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


# ---------------------------------------------------------------------------
# Request/Response models
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

@router.post("", status_code=201)
async def create_case(body: CreateCaseRequest) -> JSONResponse:
    """Create a new forensic case and return its metadata."""
    try:
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


@router.get("")
async def list_cases() -> JSONResponse:
    """Return all cases (summary only) sorted by creation time descending."""
    try:
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
        svc = get_service()
        case = svc.get_case(case_id)
        return JSONResponse({"ok": True, "case": _serialize_case_detail(case)})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    except Exception as exc:
        logger.exception("Failed to get case %s", case_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{case_id}/evidence", status_code=201)
async def ingest_evidence(
    case_id: str,
    file: UploadFile = File(...),
    notes: str = "",
) -> JSONResponse:
    """Ingest a file as immutable evidence into the case.

    The file is hashed (SHA-256 + SHA-512), stored read-only, and the
    evidence manifest is updated. Original bytes are preserved exactly.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    try:
        svc = get_service()
        # Verify case exists first
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


@router.post("/{case_id}/analyze")
async def analyze_case(case_id: str) -> JSONResponse:
    """Run all plugins against the first evidence item in the case.

    Returns findings, overall score, metadata, and timeseries (same shape as
    the legacy /api/analyze response so existing frontend code works unchanged).
    """
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    if not case.evidence_items:
        raise HTTPException(
            status_code=422,
            detail="No evidence ingested yet. Upload a flight log first.",
        )

    # Use the most recently ingested evidence item
    ev = case.evidence_items[-1]
    evidence_path = ev.stored_path

    try:
        from goose.web.app import (
            _compute_overall_score,
            _extract_timeseries,
            _finding_to_dict,
            _format_duration,
            _try_all_parsers,
        )
        from goose.parsers.ulog import ULogParser

        # Parse
        flight = None
        parse_error: str | None = None
        try:
            ulog = ULogParser()
            if ulog.can_parse(evidence_path):
                flight = ulog.parse(evidence_path)
        except Exception as exc:
            parse_error = str(exc)
            logger.warning("ULogParser failed on case evidence: %s", exc)

        if flight is None:
            flight, parse_error = _try_all_parsers(evidence_path, parse_error)

        if flight is None:
            raise HTTPException(
                status_code=422,
                detail=f"Could not parse evidence file '{ev.filename}'. "
                       f"Supported: .ulg. Error: {parse_error}",
            )

        # Run plugins
        from goose.plugins.registry import load_plugins
        plugins = load_plugins()
        all_findings: list[Any] = []
        plugin_errors: list[dict[str, str]] = []
        plugin_versions: dict[str, str] = {}

        for plugin in plugins:
            plugin_versions[plugin.name] = getattr(plugin, "version", "unknown")
            try:
                findings = plugin.analyze(flight, {})
                all_findings.extend(findings)
            except Exception as exc:
                logger.warning("Plugin %s failed: %s", plugin.name, exc)
                plugin_errors.append({"plugin": plugin.name, "error": str(exc)})

        overall_score = _compute_overall_score(all_findings)

        # Record analysis run in case
        import uuid
        from datetime import datetime
        from goose import __version__

        run = AnalysisRun(
            run_id=f"RUN-{uuid.uuid4().hex[:8].upper()}",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            plugin_versions=plugin_versions,
            ruleset_version=None,
            findings_count=len([f for f in all_findings if f.severity != "pass"]),
            status="completed",
            engine_version=__version__,
        )
        case.analysis_runs.append(run)
        svc.save_case(case)

        # Persist findings to analysis/
        import json
        analysis_dir = svc.case_dir(case_id) / "analysis"
        (analysis_dir / "findings.json").write_text(
            json.dumps([_finding_to_dict(f) for f in all_findings], indent=2),
            encoding="utf-8",
        )

        # Build response (same shape as /api/analyze for shim compatibility)
        meta = flight.metadata
        duration_sec = meta.duration_sec
        duration_str = _format_duration(duration_sec)
        start_time_str = meta.start_time_utc.isoformat() if meta.start_time_utc else None

        findings_by_severity: dict[str, int] = {"critical": 0, "warning": 0, "info": 0, "pass": 0}
        for f in all_findings:
            sev = f.severity if f.severity in findings_by_severity else "info"
            findings_by_severity[sev] += 1

        try:
            timeseries = _extract_timeseries(flight)
        except Exception as ts_exc:
            logger.warning("Time-series extraction failed: %s", ts_exc)
            timeseries = {}

        try:
            from goose.core.narrative import generate_narrative, generate_human_narrative
            narr_meta = {
                "duration_str": duration_str,
                "vehicle_type": meta.vehicle_type,
                "primary_mode": flight.primary_mode,
                "firmware_version": meta.firmware_version,
                "hardware": meta.hardware,
                "crashed": flight.crashed,
            }
            narrative = generate_narrative(all_findings, metadata=narr_meta, overall_score=overall_score)
            narrative_human = generate_human_narrative(all_findings, metadata=narr_meta, overall_score=overall_score)
        except Exception:
            narrative = narrative_human = None

        return JSONResponse({
            "ok": True,
            "case_id": case_id,
            "run_id": run.run_id,
            "evidence_id": ev.evidence_id,
            "overall_score": overall_score,
            "narrative": narrative,
            "narrative_human": narrative_human,
            "timeseries": timeseries,
            "metadata": {
                "filename": ev.filename,
                "autopilot": meta.autopilot,
                "vehicle_type": meta.vehicle_type,
                "firmware_version": meta.firmware_version,
                "hardware": meta.hardware,
                "duration_sec": round(duration_sec, 1),
                "duration_str": duration_str,
                "start_time_utc": start_time_str,
                "log_format": meta.log_format,
                "motor_count": meta.motor_count,
                "primary_mode": flight.primary_mode,
                "crashed": flight.crashed,
            },
            "summary": {
                "total_findings": len(all_findings),
                "by_severity": findings_by_severity,
                "plugins_run": len(plugins),
                "plugin_errors": plugin_errors,
            },
            "findings": [_finding_to_dict(f) for f in all_findings],
        })

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Analysis failed for case %s", case_id)
        raise HTTPException(status_code=500, detail=f"Analysis error: {exc}") from exc


@router.get("/{case_id}/findings")
async def get_findings(case_id: str) -> JSONResponse:
    """Return findings from the most recent analysis run."""
    import json

    try:
        svc = get_service()
        svc.get_case(case_id)  # verify exists
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    findings_path = svc.case_dir(case_id) / "analysis" / "findings.json"
    if not findings_path.exists():
        return JSONResponse({"ok": True, "findings": [], "count": 0})

    try:
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        return JSONResponse({"ok": True, "findings": findings, "count": len(findings)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}/audit")
async def get_audit_log(case_id: str) -> JSONResponse:
    """Return the audit log for a case (oldest first)."""
    try:
        svc = get_service()
        svc.get_case(case_id)  # verify exists
        entries = svc.get_audit_log(case_id)
        return JSONResponse({
            "ok": True,
            "audit": [e.to_dict() for e in entries],
            "count": len(entries),
        })
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    except Exception as exc:
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
        svc = get_service()
        case = svc.update_status(case_id, status, actor=body.actor)
        return JSONResponse({"ok": True, "case": _serialize_case_summary(case)})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
