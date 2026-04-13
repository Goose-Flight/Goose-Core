"""Tests for CaseService: case creation, evidence ingest, immutability, hashing, audit trail.

These are forensic primitives — tests must be thorough and unambiguous.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from goose.forensics.case_service import CaseService
from goose.forensics.hashing import sha256_file
from goose.forensics.models import AuditAction, CaseStatus


@pytest.fixture
def svc(tmp_path: Path) -> CaseService:
    """CaseService backed by a temp directory."""
    return CaseService(base_dir=tmp_path / "cases")


@pytest.fixture
def sample_log(tmp_path: Path) -> Path:
    """A small fake ULog file to use as test evidence."""
    p = tmp_path / "test_flight.ulg"
    p.write_bytes(b"ULog\x00" + b"\xff" * 512)
    return p


# ---------------------------------------------------------------------------
# Case creation
# ---------------------------------------------------------------------------

class TestCreateCase:
    def test_creates_case_with_id(self, svc: CaseService):
        case = svc.create_case(created_by="cli")
        assert case.case_id.startswith("CASE-")
        assert case.created_by == "cli"
        assert case.status == CaseStatus.OPEN

    def test_creates_directory_structure(self, svc: CaseService):
        case = svc.create_case()
        case_dir = svc.case_dir(case.case_id)
        assert (case_dir / "evidence").is_dir()
        assert (case_dir / "manifests").is_dir()
        assert (case_dir / "parsed").is_dir()
        assert (case_dir / "analysis").is_dir()
        assert (case_dir / "audit").is_dir()
        assert (case_dir / "exports").is_dir()
        assert (case_dir / "case.json").is_file()

    def test_case_persists_across_reload(self, svc: CaseService):
        case = svc.create_case(created_by="gui", tags=["sprint1"], notes="test")
        reloaded = svc.get_case(case.case_id)
        assert reloaded.case_id == case.case_id
        assert reloaded.created_by == "gui"
        assert reloaded.tags == ["sprint1"]
        assert reloaded.notes == "test"

    def test_creates_audit_entry_on_create(self, svc: CaseService):
        case = svc.create_case(created_by="cli")
        audit = svc.get_audit_log(case.case_id)
        assert len(audit) == 1
        assert audit[0].action == AuditAction.CASE_CREATED
        assert audit[0].actor == "cli"
        assert audit[0].object_id == case.case_id

    def test_sequential_case_ids(self, svc: CaseService):
        c1 = svc.create_case()
        c2 = svc.create_case()
        c3 = svc.create_case()
        # IDs should be distinct
        ids = {c1.case_id, c2.case_id, c3.case_id}
        assert len(ids) == 3

    def test_engine_version_recorded(self, svc: CaseService):
        case = svc.create_case()
        assert case.engine_version != ""


# ---------------------------------------------------------------------------
# Evidence ingest
# ---------------------------------------------------------------------------

class TestIngestEvidence:
    def test_returns_evidence_item(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log, acquired_by="cli")
        assert ev.evidence_id == "EV-0001"
        assert ev.filename == "test_flight.ulg"
        assert ev.immutable is True
        assert ev.acquired_by == "cli"

    def test_file_is_copied(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log)
        stored = Path(ev.stored_path)
        assert stored.exists()
        assert stored.read_bytes() == sample_log.read_bytes()

    def test_original_is_not_modified(self, svc: CaseService, sample_log: Path):
        original_content = sample_log.read_bytes()
        original_mtime = sample_log.stat().st_mtime
        case = svc.create_case()
        svc.ingest_evidence(case.case_id, sample_log)
        assert sample_log.read_bytes() == original_content
        assert sample_log.stat().st_mtime == original_mtime

    def test_stored_copy_is_readonly(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log)
        stored = Path(ev.stored_path)
        mode = stat.S_IMODE(stored.stat().st_mode)
        # Write bits should be cleared
        assert not (mode & stat.S_IWRITE), "Stored evidence must be read-only"
        assert not (mode & stat.S_IWGRP), "Stored evidence must not be group-writable"

    def test_sha256_is_correct(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log)
        expected = sha256_file(ev.stored_path)
        assert ev.sha256 == expected

    def test_sha512_is_present(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log)
        assert ev.sha512 is not None
        assert len(ev.sha512) == 128  # SHA-512 hex = 128 chars

    def test_sha256_matches_original(self, svc: CaseService, sample_log: Path):
        original_sha256 = sha256_file(sample_log)
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log)
        assert ev.sha256 == original_sha256

    def test_evidence_appears_in_case(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log)
        reloaded = svc.get_case(case.case_id)
        assert len(reloaded.evidence_items) == 1
        assert reloaded.evidence_items[0].evidence_id == ev.evidence_id

    def test_manifest_is_written(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        svc.ingest_evidence(case.case_id, sample_log)
        manifest_path = svc.case_dir(case.case_id) / "manifests" / "evidence_manifest.json"
        assert manifest_path.exists()
        manifest_data = json.loads(manifest_path.read_text())
        assert manifest_data["case_id"] == case.case_id
        assert len(manifest_data["evidence"]) == 1
        assert manifest_data["evidence"][0]["sha256"] != ""

    def test_audit_entry_on_ingest(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log, acquired_by="gui")
        audit = svc.get_audit_log(case.case_id)
        ingest_entries = [a for a in audit if a.action == AuditAction.EVIDENCE_INGESTED]
        assert len(ingest_entries) == 1
        assert ingest_entries[0].object_id == ev.evidence_id
        assert ingest_entries[0].actor == "gui"
        assert ingest_entries[0].details["sha256"] == ev.sha256

    def test_multiple_evidence_items(self, svc: CaseService, tmp_path: Path):
        case = svc.create_case()
        f1 = tmp_path / "flight1.ulg"
        f2 = tmp_path / "flight2.ulg"
        f1.write_bytes(b"ULog\x01" * 10)
        f2.write_bytes(b"ULog\x02" * 10)

        ev1 = svc.ingest_evidence(case.case_id, f1)
        ev2 = svc.ingest_evidence(case.case_id, f2)

        assert ev1.evidence_id == "EV-0001"
        assert ev2.evidence_id == "EV-0002"

        reloaded = svc.get_case(case.case_id)
        assert len(reloaded.evidence_items) == 2

    def test_missing_source_raises(self, svc: CaseService):
        case = svc.create_case()
        with pytest.raises(FileNotFoundError):
            svc.ingest_evidence(case.case_id, "/nonexistent/path/flight.ulg")

    def test_ingest_bytes(self, svc: CaseService):
        case = svc.create_case()
        content = b"ULog\x00" + b"\xAB" * 256
        ev = svc.ingest_evidence_bytes(
            case.case_id, "upload.ulg", content, acquired_by="gui"
        )
        assert ev.evidence_id == "EV-0001"
        assert ev.filename == "upload.ulg"
        assert ev.source_acquisition_mode == "upload"
        assert ev.source_reference is None
        stored = Path(ev.stored_path)
        assert stored.read_bytes() == content


# ---------------------------------------------------------------------------
# Evidence integrity verification
# ---------------------------------------------------------------------------

class TestVerifyEvidence:
    def test_verify_intact_evidence(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        ev = svc.ingest_evidence(case.case_id, sample_log)
        assert svc.verify_evidence(case.case_id, ev.evidence_id) is True

    def test_verify_missing_evidence_id(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        svc.ingest_evidence(case.case_id, sample_log)
        assert svc.verify_evidence(case.case_id, "EV-9999") is False


# ---------------------------------------------------------------------------
# Case listing and status
# ---------------------------------------------------------------------------

class TestCaseListing:
    def test_list_cases_empty(self, svc: CaseService):
        assert svc.list_cases() == []

    def test_list_cases(self, svc: CaseService):
        svc.create_case()
        svc.create_case()
        cases = svc.list_cases()
        assert len(cases) == 2

    def test_get_nonexistent_case(self, svc: CaseService):
        with pytest.raises(FileNotFoundError):
            svc.get_case("CASE-9999-999999")

    def test_update_status(self, svc: CaseService):
        case = svc.create_case()
        updated = svc.update_status(case.case_id, CaseStatus.REVIEW, actor="analyst")
        assert updated.status == CaseStatus.REVIEW
        reloaded = svc.get_case(case.case_id)
        assert reloaded.status == CaseStatus.REVIEW

    def test_status_change_written_to_audit(self, svc: CaseService):
        case = svc.create_case()
        svc.update_status(case.case_id, CaseStatus.CLOSED, actor="admin")
        audit = svc.get_audit_log(case.case_id)
        status_entries = [a for a in audit if a.action == AuditAction.CASE_STATUS_CHANGED]
        assert len(status_entries) == 1
        assert status_entries[0].details["to"] == "closed"


# ---------------------------------------------------------------------------
# Audit log integrity
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_audit_log_is_jsonl(self, svc: CaseService):
        case = svc.create_case()
        audit_path = svc.case_dir(case.case_id) / "audit" / "audit_log.jsonl"
        lines = [ln.strip() for ln in audit_path.read_text().splitlines() if ln.strip()]
        assert len(lines) >= 1
        for line in lines:
            # Each line must be valid JSON
            parsed = json.loads(line)
            assert "event_id" in parsed
            assert "action" in parsed

    def test_audit_log_grows_on_ingest(self, svc: CaseService, sample_log: Path):
        case = svc.create_case()
        initial_audit = svc.get_audit_log(case.case_id)
        svc.ingest_evidence(case.case_id, sample_log)
        updated_audit = svc.get_audit_log(case.case_id)
        assert len(updated_audit) == len(initial_audit) + 1
