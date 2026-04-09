"""Forensic report models for Goose-Core.

v11 Strategy Sprint — complete report object schemas.

Nine report families are defined in the v11 spec and exposed here as
dataclasses with ``to_dict``/``from_dict`` serialization helpers plus
generator functions that build them from persisted case artifacts.

All generators handle missing artifacts gracefully: a report is always
produced, with empty/None fields where source data is unavailable. This
lets the UI render a partial report even for half-analyzed cases instead
of blowing up with KeyError / FileNotFoundError.

Report objects
--------------
- ReplayVerificationReport  — bundle version comparison
- MissionSummaryReport      — high-level operator summary (extended)
- AnomalyReport             — WARNING+ findings + confident hypotheses (extended)
- CrashMishapReport         — crash/mishap forensic report (extended)
- ForensicCaseReport        — full case snapshot for deep review
- EvidenceManifestReport    — evidence/attachment chain-of-custody bundle
- QuickAnalysisSummary      — quick-analysis (no case) summary
- ServiceRepairSummary      — shop_repair profile report
- QAValidationReport        — factory_qa profile report

All generators are side-effect free (read-only) and safe to call from API
routes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from goose.forensics.profiles import WordingPack, get_profile


# ---------------------------------------------------------------------------
# Replay verification
# ---------------------------------------------------------------------------

class ReplayMatchState(str, Enum):
    EXACT = "exact"                    # all versions match
    VERSION_DRIFT = "version_drift"    # engine/plugin versions differ
    PARTIAL = "partial"                # some data missing from bundle
    INCOMPATIBLE = "incompatible"      # cannot replay


@dataclass
class ReplayVerificationReport:
    """Result of comparing a case bundle against the current engine state."""

    bundle_id: str
    case_id: str
    original_engine_version: str
    current_engine_version: str
    original_parser_version: str
    current_parser_version: str
    original_plugin_versions: dict[str, str]
    current_plugin_versions: dict[str, str]
    match_state: ReplayMatchState
    version_drifts: list[str]
    verified_at: str  # ISO timestamp
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "case_id": self.case_id,
            "original_engine_version": self.original_engine_version,
            "current_engine_version": self.current_engine_version,
            "original_parser_version": self.original_parser_version,
            "current_parser_version": self.current_parser_version,
            "original_plugin_versions": self.original_plugin_versions,
            "current_plugin_versions": self.current_plugin_versions,
            "match_state": self.match_state.value,
            "version_drifts": self.version_drifts,
            "verified_at": self.verified_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReplayVerificationReport:
        d = dict(d)
        d["match_state"] = ReplayMatchState(d["match_state"])
        return cls(**d)


# ---------------------------------------------------------------------------
# Shared helpers for generators
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    """Load JSON if present; return None on any error (graceful)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now().isoformat()


def _keep(d: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k in keys}


# ---------------------------------------------------------------------------
# MissionSummaryReport
# ---------------------------------------------------------------------------

@dataclass
class MissionSummaryReport:
    """High-level flight mission summary for operators and reviewers."""

    case_id: str
    run_id: str
    generated_at: str  # ISO timestamp
    flight_duration_s: float | None
    total_findings: int
    critical_findings: int
    warning_findings: int
    top_hypothesis: str | None
    top_hypothesis_confidence: float | None
    parser_confidence: float | None
    signal_quality_summary: dict[str, Any] = field(default_factory=dict)

    # v11 extensions — all optional for backward compat
    report_type: str = "mission_summary"
    report_version: str = "1.0"
    profile: str = "default"
    profile_id: str = "default"
    wording: dict[str, Any] = field(default_factory=dict)
    engine_version: str = ""
    mission_metadata: dict[str, Any] = field(default_factory=dict)
    platform_metadata: dict[str, Any] = field(default_factory=dict)
    operator_metadata: dict[str, Any] = field(default_factory=dict)
    environment_summary: str = ""
    flight_summary: dict[str, Any] = field(default_factory=dict)
    major_findings: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_summary: list[dict[str, Any]] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "profile": self.profile,
            "profile_id": self.profile_id,
            "wording": self.wording,
            "engine_version": self.engine_version,
            "flight_duration_s": self.flight_duration_s,
            "total_findings": self.total_findings,
            "critical_findings": self.critical_findings,
            "warning_findings": self.warning_findings,
            "top_hypothesis": self.top_hypothesis,
            "top_hypothesis_confidence": self.top_hypothesis_confidence,
            "parser_confidence": self.parser_confidence,
            "signal_quality_summary": self.signal_quality_summary,
            "mission_metadata": self.mission_metadata,
            "platform_metadata": self.platform_metadata,
            "operator_metadata": self.operator_metadata,
            "environment_summary": self.environment_summary,
            "flight_summary": self.flight_summary,
            "major_findings": self.major_findings,
            "hypotheses_summary": self.hypotheses_summary,
            "unresolved_questions": self.unresolved_questions,
            "recommendations": self.recommendations,
            "limitations": self.limitations,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MissionSummaryReport:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# AnomalyReport
