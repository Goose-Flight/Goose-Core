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
  GET  /api/cases/{case_id}/diagnostics    — get parse diagnostics from last analysis
  GET  /api/cases/{case_id}/audit          — get audit log entries
  PATCH /api/cases/{case_id}/status        — update case status

Sprint 3 — Parser Framework and Diagnostics
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from goose import __version__
from goose.forensics import CaseService, CaseStatus
from goose.forensics.models import AnalysisRun, AuditAction, AuditEntry
from goose.parsers.detect import parse_file

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
    """Run the parser framework and all plugins against the case's evidence.

    Sprint 3: uses the formal ParseResult contract. Writes canonical artifacts
    to the case parsed/ directory. Parse diagnostics are always returned.
    """
    from goose.web.app import (
        _compute_overall_score,
        _extract_timeseries,
        _finding_to_dict,
        _format_duration,
    )

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

    ev = case.evidence_items[-1]
    evidence_path = ev.stored_path
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    started_at = datetime.now()

    # --- Audit: parse started -----------------------------------------------
    svc._append_audit(case_id, AuditEntry(
        event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
        timestamp=started_at,
        actor="api",
        action=AuditAction.PARSE_STARTED,
        object_type="evidence",
        object_id=ev.evidence_id,
        details={"evidence_path": evidence_path, "run_id": run_id},
    ))

    # --- Parse via formal contract -------------------------------------------
    try:
        parse_result = parse_file(evidence_path)
    except Exception as exc:
        logger.exception("Unexpected error from parse_file for case %s", case_id)
        parse_result = None
        _parse_exc = exc
    else:
        _parse_exc = None

    if parse_result is None:
        svc._append_audit(case_id, AuditEntry(
            event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.now(),
            actor="api",
            action=AuditAction.PARSE_FAILED,
            object_type="evidence",
            object_id=ev.evidence_id,
            details={"error": str(_parse_exc)},
            success=False,
            error=str(_parse_exc),
        ))
        raise HTTPException(status_code=500, detail=f"Internal parse error: {_parse_exc}")

    # Attach evidence_id to provenance
    if parse_result.provenance:
        parse_result.provenance.source_evidence_id = ev.evidence_id

    # --- Persist parsed/ artifacts -------------------------------------------
    case_dir = svc.case_dir(case_id)
    parsed_dir = case_dir / "parsed"
    parsed_dir.mkdir(exist_ok=True)

    diag_path = parsed_dir / "parse_diagnostics.json"
    diag_path.write_text(parse_result.diagnostics.to_json(), encoding="utf-8")

    if parse_result.provenance:
        prov_path = parsed_dir / "provenance.json"
        prov_path.write_text(
            json.dumps(parse_result.provenance.to_dict(), indent=2),
            encoding="utf-8",
        )

    # --- Audit: parse completed/failed ---------------------------------------
    parse_audit_action = AuditAction.PARSE_COMPLETED if parse_result.success else AuditAction.PARSE_FAILED
    svc._append_audit(case_id, AuditEntry(
        event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
        timestamp=datetime.now(),
        actor="api",
        action=parse_audit_action,
        object_type="evidence",
        object_id=ev.evidence_id,
        details={
            "parser": parse_result.diagnostics.parser_selected,
            "parser_confidence": parse_result.diagnostics.parser_confidence,
            "warnings": len(parse_result.diagnostics.warnings),
            "errors": len(parse_result.diagnostics.errors),
        },
        success=parse_result.success,
        error="; ".join(parse_result.diagnostics.errors) if not parse_result.success else None,
    ))

    if not parse_result.success:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Could not parse evidence file '{ev.filename}'.",
                "errors": parse_result.diagnostics.errors,
                "supported": parse_result.diagnostics.supported,
                "detected_format": parse_result.diagnostics.detected_format,
            },
        )

    flight = parse_result.flight  # guaranteed non-None here

    # --- Audit: analysis started ---------------------------------------------
    svc._append_audit(case_id, AuditEntry(
        event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
        timestamp=datetime.now(),
        actor="api",
        action=AuditAction.ANALYSIS_STARTED,
        object_type="analysis",
        object_id=run_id,
        details={"evidence_id": ev.evidence_id},
    ))

    # --- Run plugins (Sprint 5: forensic contract) ----------------------------
    from goose.plugins import PLUGIN_REGISTRY
    from goose.plugins.contract import PluginDiagnostics as PDiag
    plugins = list(PLUGIN_REGISTRY.values())
    all_findings: list[Any] = []        # thin findings for backward compat
    forensic_findings: list[Any] = []   # ForensicFinding from new contract
    plugin_errors: list[dict[str, str]] = []
    plugin_versions: dict[str, str] = {}
    all_plugin_diagnostics: list[PDiag] = []

    for plugin in plugins:
        plugin_versions[plugin.name] = getattr(plugin, "version", "unknown")
        try:
            ff_list, p_diag = plugin.forensic_analyze(
                flight, ev.evidence_id, run_id, {}, parse_result.diagnostics,
            )
            forensic_findings.extend(ff_list)
            all_plugin_diagnostics.append(p_diag)
            # Also run thin findings for backward compat (narrative, overall score)
            thin = plugin.analyze(flight, {})
            all_findings.extend(thin)
        except Exception as exc:
            logger.warning("Plugin %s failed: %s", plugin.name, exc)
            plugin_errors.append({"plugin": plugin.name, "error": str(exc)})

    overall_score = _compute_overall_score(all_findings)
    completed_at = datetime.now()

    # --- Hypotheses and signal quality (still use lifting layer) -------------
    from goose.forensics.lifting import generate_hypotheses, build_signal_quality
    hypotheses = generate_hypotheses(forensic_findings, run_id=run_id)
    signal_quality = build_signal_quality(parse_result.diagnostics)

    # --- Persist analysis/ artifacts -----------------------------------------
    analysis_dir = case_dir / "analysis"
    analysis_dir.mkdir(exist_ok=True)

    # findings.json — forensic-grade (ForensicFinding), versioned
    findings_bundle = {
        "findings_version": "2.0",  # v1 was thin findings; v2 is ForensicFinding
        "run_id": run_id,
        "evidence_id": ev.evidence_id,
        "generated_at": completed_at.isoformat(),
        "findings": [f.to_dict() for f in forensic_findings],
    }
    (analysis_dir / "findings.json").write_text(
        json.dumps(findings_bundle, indent=2), encoding="utf-8"
    )

    # hypotheses.json — first-class case artifact
    hypotheses_bundle = {
        "hypotheses_version": "1.0",
        "run_id": run_id,
        "generated_at": completed_at.isoformat(),
        "hypotheses": [h.to_dict() for h in hypotheses],
    }
    (analysis_dir / "hypotheses.json").write_text(
        json.dumps(hypotheses_bundle, indent=2), encoding="utf-8"
    )

    # signal_quality.json — stream reliability from parse diagnostics
    sq_bundle = {
        "signal_quality_version": "1.0",
        "run_id": run_id,
        "generated_at": completed_at.isoformat(),
        "streams": [sq.to_dict() for sq in signal_quality],
    }
    (analysis_dir / "signal_quality.json").write_text(
        json.dumps(sq_bundle, indent=2), encoding="utf-8"
    )

    plugin_diag = {
        "run_id": run_id,
        "diagnostics_version": "2.0",
        "plugins_run": [{"name": p.name, "version": plugin_versions[p.name]} for p in plugins],
        "plugin_errors": plugin_errors,
        "plugin_diagnostics": [pd.to_dict() for pd in all_plugin_diagnostics],
        "overall_score": overall_score,
        "engine_version": __version__,
        "evidence_id": ev.evidence_id,
        "parser_selected": parse_result.diagnostics.parser_selected,
        "parser_confidence": parse_result.diagnostics.parser_confidence,
        "parser_confidence_scope": parse_result.diagnostics.confidence_scope,
    }
    (analysis_dir / "plugin_diagnostics.json").write_text(
        json.dumps(plugin_diag, indent=2), encoding="utf-8"
    )

    # --- Record analysis run in case -----------------------------------------
    run = AnalysisRun(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        plugin_versions=plugin_versions,
        ruleset_version=None,
        findings_count=len([f for f in forensic_findings if f.severity != "pass"]),
        status="completed",
        engine_version=__version__,
    )
    case.analysis_runs.append(run)
    svc.save_case(case)

    # --- Audit: analysis completed -------------------------------------------
    svc._append_audit(case_id, AuditEntry(
        event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
        timestamp=completed_at,
        actor="api",
        action=AuditAction.ANALYSIS_COMPLETED,
        object_type="analysis",
        object_id=run_id,
        details={
            "findings_count": run.findings_count,
            "plugins_run": len(plugins),
            "overall_score": overall_score,
        },
    ))

    # --- Build response ------------------------------------------------------
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
        from goose.core.narrative import generate_human_narrative, generate_narrative
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
        "parse_diagnostics": parse_result.diagnostics.to_dict(),
        "summary": {
            "total_findings": len(all_findings),
            "by_severity": findings_by_severity,
            "plugins_run": len(plugins),
            "plugin_errors": plugin_errors,
            "hypotheses_count": len(hypotheses),
        },
        # Forensic-grade findings (ForensicFinding with evidence references)
        "findings": [f.to_dict() for f in forensic_findings],
        # Hypothesis candidates
        "hypotheses": [h.to_dict() for h in hypotheses],
    })


