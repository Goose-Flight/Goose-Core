"""Quick Analysis routes (v11 Strategy Sprint).

Quick Analysis is a **session-only triage flow**. The user uploads a flight
log, chooses a profile, and receives findings + hypotheses + a summary —
**without** creating a persistent case, without hashing evidence into the
case store, and without writing to the forensic audit trail.

The forensic core is still used:
- Same parser framework (goose.parsers.detect.parse_file)
- Same plugin pipeline (goose.plugins.PLUGIN_REGISTRY)
- Same canonical models (ForensicFinding, Hypothesis)
- Same lifting layer (generate_hypotheses, build_signal_quality)

The only thing skipped is persistence. A subsequent
``POST /api/quick-analysis/save-as-case`` endpoint lets the user promote a
quick-analysis result into a real Investigation Case.
"""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from goose import __version__
from goose.forensics.profiles import get_profile
from goose.parsers.detect import parse_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quick_analysis"])


def _new_qa_id() -> str:
    return f"QA-{uuid.uuid4().hex[:8].upper()}"


@router.post("/api/quick-analysis")
async def quick_analysis(
    file: UploadFile = File(...),
    profile: str = Form("default"),
) -> JSONResponse:
    """Run a session-only Quick Analysis.

    Accepts a multipart file upload + profile id. Parses the file via the
    formal parser contract, runs the profile's preferred plugin subset (or
    all plugins if the profile declares none), and returns findings +
    hypotheses + summary as JSON. **No case is created, no evidence is
    stored, no audit entry is written.**
    """
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

    cfg = get_profile(profile)
    qa_id = _new_qa_id()
    started_at = datetime.now()

    # Write to a temp file the parser can read; cleaned up on return.
    tmp_path: Path | None = None
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        # Enforce upload size limit
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum upload size of {settings.max_upload_mb} MiB",
            )

        with tempfile.NamedTemporaryFile(
            prefix="goose_qa_", suffix=suffix, delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            parse_result = parse_file(str(tmp_path))
        except Exception:
            logger.exception("Quick analysis parse failed for %s", Path(file.filename).name)
            raise HTTPException(
                status_code=422,
                detail="Could not parse the uploaded file. Ensure it is a valid flight log.",
            )

        if parse_result is None or not parse_result.success or parse_result.flight is None:
            errors = (
                parse_result.diagnostics.errors if parse_result is not None else ["parser returned None"]
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Could not parse '{file.filename}'.",
                    "errors": errors,
                    "supported": (
                        parse_result.diagnostics.supported if parse_result else False
                    ),
                },
            )

        flight = parse_result.flight

        # Resolve plugin subset from profile — fall back to "all" if the
        # profile declares no preference (advanced, or empty default list).
        from goose.plugins import PLUGIN_REGISTRY

        available_ids = {p.manifest.plugin_id for p in PLUGIN_REGISTRY.values()}
        wanted_ids: list[str] = []
        for pid in (cfg.default_plugins or []):
            if pid in available_ids:
                wanted_ids.append(pid)
        if not wanted_ids:
            # Advanced profile or unknown plugin_ids — run everything registered.
            wanted_ids = list(available_ids)

        plugins_to_run = [
            PLUGIN_REGISTRY[pid] for pid in wanted_ids if pid in PLUGIN_REGISTRY
        ]

        # Execute plugins. Quick Analysis uses a synthetic evidence_id since
        # no real EvidenceItem exists; this keeps the forensic contract intact
        # while clearly marking the artifacts as quick-analysis output.
        synthetic_evidence_id = f"QA-EV-{uuid.uuid4().hex[:8].upper()}"
        forensic_findings: list[Any] = []
        thin_findings: list[Any] = []
        plugin_versions: dict[str, str] = {}
        plugin_errors: list[dict[str, str]] = []

        for plugin in plugins_to_run:
            plugin_versions[plugin.name] = getattr(plugin, "version", "unknown")
            try:
                ff_list, _p_diag = plugin.forensic_analyze(
                    flight, synthetic_evidence_id, qa_id, {}, parse_result.diagnostics,
                )
                forensic_findings.extend(ff_list)
                thin = plugin.analyze(flight, {})
                thin_findings.extend(thin)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Quick analysis plugin %s failed: %s", plugin.name, exc)
                plugin_errors.append({"plugin": plugin.name, "error": str(exc)})

        from goose.core.scoring import compute_overall_score
        from goose.forensics.lifting import generate_hypotheses, build_signal_quality
        from goose.forensics.timeline import build_full_timeline
        from goose.web.timeseries_utils import extract_timeseries, extract_flight_path, extract_setpoint_path

        overall_score = compute_overall_score(thin_findings)
        hypotheses = generate_hypotheses(
            forensic_findings, run_id=qa_id, parse_diag=parse_result.diagnostics,
        )
        signal_quality = build_signal_quality(parse_result.diagnostics)
        timeline_events = build_full_timeline(flight, forensic_findings, qa_id)
        timeseries = extract_timeseries(flight)
        flight_path = extract_flight_path(flight)
        setpoint_path = extract_setpoint_path(flight)

        meta = flight.metadata
        findings_by_severity: dict[str, int] = {"critical": 0, "warning": 0, "info": 0, "pass": 0}
        for f in forensic_findings:
            sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
            if sev in findings_by_severity:
                findings_by_severity[sev] += 1

        # Flight phases
        phases_out = [
            {
                "start_time": p.start_time,
                "end_time": p.end_time,
                "phase_type": p.phase_type,
                "duration_sec": round(p.end_time - p.start_time, 1),
            }
            for p in flight.phases
        ]

        # Parameters — cap at 500 most interesting (sorted by key)
        params_sorted = dict(sorted(flight.parameters.items())[:500])

        # Flight modes used
        modes_used = list(dict.fromkeys(
            [mc.to_mode for mc in flight.mode_changes if mc.to_mode]
        ))

        completed_at = datetime.now()

        return JSONResponse({
            "ok": True,
            "quick_analysis_id": qa_id,
            "profile": cfg.to_dict(),
            "engine_version": __version__,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "persisted": False,  # explicit — no case was created
            "overall_score": overall_score,
            "metadata": {
                "filename": file.filename,
                "autopilot": meta.autopilot,
                "vehicle_type": meta.vehicle_type,
                "firmware_version": meta.firmware_version,
                "frame_type": meta.frame_type,
                "hardware": meta.hardware,
                "motor_count": meta.motor_count,
                "log_format": meta.log_format,
                "duration_sec": round(meta.duration_sec, 1),
                "start_time_utc": meta.start_time_utc.isoformat() if meta.start_time_utc else None,
                "primary_mode": flight.primary_mode,
                "modes_used": modes_used,
                "crashed": flight.crashed,
            },
            "summary": {
                "total_findings": len(forensic_findings),
                "by_severity": findings_by_severity,
                "plugins_run": len(plugins_to_run),
                "plugin_errors": plugin_errors,
                "hypotheses_count": len(hypotheses),
                "phases_count": len(phases_out),
                "parameters_count": len(flight.parameters),
                "events_count": len(flight.events),
            },
            "findings": [f.to_dict() for f in forensic_findings],
            "hypotheses": [h.to_dict() for h in hypotheses],
            "signal_quality": [sq.to_dict() for sq in signal_quality],
            "timeline": [e.to_dict() for e in timeline_events],
            "phases": phases_out,
            "parameters": params_sorted,
            "timeseries": timeseries,
            "flight_path": flight_path,
            "setpoint_path": setpoint_path,
            "parse_diagnostics": parse_result.diagnostics.to_dict(),
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Quick analysis failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


@router.post("/api/quick-analysis/save-as-case")
async def save_quick_analysis_as_case(
    file: UploadFile = File(...),
    profile: str = Form("default"),
    notes: str = Form(""),
    created_by: str = Form("gui"),
) -> JSONResponse:
    """Promote a quick-analysis result into a real Investigation Case.

    This endpoint takes the same inputs as ``/api/quick-analysis`` plus a
    ``notes`` and ``created_by`` field, creates a real case, ingests the
    file as evidence, and returns the new case detail. The client should
    then hit ``POST /api/cases/{case_id}/analyze`` to run the full
    persistent analysis pipeline.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    cfg = get_profile(profile)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.create_case(created_by=created_by, tags=[], notes=notes)
        # Stamp the profile onto the new case so the GUI can bias defaults.
        case.profile = cfg.profile_id
        svc.save_case(case)

        ev = svc.ingest_evidence_bytes(
            case_id=case.case_id,
            filename=file.filename,
            content=content,
            acquired_by=created_by,
            notes=notes,
        )
    except Exception as exc:
        logger.exception("save-as-case failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Return enough for the GUI to pivot into the case view.
    return JSONResponse({
        "ok": True,
        "case_id": case.case_id,
        "profile": cfg.profile_id,
        "evidence_id": ev.evidence_id,
        "message": "Case created. Call POST /api/cases/{case_id}/analyze to run the full pipeline.",
    }, status_code=201)