# ---------------------------------------------------------------------------

@dataclass
class AnomalyReport:
    """Report containing WARNING+ findings and confident hypotheses."""

    case_id: str
    run_id: str
    generated_at: str  # ISO timestamp
    findings: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)

    # v11 extensions
    report_type: str = "anomaly_report"
    report_version: str = "1.0"
    profile_id: str = "default"
    wording: dict[str, Any] = field(default_factory=dict)
    anomaly_classification: str = ""
    affected_phase: str | None = None
    chronology_snippet: list[dict[str, Any]] = field(default_factory=list)
    evidence_references: list[dict[str, Any]] = field(default_factory=list)
    relevant_findings: list[dict[str, Any]] = field(default_factory=list)
    leading_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    confidence_notes: str = ""
    limitations: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "profile_id": self.profile_id,
            "wording": self.wording,
            "anomaly_classification": self.anomaly_classification,
            "affected_phase": self.affected_phase,
            "findings": self.findings,
            "hypotheses": self.hypotheses,
            "chronology_snippet": self.chronology_snippet,
            "evidence_references": self.evidence_references,
            "relevant_findings": self.relevant_findings,
            "leading_hypotheses": self.leading_hypotheses,
            "confidence_notes": self.confidence_notes,
            "limitations": self.limitations,
            "recommendations": self.recommendations,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnomalyReport:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# CrashMishapReport
# ---------------------------------------------------------------------------

@dataclass
class CrashMishapReport:
    """Crash/mishap-specific forensic report."""

    case_id: str
    run_id: str
    generated_at: str  # ISO timestamp
    crash_detected: bool
    crash_findings: list[dict[str, Any]] = field(default_factory=list)
    crash_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    evidence_references: list[dict[str, Any]] = field(default_factory=list)

    # v11 extensions
    report_type: str = "crash_mishap_report"
    report_version: str = "1.0"
    profile_id: str = "default"
    wording: dict[str, Any] = field(default_factory=dict)
    event_classification: str = ""
    severity: str = ""
    damage_summary: str = ""
    loss_summary: str = ""
    mission_context: dict[str, Any] = field(default_factory=dict)
    platform_context: dict[str, Any] = field(default_factory=dict)
    operator_context: dict[str, Any] = field(default_factory=dict)
    chronology: list[dict[str, Any]] = field(default_factory=list)
    key_findings: list[dict[str, Any]] = field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    contradicting_findings: list[dict[str, Any]] = field(default_factory=list)
    major_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    data_quality_limitations: list[str] = field(default_factory=list)
    attachments_summary: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    corrective_actions: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "profile_id": self.profile_id,
            "wording": self.wording,
            "crash_detected": self.crash_detected,
            "crash_findings": self.crash_findings,
            "crash_hypotheses": self.crash_hypotheses,
            "evidence_references": self.evidence_references,
            "event_classification": self.event_classification,
            "severity": self.severity,
            "damage_summary": self.damage_summary,
            "loss_summary": self.loss_summary,
            "mission_context": self.mission_context,
            "platform_context": self.platform_context,
            "operator_context": self.operator_context,
            "chronology": self.chronology,
            "key_findings": self.key_findings,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_findings": self.contradicting_findings,
            "major_hypotheses": self.major_hypotheses,
            "data_quality_limitations": self.data_quality_limitations,
            "attachments_summary": self.attachments_summary,
            "recommendations": self.recommendations,
            "corrective_actions": self.corrective_actions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CrashMishapReport:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# ForensicCaseReport
