"""Analysis, findings, hypotheses, plugins, and diagnostics routes.

Extracted from cases_api.py during API modularization sprint.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from goose import __version__
from goose.forensics.models import AnalysisRun, AuditAction, AuditEntry
from goose.parsers.detect import parse_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


@router.post("/{case_id}/analyze")
async def analyze_case(case_id: str) -> JSONResponse:
    """Run the parser framework and all plugins against the case's evidence."""
    from goose.web.app import (
        _compute_overall_score,
        _extract_timeseries,
        _finding_to_dict,
        _format_duration,
    )
    from goose.web.cases_api import get_service

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
    from goose.plugins.trust import TrustPolicy, fingerprint_plugin

    plugins = list(PLUGIN_REGISTRY.values())
    all_findings: list[Any] = []
    forensic_findings: list[Any] = []
    plugin_errors: list[dict[str, str]] = []
    plugin_versions: dict[str, str] = {}
    all_plugin_diagnostics: list[PDiag] = []
    plugin_fingerprints: dict[str, str] = {}

    # Compute fingerprints and apply trust policy
    trust_policy = TrustPolicy()
    for plugin in plugins:
        plugin_versions[plugin.name] = getattr(plugin, "version", "unknown")
        fp = fingerprint_plugin(plugin)
        plugin_fingerprints[plugin.manifest.plugin_id] = fp

        # Evaluate trust policy
        allowed, reason = trust_policy.evaluate(plugin.manifest, fp)
        if not allowed:
            all_plugin_diagnostics.append(PDiag(
                plugin_id=plugin.manifest.plugin_id,
                plugin_version=plugin.manifest.version,
                run_id=run_id,
                executed=False,
                blocked=True,
                block_reason=reason,
                trust_state=plugin.manifest.trust_state.value,
            ))
            continue

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

    # findings.json
    findings_bundle = {
        "findings_version": "2.0",
        "run_id": run_id,
        "evidence_id": ev.evidence_id,
        "generated_at": completed_at.isoformat(),
        "findings": [f.to_dict() for f in forensic_findings],
    }
    (analysis_dir / "findings.json").write_text(
        json.dumps(findings_bundle, indent=2), encoding="utf-8"
    )

    # hypotheses.json
    hypotheses_bundle = {
        "hypotheses_version": "1.0",
        "run_id": run_id,
        "generated_at": completed_at.isoformat(),
        "hypotheses": [h.to_dict() for h in hypotheses],
    }
    (analysis_dir / "hypotheses.json").write_text(
        json.dumps(hypotheses_bundle, indent=2), encoding="utf-8"
    )

    # signal_quality.json
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
        "plugin_fingerprints": plugin_fingerprints,
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

    # --- Write tuning profile used for this run ------------------------------
    from goose.forensics.tuning import TuningProfile
    tuning_profile = TuningProfile.default()
    (analysis_dir / "tuning_profile.json").write_text(
        json.dumps(tuning_profile.to_dict(), indent=2), encoding="utf-8",
    )

    # --- Record analysis run in case -----------------------------------------
    # Collect trust states and plugin ids
    plugin_trust_states: dict[str, str] = {}
    plugin_ids_used: list[str] = []
    for plugin in plugins:
        plugin_ids_used.append(plugin.manifest.plugin_id)
        plugin_trust_states[plugin.manifest.plugin_id] = plugin.manifest.trust_state.value

    critical_count = sum(1 for f in forensic_findings if f.severity == "critical")
    warning_count = sum(1 for f in forensic_findings if f.severity == "warning")

    parser_name = ""
    parser_version = ""
    if parse_result.provenance:
        parser_name = parse_result.provenance.parser_name
        parser_version = parse_result.provenance.parser_version

    run = AnalysisRun(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        plugin_versions=plugin_versions,
        ruleset_version=None,
        findings_count=len([f for f in forensic_findings if f.severity != "pass"]),
        status="completed",
        engine_version=__version__,
        tuning_profile=tuning_profile.profile_id,
        case_id=case_id,
        evidence_id=ev.evidence_id,
        parser_name=parser_name,
        parser_version=parser_version,
        plugin_ids_used=plugin_ids_used,
        plugin_trust_states=plugin_trust_states,
        tuning_profile_id=tuning_profile.profile_id,
        tuning_profile_version=tuning_profile.version,
        critical_count=critical_count,
        warning_count=warning_count,
        hypotheses_count=len(hypotheses),
        is_replay=False,
    )
    case = svc.get_case(case_id)  # refresh
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
        "findings": [f.to_dict() for f in forensic_findings],
        "hypotheses": [h.to_dict() for h in hypotheses],
    })


@router.get("/{case_id}/findings")
async def get_findings(case_id: str) -> JSONResponse:
    """Return forensic findings from the most recent analysis run."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    findings_path = svc.case_dir(case_id) / "analysis" / "findings.json"
    if not findings_path.exists():
        return JSONResponse({"ok": True, "findings": [], "count": 0, "findings_version": None})

    try:
        bundle = json.loads(findings_path.read_text(encoding="utf-8"))
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
        if isinstance(bundle, list):
            return JSONResponse({"ok": True, "findings": bundle, "count": len(bundle), "findings_version": "1.0"})
        return JSONResponse({"ok": True, "findings": [], "count": 0, "findings_version": None})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{case_id}/hypotheses")
async def get_hypotheses(case_id: str) -> JSONResponse:
    """Return hypothesis candidates from the most recent analysis run."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
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
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
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
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
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
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    from goose.plugins import PLUGIN_REGISTRY, get_plugin_manifests
    from goose.plugins.trust import TrustPolicy, fingerprint_plugin

    manifests = []
    trust_policy = TrustPolicy()
    for m in get_plugin_manifests():
        md = m.to_dict()
        # Compute fingerprint for trust visibility
        plugin_inst = PLUGIN_REGISTRY.get(m.plugin_id)
        if plugin_inst:
            fp = fingerprint_plugin(plugin_inst)
            md["computed_fingerprint"] = fp
            md["trust_verified"] = (
                m.trust_state == "builtin_trusted"
                or (m.sha256_hash and m.sha256_hash == fp)
            )
        else:
            md["computed_fingerprint"] = ""
            md["trust_verified"] = False
        manifests.append(md)

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
        "policy_mode": trust_policy.mode.value,
    })
