"""Exports, bundles, replay verification, and report generation routes.

Extracted from cases_api.py + new replay/export features from hardening sprint.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from goose import __version__
from goose.forensics.models import AuditAction, AuditEntry, CaseExport
from goose.forensics.reports import (
    AnomalyReport,
    CrashMishapReport,
    EvidenceManifestReport,
    ForensicCaseReport,
    MissionSummaryReport,
    QAValidationReport,
    QuickAnalysisSummary,
    ReplayMatchState,
    ReplayVerificationReport,
    ServiceRepairSummary,
    generate_evidence_manifest_report,
    generate_forensic_case_report,
    generate_qa_validation_report,
    generate_quick_analysis_summary,
    generate_service_repair_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["exports"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class VerifyReplayRequest(BaseModel):
    bundle_filename: str


# ---------------------------------------------------------------------------
# Serializers (shared with cases module)
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


def _serialize_case_detail(case: Any) -> dict[str, Any]:
    from goose.web.routes.cases import _serialize_case_detail as _detail
    return _detail(case)


# ---------------------------------------------------------------------------
# Existing routes (migrated from cases_api.py)
# ---------------------------------------------------------------------------

@router.get("/{case_id}/exports")
async def get_exports(case_id: str) -> JSONResponse:
    """Return export history from exports/ directory and case metadata."""
    from goose.web.cases_api import get_service
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
    """Create a replayable JSON case bundle export in exports/ directory.

    Hardening sprint: enhanced bundle format with bundle_id, case_metadata,
    replay_metadata, and export history tracking in case.json.
    """
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    case_dir = svc.case_dir(case_id)
    exports_dir = case_dir / "exports"
    exports_dir.mkdir(exist_ok=True)

    bundle_id = f"BDL-{uuid.uuid4().hex[:8].upper()}"
    exported_at = datetime.now().isoformat()

    bundle: dict[str, Any] = {
        "bundle_version": "1.0",
        "bundle_id": bundle_id,
        "exported_at": exported_at,
        "case_id": case_id,
        "engine_version": __version__,
        "case_metadata": {
            "case_id": case.case_id,
            "created_at": case.created_at.isoformat(),
            "created_by": case.created_by,
            "status": case.status.value,
            "tags": case.tags,
            "notes": case.notes,
            "engine_version": case.engine_version,
        },
    }

    # Include evidence manifest
    manifest_path = case_dir / "manifests" / "evidence_manifest.json"
    if manifest_path.exists():
        try:
            bundle["evidence_manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["evidence_manifest"] = [_serialize_evidence(ev) for ev in case.evidence_items]
    else:
        bundle["evidence_manifest"] = [_serialize_evidence(ev) for ev in case.evidence_items]

    # Include parse diagnostics
    pd_parse_path = case_dir / "parsed" / "parse_diagnostics.json"
    if pd_parse_path.exists():
        try:
            bundle["parse_diagnostics"] = json.loads(pd_parse_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["parse_diagnostics"] = None
    else:
        bundle["parse_diagnostics"] = None

    # Include provenance
    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            bundle["provenance"] = json.loads(prov_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["provenance"] = None
    else:
        bundle["provenance"] = None

    # Include findings
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle["findings"] = json.loads(findings_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["findings"] = None
    else:
        bundle["findings"] = None

    # Include hypotheses
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle["hypotheses"] = json.loads(hyp_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["hypotheses"] = None
    else:
        bundle["hypotheses"] = None

    # Include signal quality
    sq_path = case_dir / "analysis" / "signal_quality.json"
    if sq_path.exists():
        try:
            bundle["signal_quality"] = json.loads(sq_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["signal_quality"] = None
    else:
        bundle["signal_quality"] = None

    # Include plugin diagnostics
    pd_path = case_dir / "analysis" / "plugin_diagnostics.json"
    if pd_path.exists():
        try:
            bundle["plugin_diagnostics"] = json.loads(pd_path.read_text(encoding="utf-8"))
        except Exception:
            bundle["plugin_diagnostics"] = None
    else:
        bundle["plugin_diagnostics"] = None

    # Build replay_metadata
    parser_name = ""
    parser_version = ""
    plugin_versions: dict[str, str] = {}

    if bundle.get("provenance") and isinstance(bundle["provenance"], dict):
        parser_name = bundle["provenance"].get("parser_name", "")
        parser_version = bundle["provenance"].get("parser_version", "")

    if bundle.get("plugin_diagnostics") and isinstance(bundle["plugin_diagnostics"], dict):
        for p in bundle["plugin_diagnostics"].get("plugins_run", []):
            plugin_versions[p.get("name", "")] = p.get("version", "")

    bundle["replay_metadata"] = {
        "parser_name": parser_name,
        "parser_version": parser_version,
        "plugin_versions": plugin_versions,
        "tuning_profile": "default",
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = bundle_id.replace("BDL-", "").lower()
    filename = f"bundle_{ts}_{short_id}.json"
    filepath = exports_dir / filename
    filepath.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")

    # Record export in case.json
    case = svc.get_case(case_id)  # refresh
    export_record = CaseExport(
        export_id=bundle_id,
        exported_at=datetime.now(),
        export_path=str(filepath),
        bundle_version="1.0",
        includes_replay=True,
    )
    case.exports.append(export_record)
    svc.save_case(case)

    # Audit
    svc._append_audit(case_id, AuditEntry(
        event_id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
        timestamp=datetime.now(),
        actor="api",
        action=AuditAction.CASE_EXPORTED,
        object_type="export",
        object_id=bundle_id,
        details={"filename": filename, "bundle_version": "1.0"},
    ))

    return JSONResponse({
        "ok": True,
        "bundle_id": bundle_id,
        "filename": filename,
        "path": str(filepath),
        "size_bytes": filepath.stat().st_size,
    })


@router.get("/{case_id}/exports/files/{filename}")
async def get_export_file(case_id: str, filename: str) -> JSONResponse:
    """Serve an export file from the exports/ directory."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    # Security: ensure the filename doesn't traverse directories
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = svc.case_dir(case_id) / "exports" / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail=f"Export file not found: {filename}")

    from fastapi.responses import FileResponse
    return FileResponse(str(filepath), media_type="application/json", filename=filename)