# ---------------------------------------------------------------------------

@dataclass
class ForensicCaseReport:
    """Full case snapshot — everything needed to audit or deep-review a case."""

    generated_at: str
    case_id: str
    run_id: str
    profile: str
    engine_version: str
    case_summary: dict[str, Any] = field(default_factory=dict)
    evidence_inventory: list[dict[str, Any]] = field(default_factory=list)
    parser_diagnostics_summary: dict[str, Any] = field(default_factory=dict)
    findings_inventory: list[dict[str, Any]] = field(default_factory=list)
    hypotheses_inventory: list[dict[str, Any]] = field(default_factory=list)
    timeline_summary: list[dict[str, Any]] = field(default_factory=list)
    plugin_execution_summary: dict[str, Any] = field(default_factory=dict)
    trust_tuning_context: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    export_replay_context: dict[str, Any] = field(default_factory=dict)
    report_type: str = "forensic_case_report"
    report_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "profile": self.profile,
            "engine_version": self.engine_version,
            "case_summary": self.case_summary,
            "evidence_inventory": self.evidence_inventory,
            "parser_diagnostics_summary": self.parser_diagnostics_summary,
            "findings_inventory": self.findings_inventory,
            "hypotheses_inventory": self.hypotheses_inventory,
            "timeline_summary": self.timeline_summary,
            "plugin_execution_summary": self.plugin_execution_summary,
            "trust_tuning_context": self.trust_tuning_context,
            "limitations": self.limitations,
            "export_replay_context": self.export_replay_context,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ForensicCaseReport:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# EvidenceManifestReport
# ---------------------------------------------------------------------------

@dataclass
class EvidenceManifestReport:
    """Evidence and attachment chain-of-custody summary."""

    generated_at: str
    case_id: str
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    provenance_summary: dict[str, Any] = field(default_factory=dict)
    audit_summary: dict[str, Any] = field(default_factory=dict)
    derived_artifacts: list[dict[str, Any]] = field(default_factory=list)
    immutability_verification: dict[str, Any] = field(default_factory=dict)
    report_type: str = "evidence_manifest_report"
    report_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "case_id": self.case_id,
            "evidence_items": self.evidence_items,
            "attachments": self.attachments,
            "provenance_summary": self.provenance_summary,
            "audit_summary": self.audit_summary,
            "derived_artifacts": self.derived_artifacts,
            "immutability_verification": self.immutability_verification,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceManifestReport:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# QuickAnalysisSummary
# ---------------------------------------------------------------------------

@dataclass
class QuickAnalysisSummary:
    """Quick-analysis (no case) summary report."""

    generated_at: str
    profile: str
    engine_version: str
    filename: str
    file_size_bytes: int
    parser_confidence: float | None = None
    flight_duration_s: float | None = None
    top_findings: list[dict[str, Any]] = field(default_factory=list)
    primary_hypothesis: dict[str, Any] | None = None
    quick_checks: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    report_type: str = "quick_analysis_summary"
    report_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "profile": self.profile,
            "engine_version": self.engine_version,
            "filename": self.filename,
            "file_size_bytes": self.file_size_bytes,
            "parser_confidence": self.parser_confidence,
            "flight_duration_s": self.flight_duration_s,
            "top_findings": self.top_findings,
            "primary_hypothesis": self.primary_hypothesis,
            "quick_checks": self.quick_checks,
            "limitations": self.limitations,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QuickAnalysisSummary:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# ServiceRepairSummary
# ---------------------------------------------------------------------------

@dataclass
class ServiceRepairSummary:
    """Shop/repair profile report — plain-language customer + technician summary."""

    generated_at: str
    case_id: str
    run_id: str
    customer_name: str | None
    ticket_id: str | None
    platform_name: str | None
    technician_name: str | None
    damage_summary: str | None
    likely_cause: str
    likely_cause_confidence: float | None = None
    contributing_issues: list[dict[str, Any]] = field(default_factory=list)
    recommended_inspection_steps: list[str] = field(default_factory=list)
    customer_summary: str = ""
    technician_notes: str = ""
    report_type: str = "service_repair_summary"
    report_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "customer_name": self.customer_name,
            "ticket_id": self.ticket_id,
            "platform_name": self.platform_name,
            "technician_name": self.technician_name,
            "damage_summary": self.damage_summary,
            "likely_cause": self.likely_cause,
            "likely_cause_confidence": self.likely_cause_confidence,
            "contributing_issues": self.contributing_issues,
            "recommended_inspection_steps": self.recommended_inspection_steps,
            "customer_summary": self.customer_summary,
            "technician_notes": self.technician_notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ServiceRepairSummary:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# QAValidationReport