@router.get("/{case_id}/findings")
async def get_findings(case_id: str) -> JSONResponse:
    """Return forensic findings from the most recent analysis run.

    Returns the versioned findings bundle (findings_version field).
    v2.0+ bundles contain ForensicFinding objects with evidence references.
    v1.0 bundles (thin findings from Sprint 2/3) are returned as-is for compat.
    """
    try:
        svc = get_service()
        svc.get_case(case_id)  # verify exists
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    findings_path = svc.case_dir(case_id) / "analysis" / "findings.json"
    if not findings_path.exists():
        return JSONResponse({"ok": True, "findings": [], "count": 0, "findings_version": None})

    try:
        bundle = json.loads(findings_path.read_text(encoding="utf-8"))
        # v2+ bundle: has findings_version + findings array
        if isinstance(bundle, dict) and "findings" in bundle:
            findings = bundle["findings"]
            return JSONResponse({
                "ok": True,
                "findings_version": bundle.get("findings_version"),
                "run_id": bundle.get("run_id"),
                "evidence_id": bundle.get("evidence_id"),
                "findings": findings,
                "count": len(findings),
            })
        # v1 compat: was a plain list
        if isinstance(bundle, list):
            return JSONResponse({"ok": True, "findings": bundle, "count": len(bundle), "findings_version": "1.0"})
        return JSONResponse({"ok": True, "findings": [], "count": 0, "findings_version": None})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}/hypotheses")
