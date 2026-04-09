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


class AttachmentType(str, Enum):
    """v11 Strategy Sprint — types of non-telemetry attachments a user can add to a case."""
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    GCS_LOG = "gcs_log"
    SECONDARY_LOG = "secondary_log"
    NOTE = "note"
    REPORT_APPENDIX = "report_appendix"
    CHECKLIST = "checklist"
    EXTERNAL_DATA = "external_data"
    OTHER = "other"


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
    """Record of a single analysis execution on a case.

    Extended in the Advanced Forensic Validation Sprint with richer metadata
    for replay determinism, run comparison, and tuning provenance. All new
    fields have defaults for backward compatibility with existing case.json.
    """

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
    # --- Advanced Forensic Validation Sprint additions ---
    case_id: str = ""
    evidence_id: str = ""
    parser_name: str = ""
    parser_version: str = ""
    plugin_ids_used: list[str] = field(default_factory=list)
    plugin_trust_states: dict[str, str] = field(default_factory=dict)
    tuning_profile_id: str = "default"
    tuning_profile_version: str = "1.0.0"
    critical_count: int = 0
    warning_count: int = 0
    hypotheses_count: int = 0
    is_replay: bool = False
    source_run_id: str | None = None
    replay_id: str | None = None
    # v11 Strategy Sprint — active user profile at time of run.
    # Profiles bias defaults but do not change forensic truth. Recorded here
    # so replays can reproduce the same plugin ordering used for the run.
    profile_id: str = "default"

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
            "case_id": self.case_id,
            "evidence_id": self.evidence_id,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "plugin_ids_used": self.plugin_ids_used,
            "plugin_trust_states": self.plugin_trust_states,
            "tuning_profile_id": self.tuning_profile_id,
            "tuning_profile_version": self.tuning_profile_version,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "hypotheses_count": self.hypotheses_count,
            "is_replay": self.is_replay,
            "source_run_id": self.source_run_id,
            "replay_id": self.replay_id,
            "profile_id": self.profile_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnalysisRun:
        d = dict(d)
        d["started_at"] = datetime.fromisoformat(d["started_at"])
        if d.get("completed_at"):
            d["completed_at"] = datetime.fromisoformat(d["completed_at"])
        # Drop keys unknown to the dataclass (forward-compat)
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
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

    v11 Strategy Sprint — Case metadata extension
    All new fields are optional and default to None or empty strings so existing
    case.json files continue to load unchanged. ``from_dict`` ignores unknown
    keys for forward-compatibility with future fields.
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

    # --- v11 Strategy Sprint: operational context ---
    mission_id: str | None = None
    sortie_id: str | None = None
    operation_type: str | None = None       # "training", "commercial", "research", "race", "test", "operational"
    event_type: str | None = None           # "crash", "anomaly", "normal", "test_flight"
    event_classification: str | None = None # "mishap", "incident", "close_call", "performance_issue", "none"
    event_severity: str | None = None       # "critical", "major", "minor", "none"
    date_time_start: str | None = None      # ISO timestamp of the actual event (not case creation)
    date_time_end: str | None = None
    location_name: str | None = None
    operating_area: str | None = None
    environment_summary: str | None = None  # weather, wind, visibility notes

    # --- v11 Strategy Sprint: platform / system ---
    platform_name: str | None = None
    platform_type: str | None = None        # "multirotor", "fixed_wing", "vtol", "helicopter"
    serial_number: str | None = None
    firmware_version: str | None = None
    hardware_config: str | None = None
    payload_config: str | None = None
    battery_config: str | None = None
    propulsion_notes: str | None = None
    recent_changes: str | None = None       # "replaced motor 2, reflashed FC"

    # --- v11 Strategy Sprint: human / org ---
    operator_name: str | None = None
    team_name: str | None = None
    unit_name: str | None = None
    organization: str | None = None
    customer_name: str | None = None
    ticket_id: str | None = None
    technician_name: str | None = None
    tester_name: str | None = None

    # --- v11 Strategy Sprint: investigation / outcome ---
    damage_summary: str | None = None
    loss_summary: str | None = None
    recommendations: str | None = None
    corrective_actions: str | None = None
    closure_notes: str | None = None

    # --- v11 Strategy Sprint: profile ---
    profile: str = "default"   # "racer" | "research" | "shop_repair" | "factory_qa" | "gov_mil" | "advanced" | "default"

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
            # Operational context
            "mission_id": self.mission_id,
            "sortie_id": self.sortie_id,
            "operation_type": self.operation_type,
            "event_type": self.event_type,
            "event_classification": self.event_classification,
            "event_severity": self.event_severity,
            "date_time_start": self.date_time_start,
            "date_time_end": self.date_time_end,
            "location_name": self.location_name,
            "operating_area": self.operating_area,
            "environment_summary": self.environment_summary,
            # Platform
            "platform_name": self.platform_name,
            "platform_type": self.platform_type,
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "hardware_config": self.hardware_config,
            "payload_config": self.payload_config,
            "battery_config": self.battery_config,
            "propulsion_notes": self.propulsion_notes,
            "recent_changes": self.recent_changes,
            # Human / org
            "operator_name": self.operator_name,
            "team_name": self.team_name,
            "unit_name": self.unit_name,
            "organization": self.organization,
            "customer_name": self.customer_name,
            "ticket_id": self.ticket_id,
            "technician_name": self.technician_name,
            "tester_name": self.tester_name,
            # Investigation / outcome
            "damage_summary": self.damage_summary,
            "loss_summary": self.loss_summary,
            "recommendations": self.recommendations,
            "corrective_actions": self.corrective_actions,
            "closure_notes": self.closure_notes,
            # Profile
            "profile": self.profile,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Case:
        d = dict(d)
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["status"] = CaseStatus(d.get("status", "open"))
        d["evidence_items"] = [EvidenceItem.from_dict(e) for e in d.get("evidence_items", [])]
        d["analysis_runs"] = [AnalysisRun.from_dict(r) for r in d.get("analysis_runs", [])]
        d["exports"] = [CaseExport.from_dict(x) for x in d.get("exports", [])]
        # Forward-compat: drop unknown keys (any future fields)
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
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

    Schema versioning
    -----------------
    ``provenance_version`` is the schema version for this record.
    ``contract_version`` identifies the parser contract under which this
    provenance was produced — i.e., which version of the ParseResult/
    ParseDiagnostics API was in use.  Increment ``contract_version`` when
    the parser contract itself changes in a way that affects replay
    compatibility (e.g. new required fields in ParseResult, changed
    confidence model, new canonical stream list).
    """

    provenance_version: str = "1.0"     # schema version for this record
    contract_version: str = "1.0"       # parser contract version (ParseResult API)
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
        # Forward-compat: ignore unknown keys from future versions
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
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


# ---------------------------------------------------------------------------
# Attachment model (v11 Strategy Sprint)
# ---------------------------------------------------------------------------

@dataclass
class Attachment:
    """A non-telemetry attachment belonging to a case.

    Photos, videos, GCS logs, checklists, notes, report appendices, etc.
    Stored immutably under ``cases/{case_id}/attachments/`` with a manifest
    listing all attachments for the case. Distinct from EvidenceItem (which
    is the primary flight log evidence the forensic pipeline operates on).
    """

    attachment_id: str
    case_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    attachment_type: AttachmentType
    stored_path: str
    uploaded_at: str                 # ISO timestamp
    uploaded_by: str = "user"
    sha512: str = ""
    immutable: bool = True
    notes: str = ""
    related_evidence_id: str | None = None
    related_timeline_time: float | None = None
    provenance_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "case_id": self.case_id,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "attachment_type": self.attachment_type.value,
            "stored_path": self.stored_path,
            "uploaded_at": self.uploaded_at,
            "uploaded_by": self.uploaded_by,
            "sha512": self.sha512,
            "immutable": self.immutable,
            "notes": self.notes,
            "related_evidence_id": self.related_evidence_id,
            "related_timeline_time": self.related_timeline_time,
            "provenance_summary": self.provenance_summary,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Attachment:
        d = dict(d)
        at = d.get("attachment_type", "other")
        if isinstance(at, str):
            try:
                d["attachment_type"] = AttachmentType(at)
            except ValueError:
                d["attachment_type"] = AttachmentType.OTHER
        # Forward-compat: drop unknown keys
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)