# ---------------------------------------------------------------------------
# New routes — Replay verification and report generation
# ---------------------------------------------------------------------------

@router.get("/{case_id}/tuning-profile")
async def get_tuning_profile(case_id: str) -> JSONResponse:
    """Return the current/default tuning profile as JSON."""
    from goose.forensics.tuning import TuningProfile
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    profile = TuningProfile.default()
    return JSONResponse({"ok": True, "tuning_profile": profile.to_dict()})


@router.post("/{case_id}/exports/verify-replay")
async def verify_replay(case_id: str, body: VerifyReplayRequest) -> JSONResponse:
    """Compare a bundle's versions with the current engine/parser/plugins.

    Returns a ReplayVerificationReport.
    """
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    # Security check
    fn = body.bundle_filename
    if ".." in fn or "/" in fn or "\\" in fn:
        raise HTTPException(status_code=400, detail="Invalid filename")

    bundle_path = svc.case_dir(case_id) / "exports" / fn
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail=f"Bundle not found: {fn}")

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot parse bundle: {exc}") from exc

    # Extract original versions from bundle
    original_engine = bundle.get("engine_version", "")
    replay_meta = bundle.get("replay_metadata", {})
    original_parser = replay_meta.get("parser_version", "")
    original_plugins = replay_meta.get("plugin_versions", {})

    # Get current versions
    from goose.plugins import PLUGIN_REGISTRY
    current_plugins: dict[str, str] = {}
    for pid, p in PLUGIN_REGISTRY.items():
        current_plugins[p.name] = getattr(p, "version", "unknown")

    current_parser = ""
    # Try to get parser version from installed module
    try:
        from goose.parsers.ulog import UlogParser
        current_parser = getattr(UlogParser, "VERSION", "")
    except Exception:
        pass

    # Compute drifts
    drifts: list[str] = []
    if original_engine and original_engine != __version__:
        drifts.append(f"engine: {original_engine} -> {__version__}")
    if original_parser and current_parser and original_parser != current_parser:
        drifts.append(f"parser: {original_parser} -> {current_parser}")
    for name, orig_ver in original_plugins.items():
        cur_ver = current_plugins.get(name, "")
        if cur_ver and orig_ver != cur_ver:
            drifts.append(f"plugin {name}: {orig_ver} -> {cur_ver}")

    # Determine match state
    bundle_id = bundle.get("bundle_id", "unknown")

    # Check for missing data
    has_findings = bundle.get("findings") is not None
    has_hypotheses = bundle.get("hypotheses") is not None
    has_provenance = bundle.get("provenance") is not None

    if drifts:
        match_state = ReplayMatchState.VERSION_DRIFT
    elif not has_findings and not has_hypotheses:
        match_state = ReplayMatchState.PARTIAL
    else:
        match_state = ReplayMatchState.EXACT

    report = ReplayVerificationReport(
        bundle_id=bundle_id,
        case_id=case_id,
        original_engine_version=original_engine,
        current_engine_version=__version__,
        original_parser_version=original_parser,
        current_parser_version=current_parser,
        original_plugin_versions=original_plugins,
        current_plugin_versions=current_plugins,
        match_state=match_state,
        version_drifts=drifts,
        verified_at=datetime.now().isoformat(),
    )

    return JSONResponse({"ok": True, "report": report.to_dict()})