async def get_hypotheses(case_id: str) -> JSONResponse:
    """Return hypothesis candidates from the most recent analysis run."""
    try:
        svc = get_service()
        svc.get_case(case_id)  # verify exists
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    hyp_path = svc.case_dir(case_id) / "analysis" / "hypotheses.json"
    if not hyp_path.exists():
        return JSONResponse({"ok": True, "hypotheses": [], "count": 0})

    try:
        bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
        hyps = bundle.get("hypotheses", []) if isinstance(bundle, dict) else []
        return JSONResponse({
            "ok": True,
            "hypotheses_version": bundle.get("hypotheses_version") if isinstance(bundle, dict) else None,
            "run_id": bundle.get("run_id") if isinstance(bundle, dict) else None,
            "hypotheses": hyps,
            "count": len(hyps),
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}/diagnostics")
async def get_diagnostics(case_id: str) -> JSONResponse:
    """Return parse diagnostics from the most recent analysis run."""
    try:
        svc = get_service()
        svc.get_case(case_id)  # verify exists
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    diag_path = svc.case_dir(case_id) / "parsed" / "parse_diagnostics.json"
    if not diag_path.exists():
        return JSONResponse({"ok": True, "diagnostics": None, "message": "No analysis run yet."})

    try:
        diag_data = json.loads(diag_path.read_text(encoding="utf-8"))
        return JSONResponse({"ok": True, "diagnostics": diag_data})
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


@router.get("/{case_id}/plugins")
async def get_plugins(case_id: str) -> JSONResponse:
    """Return plugin manifests and (if available) per-plugin run diagnostics."""
    try:
        svc = get_service()
        svc.get_case(case_id)  # verify exists
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    from goose.plugins import get_plugin_manifests
    manifests = [m.to_dict() for m in get_plugin_manifests()]

    # Try to load plugin run diagnostics from last analysis
    plugin_run_info: list[dict[str, Any]] = []
    diag_path = svc.case_dir(case_id) / "analysis" / "plugin_diagnostics.json"
    if diag_path.exists():
        try:
            bundle = json.loads(diag_path.read_text(encoding="utf-8"))
            plugin_run_info = bundle.get("plugin_diagnostics", [])
        except Exception:
            pass

    return JSONResponse({
        "ok": True,
        "manifests": manifests,
        "plugin_run_info": plugin_run_info,
        "count": len(manifests),
    })


@router.get("/{case_id}/timeline")
async def get_timeline(case_id: str) -> JSONResponse:
    """Construct a timeline from flight phases, mode changes, events, and findings."""
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    events: list[dict[str, Any]] = []
    case_dir = svc.case_dir(case_id)

    # Load findings
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle = json.loads(findings_path.read_text(encoding="utf-8"))
            for f in bundle.get("findings", []):
                t = f.get("start_time") or f.get("end_time")
                if t is not None:
                    events.append({
                        "time": t,
                        "type": "finding",
                        "label": f.get("title", ""),
                        "severity": f.get("severity"),
                        "finding_id": f.get("finding_id"),
                        "description": f.get("description", ""),
                    })
        except Exception:
            pass

    # Load parse diagnostics for stream info (we don't have a full Flight here,
    # but we can read persisted artifacts)
    diag_path = case_dir / "parsed" / "parse_diagnostics.json"
    if diag_path.exists():
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            # If there are mode changes or events serialized, use them
            for mc in diag.get("mode_changes", []):
                events.append({
                    "time": mc.get("timestamp", 0),
                    "type": "mode",
                    "label": f"{mc.get('from_mode', '?')} -> {mc.get('to_mode', '?')}",
                    "severity": None,
                    "finding_id": None,
                    "description": "Flight mode change",
                })
        except Exception:
            pass

    # Load provenance for additional context
    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            duration = prov.get("flight_duration_sec")
            if duration:
                events.append({
                    "time": 0,
                    "type": "phase",
                    "label": "Flight start",
                    "severity": None,
                    "finding_id": None,
                    "description": f"Total duration: {duration}s",
                })
                events.append({
                    "time": duration,
                    "type": "phase",
                    "label": "Flight end",
                    "severity": None,
                    "finding_id": None,
                    "description": "",
                })
        except Exception:
            pass

    events.sort(key=lambda e: e["time"])
    return JSONResponse({
        "ok": True,
        "timeline_version": "1.0",
        "events": events,
        "count": len(events),
        "message": "Timeline constructed from available case artifacts." if events else "No parsed data available yet. Run analysis first.",
    })


@router.get("/{case_id}/charts/data")
async def get_charts_data(case_id: str, streams: str = "", start: float = 0.0, end: float = 0.0) -> JSONResponse:
    """Return time-series data for requested streams from canonical flight data.

    Query params: ?streams=battery_voltage,altitude_m&start=0&end=100
    """
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    case_dir = svc.case_dir(case_id)

    # Look for canonical flight data JSON persisted during analysis
    # The analyze route persists parse_diagnostics and provenance but not
    # raw time-series as JSON. We need to re-parse or look for cached data.
    # For now, try to load from a cached charts_data.json if available,
    # or re-extract from the evidence file.

    result_streams: dict[str, Any] = {}
    stream_list = [s.strip() for s in streams.split(",") if s.strip()]

    # Try cached canonical flight data
    canonical_path = case_dir / "parsed" / "canonical_flight.json"
    if canonical_path.exists():
        try:
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            for stream_name in stream_list:
                if stream_name in canonical:
                    sd = canonical[stream_name]
                    times = sd.get("times", [])
                    values = sd.get("values", [])
                    units = sd.get("units", "")
                    # Apply time filter
                    if end > start and times:
                        filtered_t = []
                        filtered_v = []
                        for t, v in zip(times, values):
                            if start <= t <= end:
                                filtered_t.append(t)
                                filtered_v.append(v)
                        times = filtered_t
                        values = filtered_v
                    result_streams[stream_name] = {
                        "times": times,
                        "values": values,
                        "units": units,
                    }
        except Exception:
            pass

    # If no canonical file, try re-parsing evidence to extract streams
    if not result_streams and stream_list:
        ev_dir = case_dir / "evidence"
        if ev_dir.exists():
            ev_files = list(ev_dir.iterdir())
            if ev_files:
                try:
                    from goose.parsers.detect import parse_file
                    pr = parse_file(str(ev_files[0]))
                    if pr and pr.success and pr.flight:
                        flight = pr.flight
                        # Map requested stream names to Flight attributes
                        _STREAM_ATTR_MAP = {
                            "battery_voltage": ("battery", "voltage", "V"),
                            "altitude_m": ("position", "alt_rel", "m"),
                            "altitude_msl": ("position", "alt_msl", "m"),
                            "velocity_m_s": ("velocity", "velocity", "m/s"),
                            "roll_deg": ("attitude", "roll", "rad"),
                            "pitch_deg": ("attitude", "pitch", "rad"),
                            "yaw_deg": ("attitude", "yaw", "rad"),
                            "motor_0": ("motors", "output_0", ""),
                            "gps_nsats": ("gps", "satellites_visible", ""),
                            "vibration_x": ("vibration", "accel_x", "m/s2"),
                            "battery_current": ("battery", "current", "A"),
                            "battery_remaining": ("battery", "remaining_pct", "%"),
                        }
                        for stream_name in stream_list:
                            if stream_name in _STREAM_ATTR_MAP:
                                attr, col, units = _STREAM_ATTR_MAP[stream_name]
                                df = getattr(flight, attr, None)
                                if df is not None and not df.empty and "timestamp" in df.columns and col in df.columns:
                                    times = df["timestamp"].tolist()
                                    values = df[col].tolist()
                                    # Clean NaN/Inf
                                    clean_t, clean_v = [], []
                                    for t, v in zip(times, values):
                                        if t is not None and v is not None:
                                            try:
                                                tf = float(t)
                                                vf = float(v)
                                                if not (math.isnan(tf) or math.isinf(tf) or math.isnan(vf) or math.isinf(vf)):
                                                    if end > start:
                                                        if start <= tf <= end:
                                                            clean_t.append(tf)
                                                            clean_v.append(vf)
                                                    else:
                                                        clean_t.append(tf)
                                                        clean_v.append(vf)
                                            except (TypeError, ValueError):
                                                pass
                                    result_streams[stream_name] = {
                                        "times": clean_t,
                                        "values": clean_v,
                                        "units": units,
                                    }
                except Exception as exc:
                    logger.warning("Chart data re-parse failed: %s", exc)

    return JSONResponse({
        "ok": True,
        "streams": result_streams,
        "available_streams": [
            "battery_voltage", "altitude_m", "altitude_msl", "velocity_m_s",
            "roll_deg", "pitch_deg", "yaw_deg", "motor_0",
            "gps_nsats", "vibration_x", "battery_current", "battery_remaining",
        ],
        "message": "" if result_streams else "No chart data available. Run analysis first or request valid stream names.",
    })


@router.get("/{case_id}/exports")
async def get_exports(case_id: str) -> JSONResponse:
    """Return export history from exports/ directory and case metadata."""
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    exports_dir = svc.case_dir(case_id) / "exports"
    export_files: list[dict[str, Any]] = []
    if exports_dir.exists():
        for f in sorted(exports_dir.iterdir()):
            if f.is_file():
                stat = f.stat()
                export_files.append({
                    "filename": f.name,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })

    return JSONResponse({
        "ok": True,
        "exports": export_files,
        "count": len(export_files),
        "case_id": case_id,
    })


@router.post("/{case_id}/exports/bundle")
async def create_export_bundle(case_id: str) -> JSONResponse:
    """Create a JSON case bundle export in exports/ directory."""
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    case_dir = svc.case_dir(case_id)
    exports_dir = case_dir / "exports"
    exports_dir.mkdir(exist_ok=True)

    bundle: dict[str, Any] = {
        "bundle_version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "engine_version": __version__,
        "case": _serialize_case_detail(case),
    }

    # Include evidence manifest
    bundle["evidence_manifest"] = [_serialize_evidence(ev) for ev in case.evidence_items]

    # Include findings
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle["findings"] = json.loads(findings_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["findings"] = None

    # Include hypotheses
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle["hypotheses"] = json.loads(hyp_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["hypotheses"] = None

    # Include plugin diagnostics
    pd_path = case_dir / "analysis" / "plugin_diagnostics.json"
    if pd_path.exists():
        try:
            bundle["plugin_diagnostics"] = json.loads(pd_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["plugin_diagnostics"] = None

    # Include provenance
    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            bundle["provenance"] = json.loads(prov_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["provenance"] = None

    # Include signal quality
    sq_path = case_dir / "analysis" / "signal_quality.json"
    if sq_path.exists():
        try:
            bundle["signal_quality"] = json.loads(sq_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["signal_quality"] = None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"case_bundle_{case_id}_{ts}.json"
    filepath = exports_dir / filename
    filepath.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")

    return JSONResponse({
        "ok": True,
        "filename": filename,
        "path": str(filepath),
        "size_bytes": filepath.stat().st_size,
    })


@router.get("/{case_id}/exports/files/{filename}")
async def get_export_file(case_id: str, filename: str) -> JSONResponse:
    """Serve an export file from the exports/ directory."""
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    filepath = svc.case_dir(case_id) / "exports" / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail=f"Export file not found: {filename}")

    # Security: ensure the filename doesn't traverse directories
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    from fastapi.responses import FileResponse
    return FileResponse(str(filepath), media_type="application/json", filename=filename)


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