# ---------------------------------------------------------------------------

@dataclass
class QAValidationReport:
    """Factory/QA profile report — acceptance criteria and disposition."""

    generated_at: str
    case_id: str
    run_id: str
    serial_number: str | None
    tester_name: str | None
    firmware_version: str | None
    overall_disposition: str  # "PASS" | "FAIL" | "CONDITIONAL_PASS" | "REQUIRES_REVIEW"
    acceptance_criteria_results: list[dict[str, Any]] = field(default_factory=list)
    out_of_tolerance_findings: list[dict[str, Any]] = field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    signoff_context: dict[str, Any] = field(default_factory=dict)
    report_type: str = "qa_validation_report"
    report_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "serial_number": self.serial_number,
            "tester_name": self.tester_name,
            "firmware_version": self.firmware_version,
            "overall_disposition": self.overall_disposition,
            "acceptance_criteria_results": self.acceptance_criteria_results,
            "out_of_tolerance_findings": self.out_of_tolerance_findings,
            "supporting_evidence": self.supporting_evidence,
            "signoff_context": self.signoff_context,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QAValidationReport:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**_keep(d, known))


# ---------------------------------------------------------------------------
# Generator functions — build reports from a case directory
# ---------------------------------------------------------------------------

def _load_case_summary(case_dir: Path) -> dict[str, Any]:
    case_json = _load_json(case_dir / "case.json")
    if not isinstance(case_json, dict):
        return {}
    return case_json


def _load_findings(case_dir: Path) -> list[dict[str, Any]]:
    data = _load_json(case_dir / "analysis" / "findings.json")
    if isinstance(data, dict):
        return data.get("findings", []) or []
    if isinstance(data, list):
        return data
    return []


def _load_hypotheses(case_dir: Path) -> list[dict[str, Any]]:
    data = _load_json(case_dir / "analysis" / "hypotheses.json")
    if isinstance(data, dict):
        return data.get("hypotheses", []) or []
    if isinstance(data, list):
        return data
    return []


def _load_timeline(case_dir: Path) -> list[dict[str, Any]]:
    data = _load_json(case_dir / "analysis" / "timeline.json")
    if isinstance(data, dict):
        return data.get("events", []) or []
    if isinstance(data, list):
        return data
    return []


def _load_plugin_diagnostics(case_dir: Path) -> dict[str, Any]:
    data = _load_json(case_dir / "analysis" / "plugin_diagnostics.json")
    if isinstance(data, dict):
        return data
    return {}


def _load_parse_diagnostics(case_dir: Path) -> dict[str, Any]:
    data = _load_json(case_dir / "parsed" / "parse_diagnostics.json")
    if isinstance(data, dict):
        return data
    return {}


def _load_provenance(case_dir: Path) -> dict[str, Any]:
    data = _load_json(case_dir / "parsed" / "provenance.json")
    if isinstance(data, dict):
        return data
    return {}


def _load_evidence_manifest(case_dir: Path) -> list[dict[str, Any]]:
    data = _load_json(case_dir / "manifests" / "evidence_manifest.json")
    if isinstance(data, dict):
        return data.get("evidence", []) or data.get("evidence_items", []) or []
    if isinstance(data, list):
        return data
    return []


def _load_attachments(case_dir: Path) -> list[dict[str, Any]]:
    # Attachments live either under manifests/attachment_manifest.json or
    # in case.json.attachments. Try both.
    data = _load_json(case_dir / "manifests" / "attachment_manifest.json")
    if isinstance(data, dict):
        return data.get("attachments", []) or []
    if isinstance(data, list):
        return data
    case = _load_case_summary(case_dir)
    return case.get("attachments", []) or []


def _load_audit_entries(case_dir: Path) -> list[dict[str, Any]]:
    path = case_dir / "audit" / "audit.log"
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return entries