@router.get("/{case_id}/exports/reports/mission-summary")
async def mission_summary_report(case_id: str) -> JSONResponse:
    """Generate and return a MissionSummaryReport from current case analysis data."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    case_dir = svc.case_dir(case_id)
    run_id = ""
    if case.analysis_runs:
        run_id = case.analysis_runs[-1].run_id

    # Load findings
    findings: list[dict[str, Any]] = []
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle = json.loads(findings_path.read_text(encoding="utf-8"))
            findings = bundle.get("findings", [])
        except Exception:
            pass

    # Load hypotheses
    hypotheses: list[dict[str, Any]] = []
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
            hypotheses = bundle.get("hypotheses", [])
        except Exception:
            pass

    # Load signal quality
    sq_summary: dict[str, Any] = {}
    sq_path = case_dir / "analysis" / "signal_quality.json"
    if sq_path.exists():
        try:
            sq_bundle = json.loads(sq_path.read_text(encoding="utf-8"))
            for stream in sq_bundle.get("streams", []):
                sq_summary[stream.get("stream_name", "")] = stream.get("reliability_estimate", None)
        except Exception:
            pass

    # Load provenance for duration
    flight_duration = None
    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            flight_duration = prov.get("flight_duration_sec")
        except Exception:
            pass

    # Load parser confidence
    parser_confidence = None
    diag_path = case_dir / "parsed" / "parse_diagnostics.json"
    if diag_path.exists():
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            parser_confidence = diag.get("parser_confidence")
        except Exception:
            pass

    # Compute severity counts
    critical = sum(1 for f in findings if f.get("severity") == "critical")
    warning = sum(1 for f in findings if f.get("severity") == "warning")

    # Find top hypothesis
    top_hyp = None
    top_conf = None
    for h in hypotheses:
        conf = h.get("confidence", 0)
        if top_conf is None or conf > top_conf:
            top_conf = conf
            top_hyp = h.get("statement", h.get("title", ""))

    report = MissionSummaryReport(
        case_id=case_id,
        run_id=run_id,
        generated_at=datetime.now().isoformat(),
        flight_duration_s=flight_duration,
        total_findings=len(findings),
        critical_findings=critical,
        warning_findings=warning,
        top_hypothesis=top_hyp,
        top_hypothesis_confidence=top_conf,
        parser_confidence=parser_confidence,
        signal_quality_summary=sq_summary,
    )

    return JSONResponse({"ok": True, "report": report.to_dict()})


@router.get("/{case_id}/exports/reports/anomaly")
async def anomaly_report(case_id: str) -> JSONResponse:
    """Generate and return an AnomalyReport (WARNING+ findings, confident hypotheses)."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    case_dir = svc.case_dir(case_id)
    run_id = ""
    if case.analysis_runs:
        run_id = case.analysis_runs[-1].run_id

    # Load findings and filter to WARNING+
    findings: list[dict[str, Any]] = []
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle = json.loads(findings_path.read_text(encoding="utf-8"))
            for f in bundle.get("findings", []):
                if f.get("severity") in ("critical", "warning"):
                    findings.append(f)
        except Exception:
            pass

    # Load hypotheses and filter to confidence >= 0.5
    hypotheses: list[dict[str, Any]] = []
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
            for h in bundle.get("hypotheses", []):
                if h.get("confidence", 0) >= 0.5:
                    hypotheses.append(h)
        except Exception:
            pass

    report = AnomalyReport(
        case_id=case_id,
        run_id=run_id,
        generated_at=datetime.now().isoformat(),
        findings=findings,
        hypotheses=hypotheses,
    )

    return JSONResponse({"ok": True, "report": report.to_dict()})


@router.get("/{case_id}/exports/reports/crash")
async def crash_report(case_id: str) -> JSONResponse:
    """Generate and return a CrashMishapReport."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    case_dir = svc.case_dir(case_id)
    run_id = ""
    if case.analysis_runs:
        run_id = case.analysis_runs[-1].run_id

    # Load all findings
    all_findings: list[dict[str, Any]] = []
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle = json.loads(findings_path.read_text(encoding="utf-8"))
            all_findings = bundle.get("findings", [])
        except Exception:
            pass

    # Identify crash-related findings
    crash_keywords = ["crash", "impact", "freefall", "free fall", "disarm", "flip"]
    crash_findings = []
    evidence_refs = []
    for f in all_findings:
        title = (f.get("title", "") or "").lower()
        desc = (f.get("description", "") or "").lower()
        plugin = (f.get("plugin_id", "") or "").lower()
        is_crash = (
            any(kw in title for kw in crash_keywords)
            or any(kw in desc for kw in crash_keywords)
            or "crash" in plugin
            or f.get("severity") == "critical"
        )
        if is_crash:
            crash_findings.append(f)
            for ref in f.get("evidence_references", []):
                evidence_refs.append(ref)

    # Load hypotheses related to crashes
    crash_hypotheses: list[dict[str, Any]] = []
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
            for h in bundle.get("hypotheses", []):
                stmt = (h.get("statement", "") or "").lower()
                if any(kw in stmt for kw in crash_keywords) or h.get("confidence", 0) >= 0.7:
                    crash_hypotheses.append(h)
        except Exception:
            pass

    crash_detected = len(crash_findings) > 0

    report = CrashMishapReport(
        case_id=case_id,
        run_id=run_id,
        generated_at=datetime.now().isoformat(),
        crash_detected=crash_detected,
        crash_findings=crash_findings,
        crash_hypotheses=crash_hypotheses,
        evidence_references=evidence_refs,
    )

    return JSONResponse({"ok": True, "report": report.to_dict()})


# ---------------------------------------------------------------------------
# v11 Strategy Sprint — extended report routes
# ---------------------------------------------------------------------------

def _resolve_case_and_run(case_id: str) -> tuple[Any, Any, str]:
    """Resolve case_id to (svc, case, run_id) or raise HTTPException 404."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        case = svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    run_id = case.analysis_runs[-1].run_id if case.analysis_runs else ""
    return svc, case, run_id


