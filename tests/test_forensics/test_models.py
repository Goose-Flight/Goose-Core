"""Tests for Goose forensic case data models.

Covers: Case, EvidenceItem, EvidenceManifest, Provenance, AuditEntry
and their JSON serialization round-trips.
"""

from __future__ import annotations

import json
from datetime import datetime

from goose.forensics.models import (
    AnalysisRun,
    AuditAction,
    AuditEntry,
    Case,
    CaseStatus,
    EvidenceItem,
    EvidenceManifest,
    Provenance,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 4, 8, 12, 0, 0)


def _make_evidence_item(ev_id: str = "EV-0001") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=ev_id,
        filename="flight.ulg",
        content_type="application/x-ulog",
        size_bytes=1024,
        sha256="a" * 64,
        sha512="b" * 128,
        source_acquisition_mode="upload",
        source_reference=None,
        stored_path="/tmp/cases/CASE-2026-000001/evidence/EV-0001-flight.ulg",  # noqa: S108
        acquired_at=NOW,
        acquired_by="gui",
    )


def _make_case() -> Case:
    return Case(
        case_id="CASE-2026-000001",
        created_at=NOW,
        created_by="cli",
        tags=["test", "sprint1"],
        notes="Test case",
        engine_version="1.3.4",
    )


# ---------------------------------------------------------------------------
# EvidenceItem tests
# ---------------------------------------------------------------------------

class TestEvidenceItem:
    def test_creation(self):
        ev = _make_evidence_item()
        assert ev.evidence_id == "EV-0001"
        assert ev.immutable is True
        assert ev.sha256 == "a" * 64

    def test_json_roundtrip(self):
        ev = _make_evidence_item()
        d = ev.to_dict()
        ev2 = EvidenceItem.from_dict(d)
        assert ev2.evidence_id == ev.evidence_id
        assert ev2.sha256 == ev.sha256
        assert ev2.sha512 == ev.sha512
        assert ev2.acquired_at == ev.acquired_at
        assert ev2.immutable is True

    def test_json_roundtrip_null_sha512(self):
        ev = _make_evidence_item()
        ev.sha512 = None
        d = ev.to_dict()
        ev2 = EvidenceItem.from_dict(d)
        assert ev2.sha512 is None

    def test_json_roundtrip_null_source_reference(self):
        ev = _make_evidence_item()
        d = ev.to_dict()
        ev2 = EvidenceItem.from_dict(d)
        assert ev2.source_reference is None


# ---------------------------------------------------------------------------
# EvidenceManifest tests
# ---------------------------------------------------------------------------

class TestEvidenceManifest:
    def test_creation(self):
        manifest = EvidenceManifest(case_id="CASE-2026-000001")
        assert manifest.manifest_version == "1.0"
        assert manifest.evidence == []

    def test_json_roundtrip_empty(self):
        m = EvidenceManifest(case_id="CASE-2026-000001", generated_at=NOW)
        d = m.to_dict()
        m2 = EvidenceManifest.from_dict(d)
        assert m2.case_id == "CASE-2026-000001"
        assert m2.evidence == []
        assert m2.generated_at == NOW

    def test_json_roundtrip_with_evidence(self):
        m = EvidenceManifest(
            case_id="CASE-2026-000001",
            generated_at=NOW,
            evidence=[_make_evidence_item("EV-0001"), _make_evidence_item("EV-0002")],
        )
        d = m.to_dict()
        m2 = EvidenceManifest.from_dict(d)
        assert len(m2.evidence) == 2
        assert m2.evidence[0].evidence_id == "EV-0001"
        assert m2.evidence[1].evidence_id == "EV-0002"


# ---------------------------------------------------------------------------
# Case tests
# ---------------------------------------------------------------------------

