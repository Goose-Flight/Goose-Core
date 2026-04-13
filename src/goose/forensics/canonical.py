"""Canonical forensic data models for Goose-Core.

These are the forensic-ready types that sit above the parser layer and below
the GUI/API layer.  Plugins emit thin findings (goose.core.finding.Finding);
the lifting layer (goose.forensics.lifting) promotes them to ForensicFinding.

Sprint 4 — Canonical Model Completion

Design rules:
- Facts (parsed data), findings, and hypotheses are explicitly distinct types.
- Every finding must carry evidence references — detached findings are rejected.
- Confidence fields always include a scope label. Parser confidence ≠ finding
  confidence ≠ hypothesis confidence. Conflating them corrupts forensic reasoning.
- All models are fully serializable to/from plain dicts for case persistence
  and API responses.
- from_dict() on all models ignores unknown keys for forward-compatibility.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FindingSeverity(str, Enum):
    """Severity levels for forensic findings.

    CRITICAL — system failure, likely cause of crash or serious anomaly
    WARNING  — degraded performance, potential risk
    INFO     — observation, no immediate risk
    PASS     — check passed, no issue found
    """
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    PASS = "pass"


class HypothesisStatus(str, Enum):
    """The evaluation state of a root-cause hypothesis."""
    CANDIDATE = "candidate"       # proposed, not yet evaluated
    SUPPORTED = "supported"       # more supporting than contradicting findings
    REFUTED = "refuted"           # contradicting evidence outweighs support
    INCONCLUSIVE = "inconclusive" # insufficient evidence to decide


class ConfidenceBand(str, Enum):
    """Qualitative confidence band derived from a float confidence score."""
    HIGH = "high"       # >= 0.80
    MEDIUM = "medium"   # >= 0.50
    LOW = "low"         # >= 0.25
    UNKNOWN = "unknown" # < 0.25 or not computed

    @classmethod
    def from_score(cls, score: float) -> ConfidenceBand:
        if score >= 0.80:
            return cls.HIGH
        if score >= 0.50:
            return cls.MEDIUM
        if score >= 0.25:
            return cls.LOW
        return cls.UNKNOWN


# ---------------------------------------------------------------------------
# SignalQuality
# ---------------------------------------------------------------------------

@dataclass
class SignalQuality:
    """Quality representation for a single telemetry stream.

    Built from ParseDiagnostics.stream_coverage after a successful parse.
    Attached to case analysis artifacts — not to the Flight object itself.

    completeness  — fraction of expected rows that are present (0–1)
    continuity    — fraction of time without detected gaps (0–1)
    reliability   — combined estimate; 1.0 = fully reliable, 0.0 = unusable
    """

    stream_name: str
    completeness: float = 1.0       # 0.0–1.0
    continuity: float = 1.0         # 0.0–1.0
    corruption_detected: bool = False
    reliability_estimate: float = 1.0  # 0.0–1.0
    row_count: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SignalQuality:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_stream_coverage(cls, sc: Any) -> SignalQuality:
        """Build SignalQuality from a ParseDiagnostics.StreamCoverage entry."""
        # If stream is absent, reliability is 0; if present, start at 1.0
        if not sc.present:
            return cls(
                stream_name=sc.stream_name,
                completeness=0.0,
                continuity=0.0,
                reliability_estimate=0.0,
                row_count=0,
                notes="Stream not present in log.",
            )
        return cls(
            stream_name=sc.stream_name,
            completeness=1.0,  # we know rows exist; more granular checks in Sprint 5
            continuity=1.0,
            reliability_estimate=1.0,
            row_count=sc.row_count,
        )


# ---------------------------------------------------------------------------
# EvidenceReference
# ---------------------------------------------------------------------------

@dataclass
class EvidenceReference:
    """Links a finding back to a specific piece of case evidence.

    Every ForensicFinding must have at least one EvidenceReference.
    Findings without evidence references are not forensically valid.

    Fields:
        evidence_id     — matches EvidenceItem.evidence_id in the case
        stream_name     — telemetry stream/topic (e.g. "battery_status")
        time_range_start — seconds from log start where the relevant data begins
        time_range_end   — seconds from log start where the relevant data ends
        sample_index_start / sample_index_end — row indices if available
        parameter_ref   — e.g. "BAT_V_CHARGED_THRESH" if a parameter is relevant
        support_summary — one sentence explaining what this evidence shows
    """

    evidence_id: str
    stream_name: str | None = None
    time_range_start: float | None = None
    time_range_end: float | None = None
    sample_index_start: int | None = None
    sample_index_end: int | None = None
    parameter_ref: str | None = None
    support_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceReference:
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# ForensicFinding
# ---------------------------------------------------------------------------


@dataclass
class ForensicFinding:
    """A forensic-grade finding produced by an analysis plugin.

    This is the Sprint 4 canonical finding model.  It is distinct from the
    thin goose.core.finding.Finding that plugins currently emit; the lifting
    layer (goose.forensics.lifting) promotes thin findings into this form.

    In Sprint 5, plugins will emit ForensicFinding directly.

    Confidence scope
    ----------------
    ``confidence`` is finding-level analytical confidence — how certain the
    analysis logic is that this finding reflects a real anomaly given the
    available evidence.  It is NOT parser confidence (that lives in
    ParseDiagnostics).  It is NOT root-cause certainty (that lives in
    Hypothesis.confidence).  The ``confidence_scope`` field makes this
    explicit in the serialized output.

    Evidence reference rule
    -----------------------
    Every finding must have at least one EvidenceReference.  The lifting
    layer always constructs one from the source evidence item even when
    the plugin does not specify a stream.  This ensures findings are never
    detached from their evidentiary basis.
    """

    finding_id: str
    plugin_id: str                          # plugin.name
    plugin_version: str
    title: str
    description: str
    severity: FindingSeverity
    score: int                              # 0–100 (100 = perfect/pass)
    confidence: float                       # 0.0–1.0, finding analytical confidence
    confidence_scope: str = "finding_analysis"  # explicit — not parser or hypothesis confidence
    phase: str | None = None
    start_time: float | None = None         # seconds from log start
    end_time: float | None = None
    evidence_references: list[EvidenceReference] = field(default_factory=list)
    supporting_metrics: dict[str, Any] = field(default_factory=dict)
    contradicting_metrics: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "finding_id": self.finding_id,
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "score": self.score,
            "confidence": self.confidence,
            "confidence_scope": self.confidence_scope,
            "confidence_band": ConfidenceBand.from_score(self.confidence).value,
            "phase": self.phase,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "evidence_references": [r.to_dict() for r in self.evidence_references],
            "supporting_metrics": self.supporting_metrics,
            "contradicting_metrics": self.contradicting_metrics,
            "assumptions": self.assumptions,
            "generated_at": self.generated_at.isoformat(),
            "run_id": self.run_id,
        }
        # Frontend-compatible aliases so the SPA doesn't break on field name mismatches
        d["plugin_name"] = self.plugin_id
        d["timestamp_start"] = self.start_time
        d["timestamp_end"] = self.end_time
        d["evidence"] = self.supporting_metrics
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ForensicFinding:
        d = dict(d)
        d["severity"] = FindingSeverity(d.get("severity", "info"))
        d["evidence_references"] = [
            EvidenceReference.from_dict(r) for r in d.get("evidence_references", [])
        ]
        if "generated_at" in d and d["generated_at"]:
            d["generated_at"] = datetime.fromisoformat(d["generated_at"])
        else:
            d["generated_at"] = datetime.now().replace(microsecond=0)
        # Remove computed/derived keys not in the dataclass
        d.pop("confidence_band", None)
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence_references) > 0

    @property
    def confidence_band(self) -> ConfidenceBand:
        return ConfidenceBand.from_score(self.confidence)


# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis:
    """A structured root-cause candidate built from correlated findings.

    Facts (parsed telemetry), findings (plugin outputs), and hypotheses are
    explicitly distinct.  A hypothesis references findings by ID — it does
    not embed them or replace them.

    Confidence scope
    ----------------
    Hypothesis confidence is root-cause/investigative confidence — how well
    the available findings explain the observed behavior as a coherent causal
    story.  It is NOT parser confidence and NOT individual finding confidence.

    Status transitions
    ------------------
    CANDIDATE → SUPPORTED if supporting_finding_ids substantially outweighs
                             contradicting_finding_ids
    CANDIDATE → REFUTED    if contradicting evidence is decisive
    CANDIDATE → INCONCLUSIVE if evidence is mixed without clear resolution
    """

    hypothesis_id: str
    statement: str                              # plain-language root cause claim
    supporting_finding_ids: list[str] = field(default_factory=list)
    contradicting_finding_ids: list[str] = field(default_factory=list)
    # Structured contradicting findings: list of dicts with finding_id, title, severity
    contradicting_findings: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0                     # 0.0–1.0, root-cause confidence
    confidence_scope: str = "hypothesis_root_cause"  # explicit — not parser confidence
    status: HypothesisStatus = HypothesisStatus.CANDIDATE
    unresolved_questions: list[str] = field(default_factory=list)
    analyst_notes: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))
    run_id: str | None = None
    theme: str = ""  # e.g. "power", "crash", "navigation", "control"
    # v11 Strategy Sprint additions
    category: str = ""                          # e.g. "propulsion / motor issue"
    related_timeline_events: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_by: str = "system"                # "system" or "user"
    # Sprint 2 — scoring transparency
    supporting_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "supporting_finding_ids": self.supporting_finding_ids,
            "contradicting_finding_ids": self.contradicting_finding_ids,
            "contradicting_findings": list(self.contradicting_findings),
            "confidence": self.confidence,
            "confidence_scope": self.confidence_scope,
            "confidence_band": ConfidenceBand.from_score(self.confidence).value,
            "status": self.status.value,
            "unresolved_questions": self.unresolved_questions,
            "analyst_notes": self.analyst_notes,
            "generated_at": self.generated_at.isoformat(),
            "run_id": self.run_id,
            "theme": self.theme,
            "category": self.category,
            "related_timeline_events": list(self.related_timeline_events),
            "recommendations": list(self.recommendations),
            "generated_by": self.generated_by,
            "supporting_metrics": dict(self.supporting_metrics),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Hypothesis:
        d = dict(d)
        d["status"] = HypothesisStatus(d.get("status", "candidate"))
        if "generated_at" in d and d["generated_at"]:
            d["generated_at"] = datetime.fromisoformat(d["generated_at"])
        else:
            d["generated_at"] = datetime.now().replace(microsecond=0)
        d.pop("confidence_band", None)
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def confidence_band(self) -> ConfidenceBand:
        return ConfidenceBand.from_score(self.confidence)