@router.get("/{case_id}/exports/reports/forensic-case")
async def forensic_case_report(case_id: str) -> JSONResponse:
    """Return a full ForensicCaseReport built from case artifacts."""
    svc, _case, run_id = _resolve_case_and_run(case_id)
    report = generate_forensic_case_report(
        svc.case_dir(case_id), run_id=run_id, engine_version=__version__,
    )
    return JSONResponse({"ok": True, "report": report.to_dict()})


@router.get("/{case_id}/exports/reports/evidence-manifest")
async def evidence_manifest_report(case_id: str) -> JSONResponse:
    """Return an EvidenceManifestReport built from case manifests."""
    svc, _case, _run_id = _resolve_case_and_run(case_id)
    report = generate_evidence_manifest_report(svc.case_dir(case_id))
    return JSONResponse({"ok": True, "report": report.to_dict()})


@router.get("/{case_id}/exports/reports/service-repair")
async def service_repair_report(case_id: str) -> JSONResponse:
    """Return a ServiceRepairSummary (intended for shop_repair profile)."""
    svc, _case, run_id = _resolve_case_and_run(case_id)
    report = generate_service_repair_summary(svc.case_dir(case_id), run_id=run_id)
    return JSONResponse({"ok": True, "report": report.to_dict()})


@router.get("/{case_id}/exports/reports/qa-validation")
async def qa_validation_report_route(case_id: str) -> JSONResponse:
    """Return a QAValidationReport (intended for factory_qa profile)."""
    svc, _case, run_id = _resolve_case_and_run(case_id)
    report = generate_qa_validation_report(svc.case_dir(case_id), run_id=run_id)
    return JSONResponse({"ok": True, "report": report.to_dict()})


@router.get("/{case_id}/exports/reports/quick-summary")
async def quick_analysis_summary_route(case_id: str) -> JSONResponse:
    """Return a QuickAnalysisSummary built from case analysis data.

    The quick summary is the same shape returned by the quick-analysis entry
    path; here it is rebuilt from the current case's persisted artifacts so
    the two entry paths converge on one report format.
    """
    svc, case, _run_id = _resolve_case_and_run(case_id)
    case_dir = svc.case_dir(case_id)

    # Load findings + hypotheses from analysis/
    findings: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            data = json.loads(findings_path.read_text(encoding="utf-8"))
            findings = data.get("findings", []) if isinstance(data, dict) else (data or [])
        except Exception:
            pass
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if hyp_path.exists():
        try:
            data = json.loads(hyp_path.read_text(encoding="utf-8"))
            hypotheses = data.get("hypotheses", []) if isinstance(data, dict) else (data or [])
        except Exception:
            pass

    # Parser info from parse_diagnostics + provenance
    parser_confidence = None
    flight_duration = None
    diag_path = case_dir / "parsed" / "parse_diagnostics.json"
    if diag_path.exists():
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            parser_confidence = diag.get("parser_confidence")
        except Exception:
            pass
    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            flight_duration = prov.get("flight_duration_sec")
        except Exception:
            pass

    # Filename from first evidence item, if any
    filename = ""
    file_size = 0
    if case.evidence_items:
        filename = case.evidence_items[0].filename
        file_size = case.evidence_items[0].size_bytes

    report = generate_quick_analysis_summary(
        filename=filename,
        file_size_bytes=file_size,
        findings=findings,
        hypotheses=hypotheses,
        parser_confidence=parser_confidence,
        flight_duration_s=flight_duration,
        profile=getattr(case, "profile", "default") or "default",
        engine_version=__version__,
    )
    return JSONResponse({"ok": True, "report": report.to_dict()})