def _limitations_from_diagnostics(parse_diag: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    warnings = parse_diag.get("warnings") or []
    if isinstance(warnings, list):
        for w in warnings:
            if isinstance(w, str):
                limitations.append(w)
            elif isinstance(w, dict):
                msg = w.get("message") or w.get("warning") or ""
                if msg:
                    limitations.append(str(msg))
    missing = parse_diag.get("missing_streams") or []
    if isinstance(missing, list):
        for m in missing:
            limitations.append(f"missing stream: {m}")
    return limitations


def _top_findings(findings: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    """Return top-N findings by severity (critical > warning > info > pass)."""
    order = {"critical": 0, "warning": 1, "info": 2, "pass": 3}
    return sorted(
        findings,
        key=lambda f: order.get(str(f.get("severity", "info")).lower(), 99),
    )[:n]


def _top_hypotheses(hypotheses: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    return sorted(
        hypotheses,
        key=lambda h: -float(h.get("confidence", 0) or 0),
    )[:n]


def generate_mission_summary_report(
    case_dir: Path,
    case_id: str,
    run_id: str,
    engine_version: str = "0.6.0",
    profile_id: str = "default",
) -> MissionSummaryReport:
    """Build an extended MissionSummaryReport from case artifacts."""
    case = _load_case_summary(case_dir)
    # Resolve profile_id: explicit param takes priority, then case.json, then "default"
    resolved_profile_id = profile_id or case.get("profile", "default") or "default"
    profile_cfg = get_profile(resolved_profile_id)
    wording: WordingPack = profile_cfg.wording
    findings = _load_findings(case_dir)
    hypotheses = _load_hypotheses(case_dir)
    parse_diag = _load_parse_diagnostics(case_dir)
    prov = _load_provenance(case_dir)

    critical = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
    warning = sum(1 for f in findings if str(f.get("severity", "")).lower() == "warning")

    top_hyp = None
    top_conf: float | None = None
    for h in hypotheses:
        c = float(h.get("confidence", 0) or 0)
        if top_conf is None or c > top_conf:
            top_conf = c
            top_hyp = h.get("statement") or h.get("title") or ""

    flight_duration = prov.get("flight_duration_sec") if isinstance(prov, dict) else None

    mission_meta = {
        k: case.get(k)
        for k in (
            "mission_id", "sortie_id", "operation_type",
            "date_time_start", "date_time_end", "location_name",
        )
    }
    platform_meta = {
        k: case.get(k)
        for k in ("platform_name", "platform_type", "serial_number", "firmware_version")
    }
    operator_meta = {
        k: case.get(k) for k in ("operator_name", "team_name", "unit_name")
    }

    return MissionSummaryReport(
        case_id=case_id,
        run_id=run_id,
        generated_at=_now_iso(),
        flight_duration_s=flight_duration,
        total_findings=len(findings),
        critical_findings=critical,
        warning_findings=warning,
        top_hypothesis=top_hyp,
        top_hypothesis_confidence=top_conf,
        parser_confidence=parse_diag.get("parser_confidence") if parse_diag else None,
        signal_quality_summary={},
        profile=resolved_profile_id,
        profile_id=resolved_profile_id,
        wording=wording.to_dict(),
        engine_version=engine_version,
        mission_metadata=mission_meta,
        platform_metadata=platform_meta,
        operator_metadata=operator_meta,
        environment_summary=case.get("environment_summary") or "",
        flight_summary={
            "duration_s": flight_duration,
            # Use profile wording: "workflow_label Run/Sortie/Case"
            "workflow_label": wording.workflow_label,
            "phases": [],
        },
        major_findings=_top_findings(findings, 5),
        hypotheses_summary=_top_hypotheses(hypotheses, 3),
        unresolved_questions=[],
        recommendations=[case["recommendations"]] if case.get("recommendations") else [],
        limitations=_limitations_from_diagnostics(parse_diag),
    )


def generate_forensic_case_report(
    case_dir: Path,
    run_id: str,
    engine_version: str = "0.6.0",
    profile_id: str = "default",
) -> ForensicCaseReport:
    """Load all artifacts from case_dir and produce a ForensicCaseReport."""
    case = _load_case_summary(case_dir)
    case_id = case.get("case_id", case_dir.name)
    resolved_profile_id = profile_id or case.get("profile", "default") or "default"
    findings = _load_findings(case_dir)
    hypotheses = _load_hypotheses(case_dir)
    timeline = _load_timeline(case_dir)
    plugin_diag = _load_plugin_diagnostics(case_dir)
    parse_diag = _load_parse_diagnostics(case_dir)
    evidence = _load_evidence_manifest(case_dir)

    case_summary = {
        k: case.get(k) for k in (
            "case_id", "status", "created_at", "created_by", "tags", "notes",
            "profile", "event_classification", "event_severity",
            "mission_id", "platform_name", "operator_name",
        )
    }

    parser_diag_summary = {
        "parser_confidence": parse_diag.get("parser_confidence"),
        "warnings_count": len(parse_diag.get("warnings") or []),
        "stream_coverage_count": len(parse_diag.get("stream_coverage") or parse_diag.get("streams") or []),
    }

    # plugin execution summary: plugin_id -> details
    plugin_exec: dict[str, Any] = {}
    for p in plugin_diag.get("plugins_run", []) or []:
        pid = p.get("plugin_id") or p.get("name") or "unknown"
        plugin_exec[pid] = {
            "status": p.get("status", "unknown"),
            "findings_count": p.get("findings_count", 0),
            "version": p.get("version", ""),
            "trust_state": p.get("trust_state", "unknown"),
        }

    trust_tuning = {
        "tuning_profile_id": "default",
        "tuning_profile_version": "1.0.0",
        "policy_mode": "standard",
    }
    runs = case.get("analysis_runs") or []
    if runs and isinstance(runs, list):
        last = runs[-1]
        if isinstance(last, dict):
            trust_tuning["tuning_profile_id"] = last.get("tuning_profile_id", "default")
            trust_tuning["tuning_profile_version"] = last.get("tuning_profile_version", "1.0.0")

    export_replay = {
        "bundle_ids": [e.get("export_id") for e in (case.get("exports") or []) if isinstance(e, dict)],
        "export_timestamps": [e.get("exported_at") for e in (case.get("exports") or []) if isinstance(e, dict)],
    }

    return ForensicCaseReport(
        generated_at=_now_iso(),
        case_id=case_id,
        run_id=run_id,
        profile=resolved_profile_id,
        engine_version=engine_version,
        case_summary=case_summary,
        evidence_inventory=evidence,
        parser_diagnostics_summary=parser_diag_summary,
        findings_inventory=findings,
        hypotheses_inventory=hypotheses,
        timeline_summary=timeline[:50],  # cap for report size
        plugin_execution_summary=plugin_exec,
        trust_tuning_context=trust_tuning,
        limitations=_limitations_from_diagnostics(parse_diag),
        export_replay_context=export_replay,
    )


def generate_evidence_manifest_report(case_dir: Path, profile_id: str = "default") -> EvidenceManifestReport:
    """Load evidence and attachment manifests from case_dir."""
    case = _load_case_summary(case_dir)
    case_id = case.get("case_id", case_dir.name)
    evidence = _load_evidence_manifest(case_dir)
    attachments = _load_attachments(case_dir)
    prov = _load_provenance(case_dir)
    audit = _load_audit_entries(case_dir)

    provenance_summary: dict[str, Any] = {}
    if prov:
        provenance_summary = {
            "parser_name": prov.get("parser_name", ""),
            "parser_version": prov.get("parser_version", ""),
            "transformation_chain": prov.get("transformation_chain", []),
        }

    first_ts = audit[0].get("timestamp") if audit else None
    last_ts = audit[-1].get("timestamp") if audit else None
    audit_summary = {
        "event_count": len(audit),
        "first_event": first_ts,
        "last_event": last_ts,
    }

    derived: list[dict[str, Any]] = []
    for sub in ("parsed", "analysis"):
        d = case_dir / sub
        if d.exists() and d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    try:
                        derived.append({
                            "path": f"{sub}/{f.name}",
                            "size_bytes": f.stat().st_size,
                        })
                    except Exception:
                        continue

    immutability = {
        "all_verified": all(bool(e.get("immutable", False)) for e in evidence) if evidence else True,
        "verified_count": sum(1 for e in evidence if e.get("immutable")),
        "total_count": len(evidence),
    }

    return EvidenceManifestReport(
        generated_at=_now_iso(),
        case_id=case_id,
        evidence_items=evidence,
        attachments=attachments,
        provenance_summary=provenance_summary,
        audit_summary=audit_summary,
        derived_artifacts=derived,
        immutability_verification=immutability,
    )


def generate_service_repair_summary(
    case_dir: Path,
    run_id: str,
) -> ServiceRepairSummary:
    """Generate shop/repair profile report from case artifacts."""
    case = _load_case_summary(case_dir)
    case_id = case.get("case_id", case_dir.name)
    findings = _load_findings(case_dir)
    hypotheses = _load_hypotheses(case_dir)

    top_hyps = _top_hypotheses(hypotheses, 3)
    primary = top_hyps[0] if top_hyps else None
    if primary:
        likely_cause = primary.get("statement") or primary.get("title") or "Unknown"
        likely_conf = float(primary.get("confidence", 0) or 0) or None
    else:
        likely_cause = "No definitive cause identified"
        likely_conf = None

    # contributing issues: secondary findings beyond top 1
    contributing = [
        f for f in findings
        if str(f.get("severity", "")).lower() in ("warning", "critical")
    ][:5]

    # Customer-friendly plain-language summary
    critical_n = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
    warning_n = sum(1 for f in findings if str(f.get("severity", "")).lower() == "warning")
    customer_summary = (
        f"We analyzed your flight log and found {critical_n} critical issue(s) "
        f"and {warning_n} warning(s). "
        f"Most likely cause: {likely_cause}."
    )

    # Recommended inspection steps derived from top findings
    steps: list[str] = []
    for f in _top_findings(findings, 5):
        title = f.get("title") or ""
        if title:
            steps.append(f"Inspect: {title}")

    return ServiceRepairSummary(
        generated_at=_now_iso(),
        case_id=case_id,
        run_id=run_id,
        customer_name=case.get("customer_name"),
        ticket_id=case.get("ticket_id"),
        platform_name=case.get("platform_name"),
        technician_name=case.get("technician_name"),
        damage_summary=case.get("damage_summary"),
        likely_cause=likely_cause,
        likely_cause_confidence=likely_conf,
        contributing_issues=contributing,
        recommended_inspection_steps=steps,
        customer_summary=customer_summary,
        technician_notes=case.get("notes", "") or "",
    )


def generate_qa_validation_report(
    case_dir: Path,
    run_id: str,
) -> QAValidationReport:
    """Generate factory/QA profile report from case artifacts."""
    case = _load_case_summary(case_dir)
    case_id = case.get("case_id", case_dir.name)
    findings = _load_findings(case_dir)

    critical_n = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
    warning_n = sum(1 for f in findings if str(f.get("severity", "")).lower() == "warning")

    # PASS/FAIL disposition:
    # - any critical -> FAIL
    # - any warnings, no criticals -> CONDITIONAL_PASS
    # - none -> PASS
    # - no findings file at all -> REQUIRES_REVIEW
    if not findings and not (case_dir / "analysis" / "findings.json").exists():
        disposition = "REQUIRES_REVIEW"
    elif critical_n > 0:
        disposition = "FAIL"
    elif warning_n > 0:
        disposition = "CONDITIONAL_PASS"
    else:
        disposition = "PASS"

    out_of_tol = [
        f for f in findings
        if str(f.get("severity", "")).lower() in ("critical", "warning")
    ]

    acceptance_results = [
        {
            "criterion": f.get("title", "finding"),
            "result": "FAIL" if str(f.get("severity", "")).lower() == "critical" else "WARN",
            "finding_ref": f.get("finding_id") or f.get("id"),
        }
        for f in out_of_tol
    ]

    return QAValidationReport(
        generated_at=_now_iso(),
        case_id=case_id,
        run_id=run_id,
        serial_number=case.get("serial_number"),
        tester_name=case.get("tester_name"),
        firmware_version=case.get("firmware_version"),
        overall_disposition=disposition,
        acceptance_criteria_results=acceptance_results,
        out_of_tolerance_findings=out_of_tol,
        supporting_evidence=_load_evidence_manifest(case_dir),
        signoff_context={
            "tester": case.get("tester_name"),
            "timestamp": _now_iso(),
            "run_id": run_id,
        },
    )


def generate_quick_analysis_summary(
    *,
    filename: str,
    file_size_bytes: int,
    findings: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    parser_confidence: float | None = None,
    flight_duration_s: float | None = None,
    profile: str = "default",
    engine_version: str = "0.6.0",
    limitations: list[str] | None = None,
) -> QuickAnalysisSummary:
    """Build a quick-analysis summary report from in-memory analysis data."""
    top_hyps = _top_hypotheses(hypotheses, 1)
    primary = top_hyps[0] if top_hyps else None

    # quick checks: simple recommended next actions based on finding keywords
    checks: list[str] = []
    for f in _top_findings(findings, 5):
        title = (f.get("title") or "").lower()
        if "vibration" in title:
            checks.append("Check prop balance and motor mounts")
        elif "battery" in title or "voltage" in title:
            checks.append("Inspect battery and power distribution")
        elif "gps" in title:
            checks.append("Verify GPS antenna placement and sky view")
        elif "motor" in title or "saturation" in title:
            checks.append("Inspect motors and ESCs for damage or wear")
        elif "ekf" in title:
            checks.append("Check sensor calibration (compass, accel, gyro)")

    return QuickAnalysisSummary(
        generated_at=_now_iso(),
        profile=profile,
        engine_version=engine_version,
        filename=filename,
        file_size_bytes=file_size_bytes,
        parser_confidence=parser_confidence,
        flight_duration_s=flight_duration_s,
        top_findings=_top_findings(findings, 5),
        primary_hypothesis=primary,
        quick_checks=checks,
        limitations=limitations or [],
    )


def generate_anomaly_report(
    case_dir: Path,
    case_id: str,
    run_id: str,
    profile_id: str = "default",
) -> AnomalyReport:
    """Build an AnomalyReport from case artifacts (WARNING+ findings, confident hypotheses)."""
    case = _load_case_summary(case_dir)
    resolved_profile_id = profile_id or case.get("profile", "default") or "default"
    profile_cfg = get_profile(resolved_profile_id)
    wording: WordingPack = profile_cfg.wording

    all_findings = _load_findings(case_dir)
    findings = [f for f in all_findings if f.get("severity") in ("critical", "warning")]

    all_hypotheses = _load_hypotheses(case_dir)
    hypotheses = [h for h in all_hypotheses if float(h.get("confidence", 0) or 0) >= 0.5]

    return AnomalyReport(
        case_id=case_id,
        run_id=run_id,
        generated_at=_now_iso(),
        findings=findings,
        hypotheses=hypotheses,
        profile_id=resolved_profile_id,
        wording=wording.to_dict(),
        # anomaly_classification uses the profile's event_label as a heading prefix
        anomaly_classification=wording.event_label,
    )


def generate_crash_mishap_report(
    case_dir: Path,
    case_id: str,
    run_id: str,
    profile_id: str = "default",
) -> CrashMishapReport:
    """Build a CrashMishapReport from case artifacts."""
    case = _load_case_summary(case_dir)
    resolved_profile_id = profile_id or case.get("profile", "default") or "default"
    profile_cfg = get_profile(resolved_profile_id)
    wording: WordingPack = profile_cfg.wording

    all_findings = _load_findings(case_dir)
    crash_keywords = ["crash", "impact", "freefall", "free fall", "disarm", "flip"]
    crash_findings = []
    evidence_refs: list[dict[str, Any]] = []
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

    all_hypotheses = _load_hypotheses(case_dir)
    crash_hypotheses = [
        h for h in all_hypotheses
        if any(kw in (h.get("statement", "") or "").lower() for kw in crash_keywords)
        or float(h.get("confidence", 0) or 0) >= 0.7
    ]

    crash_detected = len(crash_findings) > 0

    return CrashMishapReport(
        case_id=case_id,
        run_id=run_id,
        generated_at=_now_iso(),
        crash_detected=crash_detected,
        crash_findings=crash_findings,
        crash_hypotheses=crash_hypotheses,
        evidence_references=evidence_refs,
        profile_id=resolved_profile_id,
        wording=wording.to_dict(),
        # event_classification uses profile's event_label ("Crash"/"Mishap"/"Incident")
        event_classification=wording.event_label,
    )