class TestCase:
    def test_creation(self):
        case = _make_case()
        assert case.case_id == "CASE-2026-000001"
        assert case.status == CaseStatus.OPEN
        assert case.evidence_items == []
        assert case.analysis_runs == []
        assert case.exports == []

    def test_status_enum(self):
        case = _make_case()
        case.status = CaseStatus.ANALYZING
        assert case.status == CaseStatus.ANALYZING

    def test_json_roundtrip_minimal(self):
        case = _make_case()
        case2 = Case.from_json(case.to_json())
        assert case2.case_id == case.case_id
        assert case2.created_by == "cli"
        assert case2.status == CaseStatus.OPEN
        assert case2.tags == ["test", "sprint1"]
        assert case2.notes == "Test case"
        assert case2.created_at == NOW

    def test_json_roundtrip_with_evidence(self):
        case = _make_case()
        case.evidence_items = [_make_evidence_item()]
        case2 = Case.from_json(case.to_json())
        assert len(case2.evidence_items) == 1
        assert case2.evidence_items[0].evidence_id == "EV-0001"

    def test_json_roundtrip_with_analysis_run(self):
        case = _make_case()
        run = AnalysisRun(
            run_id="RUN-0001",
            started_at=NOW,
            completed_at=NOW,
            plugin_versions={"crash_detection": "1.0.0"},
            ruleset_version=None,
            findings_count=3,
            status="completed",
        )
        case.analysis_runs = [run]
        case2 = Case.from_json(case.to_json())
        assert len(case2.analysis_runs) == 1
        assert case2.analysis_runs[0].run_id == "RUN-0001"
        assert case2.analysis_runs[0].findings_count == 3

    def test_to_json_is_valid_json(self):
        case = _make_case()
        raw = case.to_json()
        parsed = json.loads(raw)
        assert parsed["case_id"] == "CASE-2026-000001"
        assert parsed["status"] == "open"

    def test_status_value_in_json(self):
        case = _make_case()
        case.status = CaseStatus.CLOSED
        d = json.loads(case.to_json())
        assert d["status"] == "closed"


# ---------------------------------------------------------------------------
# Provenance tests
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_creation(self):
        p = Provenance(
            source_evidence_id="EV-0001",
            parser_name="ULogParser",
            parser_version="1.0.0",
            detected_format="ulog",
            parsed_at=NOW,
        )
        assert p.source_evidence_id == "EV-0001"
        assert p.assumptions == []

    def test_json_roundtrip(self):
        p = Provenance(
            source_evidence_id="EV-0001",
            parser_name="ULogParser",
            parser_version="1.0.0",
            detected_format="ulog",
            parsed_at=NOW,
            assumptions=["timebase assumed monotonic"],
        )
        d = p.to_dict()
        p2 = Provenance.from_dict(d)
        assert p2.source_evidence_id == "EV-0001"
        assert p2.parsed_at == NOW
        assert p2.assumptions == ["timebase assumed monotonic"]


# ---------------------------------------------------------------------------
# AuditEntry tests
# ---------------------------------------------------------------------------

class TestAuditEntry:
    def test_creation(self):
        entry = AuditEntry(
            event_id="ABCD1234",
            timestamp=NOW,
            actor="cli",
            action=AuditAction.CASE_CREATED,
            object_type="case",
            object_id="CASE-2026-000001",
        )
        assert entry.success is True
        assert entry.error is None

    def test_to_jsonl_is_single_line(self):
        entry = AuditEntry(
            event_id="ABCD1234",
            timestamp=NOW,
            actor="gui",
            action=AuditAction.EVIDENCE_INGESTED,
            object_type="evidence",
            object_id="EV-0001",
            details={"sha256": "a" * 64},
        )
        line = entry.to_jsonl()
        assert "\n" not in line
        parsed = json.loads(line)
        assert parsed["action"] == "evidence_ingested"
        assert parsed["details"]["sha256"] == "a" * 64

    def test_json_roundtrip(self):
        entry = AuditEntry(
            event_id="XYZ",
            timestamp=NOW,
            actor="system",
            action=AuditAction.ANALYSIS_COMPLETED,
            object_type="analysis",
            object_id="RUN-0001",
            success=True,
        )
        d = entry.to_dict()
        entry2 = AuditEntry.from_dict(d)
        assert entry2.event_id == "XYZ"
        assert entry2.action == AuditAction.ANALYSIS_COMPLETED
        assert entry2.timestamp == NOW

    def test_failed_audit_entry(self):
        entry = AuditEntry(
            event_id="ERR",
            timestamp=NOW,
            actor="cli",
            action=AuditAction.PARSE_FAILED,
            object_type="case",
            object_id="CASE-2026-000001",
            success=False,
            error="Corrupt ULog header",
        )
        d = entry.to_dict()
        entry2 = AuditEntry.from_dict(d)
        assert entry2.success is False
        assert entry2.error == "Corrupt ULog header"


# ---------------------------------------------------------------------------
# CaseStatus enum tests
# ---------------------------------------------------------------------------

class TestCaseStatus:
    def test_all_values(self):
        assert CaseStatus.OPEN.value == "open"
        assert CaseStatus.ANALYZING.value == "analyzing"
        assert CaseStatus.REVIEW.value == "review"
        assert CaseStatus.CLOSED.value == "closed"
        assert CaseStatus.ARCHIVED.value == "archived"

    def test_from_string(self):
        assert CaseStatus("open") == CaseStatus.OPEN
        assert CaseStatus("closed") == CaseStatus.CLOSED
