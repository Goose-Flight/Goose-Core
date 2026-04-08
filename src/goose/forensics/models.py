"""Forensic case data models for Goose-Core.

These are the foundational types for the case-oriented investigation system.
All forensic workflows operate on these models.

Sprint 1 — Case & Evidence Foundation
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CaseStatus(str, Enum):
    OPEN = "open"
    ANALYZING = "analyzing"
    REVIEW = "review"
    CLOSED = "closed"
    ARCHIVED = "archived"


class AuditAction(str, Enum):
    CASE_CREATED = "case_created"
    EVIDENCE_INGESTED = "evidence_ingested"
    EVIDENCE_ACCESSED = "evidence_accessed"
    PARSE_STARTED = "parse_started"
    PARSE_COMPLETED = "parse_completed"
    PARSE_FAILED = "parse_failed"
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_FAILED = "analysis_failed"
    CASE_EXPORTED = "case_exported"
    CASE_STATUS_CHANGED = "case_status_changed"


# ---------------------------------------------------------------------------
# Evidence models
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    """A single piece of evidence attached to a case.

    The original file is copied immutably into the case directory.
    SHA-256 is always computed. SHA-512 is preferred when available.
    """

    evidence_id: str               # e.g. "EV-0001"
    filename: str                  # original filename (sanitized)
    content_type: str              # e.g. "application/octet-stream"
    size_bytes: int
    sha256: str                    # lowercase hex, always present
    sha512: str | None             # lowercase hex, preferred
    source_acquisition_mode: str   # "upload" | "local_copy" | "remote_fetch"
    source_reference: str | None   # original path or URL if applicable
    stored_path: str               # absolute path to immutable copy in case dir
    acquired_at: datetime
    acquired_by: str               # "gui" | "cli" | "api" | user identifier
    immutable: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["acquired_at"] = self.acquired_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceItem:
        d = dict(d)
        d["acquired_at"] = datetime.fromisoformat(d["acquired_at"])
        return cls(**d)


@dataclass
class EvidenceManifest:
    """Hash manifest for all evidence in a case.

    Written (and re-written) by CaseService after each evidence ingest.
    Immutable in the sense that prior versions should be preserved via audit.
    """

    manifest_version: str = "1.0"
    case_id: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))
    evidence: list[EvidenceItem] = field(default_factory=list)
    # maps evidence_id -> list of derived artifact paths produced from that evidence
    derived_artifacts: dict[str, list[str]] = field(default_factory=dict)
    retention_policy: str = "indefinite"

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "case_id": self.case_id,
            "generated_at": self.generated_at.isoformat(),
            "evidence": [e.to_dict() for e in self.evidence],
            "derived_artifacts": self.derived_artifacts,
            "retention_policy": self.retention_policy,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceManifest:
        d = dict(d)
        d["generated_at"] = datetime.fromisoformat(d["generated_at"])
        d["evidence"] = [EvidenceItem.from_dict(e) for e in d.get("evidence", [])]
        return cls(**d)


# ---------------------------------------------------------------------------
# Case models
# ---------------------------------------------------------------------------

@dataclass
class AnalysisRun:
    """Record of a single analysis execution on a case."""

    run_id: str
    started_at: datetime
    completed_at: datetime | None
    plugin_versions: dict[str, str]    # plugin_id -> version string
    ruleset_version: str | None
    findings_count: int
    status: str                        # "completed" | "failed" | "in_progress"
    engine_version: str = ""           # goose version at time of run — required for replay
    tuning_profile: str | None = None  # named tuning profile if non-default
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "plugin_versions": self.plugin_versions,
            "ruleset_version": self.ruleset_version,
            "findings_count": self.findings_count,
            "status": self.status,
            "engine_version": self.engine_version,
            "tuning_profile": self.tuning_profile,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnalysisRun:
        d = dict(d)
        d["started_at"] = datetime.fromisoformat(d["started_at"])
        if d.get("completed_at"):
            d["completed_at"] = datetime.fromisoformat(d["completed_at"])
        return cls(**d)


@dataclass
class CaseExport:
    """Record of an export produced from a case."""

    export_id: str
    exported_at: datetime
    export_path: str
    bundle_version: str
    includes_replay: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["exported_at"] = self.exported_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CaseExport:
        d = dict(d)
        d["exported_at"] = datetime.fromisoformat(d["exported_at"])
        return cls(**d)


@dataclass
class Case:
    """A forensic investigation case.

    The case is the top-level container for evidence, analysis runs, and exports.
    Persisted as case.json in the case directory.
    """

    case_id: str                                       # e.g. "CASE-2026-000001"
    created_at: datetime
    created_by: str                                    # "gui" | "cli" | actor identifier
    status: CaseStatus = CaseStatus.OPEN
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    engine_version: str = ""                           # goose package version at time of creation
    ruleset_version: str | None = None
    plugin_policy_version: str | None = None
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    analysis_runs: list[AnalysisRun] = field(default_factory=list)
    exports: list[CaseExport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "status": self.status.value,
            "tags": self.tags,
            "notes": self.notes,
            "engine_version": self.engine_version,
            "ruleset_version": self.ruleset_version,
            "plugin_policy_version": self.plugin_policy_version,
            "evidence_items": [e.to_dict() for e in self.evidence_items],
            "analysis_runs": [r.to_dict() for r in self.analysis_runs],
            "exports": [x.to_dict() for x in self.exports],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Case:
        d = dict(d)
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["status"] = CaseStatus(d.get("status", "open"))
        d["evidence_items"] = [EvidenceItem.from_dict(e) for e in d.get("evidence_items", [])]
        d["analysis_runs"] = [AnalysisRun.from_dict(r) for r in d.get("analysis_runs", [])]
        d["exports"] = [CaseExport.from_dict(x) for x in d.get("exports", [])]
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s: str) -> Case:
        return cls.from_dict(json.loads(s))


# ---------------------------------------------------------------------------
# Provenance model
# ---------------------------------------------------------------------------

@dataclass
class Provenance:
    """Records the full lineage of parsed data back to source evidence.

    Written by the parser framework alongside canonical flight data.
    """

    provenance_version: str = "1.0"    # schema version for forward-compat
    source_evidence_id: str = ""
    parser_name: str = ""
    parser_version: str = ""
    detected_format: str = ""
    parsed_at: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))
    transformation_chain: list[str] = field(default_factory=list)
    config_references: dict[str, str] = field(default_factory=dict)
    engine_version: str = ""
    build_hash: str | None = None
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["parsed_at"] = self.parsed_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Provenance:
        d = dict(d)
        d["parsed_at"] = datetime.fromisoformat(d["parsed_at"])
        return cls(**d)


# ---------------------------------------------------------------------------
# Audit model
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """A single write-once audit record.

    Written to audit/audit_log.jsonl (one JSON object per line, append-only).
    Never updated or deleted.
    """

    event_id: str
    timestamp: datetime
    actor: str                    # "gui" | "cli" | "system" | user identifier
    action: AuditAction
    object_type: str              # "case" | "evidence" | "analysis" | "export"
    object_id: str                # case_id, evidence_id, or run_id
    details: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "action": self.action.value,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "details": self.details,
            "success": self.success,
            "error": self.error,
        }

    def to_jsonl(self) -> str:
        """Single-line JSON for audit_log.jsonl."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuditEntry:
        d = dict(d)
        d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        d["action"] = AuditAction(d["action"])
        return cls(**d)
