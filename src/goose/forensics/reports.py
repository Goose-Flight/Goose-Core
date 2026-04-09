"""Forensic report models for Goose-Core.

Hardening Sprint — Replay/Export and Report Generation

Report types:
- ReplayVerificationReport: compares bundle versions with current engine
- MissionSummaryReport: high-level flight summary for operators
- AnomalyReport: WARNING+ findings and confident hypotheses
- CrashMishapReport: crash-specific forensic report
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "flight_duration_s": self.flight_duration_s,
            "total_findings": self.total_findings,
            "critical_findings": self.critical_findings,
            "warning_findings": self.warning_findings,
            "top_hypothesis": self.top_hypothesis,
            "top_hypothesis_confidence": self.top_hypothesis_confidence,
            "parser_confidence": self.parser_confidence,
            "signal_quality_summary": self.signal_quality_summary,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MissionSummaryReport:
        return cls(**{k: v for k, v in d.items() if k in {
            "case_id", "run_id", "generated_at", "flight_duration_s",
            "total_findings", "critical_findings", "warning_findings",
            "top_hypothesis", "top_hypothesis_confidence",
            "parser_confidence", "signal_quality_summary",
        }})


@dataclass
class AnomalyReport:
    """Report containing WARNING+ findings and confident hypotheses."""

    case_id: str
    run_id: str
    generated_at: str  # ISO timestamp
    findings: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "findings": self.findings,
            "hypotheses": self.hypotheses,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnomalyReport:
        return cls(**{k: v for k, v in d.items() if k in {
            "case_id", "run_id", "generated_at", "findings", "hypotheses",
        }})


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "crash_detected": self.crash_detected,
            "crash_findings": self.crash_findings,
            "crash_hypotheses": self.crash_hypotheses,
            "evidence_references": self.evidence_references,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CrashMishapReport:
        return cls(**{k: v for k, v in d.items() if k in {
            "case_id", "run_id", "generated_at", "crash_detected",
            "crash_findings", "crash_hypotheses", "evidence_references",
        }})
