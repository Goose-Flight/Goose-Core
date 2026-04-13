"""Tests for the case-oriented API routes (Sprint 2).

Covers: POST /api/cases, GET /api/cases, GET /api/cases/{id},
        POST /api/cases/{id}/evidence, GET /api/cases/{id}/evidence,
        GET /api/cases/{id}/audit, PATCH /api/cases/{id}/status,
        and backward-compatibility of POST /api/analyze (shim).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.web import cases_api
from goose.web.app import create_app


@pytest.fixture
def tmp_case_service(tmp_path: Path) -> CaseService:
    svc = CaseService(base_dir=tmp_path / "cases")
    return svc


@pytest.fixture
def client(tmp_case_service: CaseService) -> TestClient:
    """TestClient with an injected in-memory CaseService."""
    cases_api._set_service(tmp_case_service)
    app = create_app()
    return TestClient(app)


@pytest.fixture
def fake_ulg() -> bytes:
    """Minimal fake ULog bytes (not a real log — just for upload tests)."""
    return b"ULog\x00" + b"\xff" * 256


# ---------------------------------------------------------------------------
# POST /api/cases
# ---------------------------------------------------------------------------


class TestCreateCase:
    def test_create_returns_201(self, client: TestClient):
        res = client.post("/api/cases", json={"created_by": "test", "tags": [], "notes": ""})
        assert res.status_code == 201

    def test_create_returns_case_id(self, client: TestClient):
        res = client.post("/api/cases", json={})
        data = res.json()
        assert data["ok"] is True
        assert data["case"]["case_id"].startswith("CASE-")

    def test_create_with_notes_and_tags(self, client: TestClient):
        res = client.post("/api/cases", json={"notes": "test investigation", "tags": ["px4", "crash"]})
        data = res.json()
        assert data["case"]["notes"] == "test investigation"
        assert "px4" in data["case"]["tags"]

    def test_create_status_is_open(self, client: TestClient):
        res = client.post("/api/cases", json={})
        assert res.json()["case"]["status"] == "open"


# ---------------------------------------------------------------------------
# GET /api/cases
# ---------------------------------------------------------------------------


class TestListCases:
    def test_empty_list(self, client: TestClient):
        res = client.get("/api/cases")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["cases"] == []
        assert data["count"] == 0

    def test_lists_created_cases(self, client: TestClient):
        client.post("/api/cases", json={})
        client.post("/api/cases", json={})
        res = client.get("/api/cases")
        data = res.json()
        assert data["count"] == 2

    def test_summary_fields_present(self, client: TestClient):
        client.post("/api/cases", json={"notes": "x"})
        cases = client.get("/api/cases").json()["cases"]
        case = cases[0]
        for field in ["case_id", "created_at", "status", "evidence_count", "analysis_run_count"]:
            assert field in case


# ---------------------------------------------------------------------------
# GET /api/cases/{case_id}
# ---------------------------------------------------------------------------


class TestGetCase:
    def test_get_existing_case(self, client: TestClient):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["case"]["case_id"] == case_id

    def test_get_nonexistent_case(self, client: TestClient):
        res = client.get("/api/cases/CASE-9999-999999")
        assert res.status_code == 404

    def test_detail_includes_evidence_items(self, client: TestClient):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        data = client.get(f"/api/cases/{case_id}").json()
        assert "evidence_items" in data["case"]


# ---------------------------------------------------------------------------
# POST /api/cases/{case_id}/evidence
# ---------------------------------------------------------------------------


class TestIngestEvidence:
    def test_upload_returns_201(self, client: TestClient, fake_ulg: bytes):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("flight.ulg", io.BytesIO(fake_ulg), "application/octet-stream")},
        )
        assert res.status_code == 201

    def test_upload_returns_evidence_item(self, client: TestClient, fake_ulg: bytes):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("flight.ulg", io.BytesIO(fake_ulg), "application/octet-stream")},
        )
        data = res.json()
        assert data["ok"] is True
        ev = data["evidence"]
        assert ev["evidence_id"] == "EV-0001"
        assert ev["filename"] == "flight.ulg"
        assert ev["immutable"] is True
        assert len(ev["sha256"]) == 64
        assert ev["sha512"] is not None

    def test_upload_to_nonexistent_case(self, client: TestClient, fake_ulg: bytes):
        res = client.post(
            "/api/cases/CASE-9999-999999/evidence",
            files={"file": ("flight.ulg", io.BytesIO(fake_ulg), "application/octet-stream")},
        )
        assert res.status_code == 404

    def test_evidence_appears_in_case_detail(self, client: TestClient, fake_ulg: bytes):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("flight.ulg", io.BytesIO(fake_ulg), "application/octet-stream")},
        )
        ev_list = client.get(f"/api/cases/{case_id}/evidence").json()["evidence"]
        assert len(ev_list) == 1
        assert ev_list[0]["filename"] == "flight.ulg"

    def test_multiple_uploads(self, client: TestClient, fake_ulg: bytes):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        for i in range(3):
            client.post(
                f"/api/cases/{case_id}/evidence",
                files={"file": (f"flight{i}.ulg", io.BytesIO(fake_ulg), "application/octet-stream")},
            )
        ev_list = client.get(f"/api/cases/{case_id}/evidence").json()["evidence"]
        assert len(ev_list) == 3
        assert ev_list[0]["evidence_id"] == "EV-0001"
        assert ev_list[2]["evidence_id"] == "EV-0003"


# ---------------------------------------------------------------------------
# GET /api/cases/{case_id}/evidence
# ---------------------------------------------------------------------------


class TestListEvidence:
    def test_empty_evidence_list(self, client: TestClient):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/evidence")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["evidence"] == []
        assert data["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/cases/{case_id}/audit
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_has_create_entry(self, client: TestClient):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/audit")
        data = res.json()
        assert data["ok"] is True
        assert data["count"] >= 1
        actions = [e["action"] for e in data["audit"]]
        assert "case_created" in actions

    def test_audit_grows_after_ingest(self, client: TestClient, fake_ulg: bytes):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        initial = client.get(f"/api/cases/{case_id}/audit").json()["count"]
        client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("flight.ulg", io.BytesIO(fake_ulg))},
        )
        updated = client.get(f"/api/cases/{case_id}/audit").json()["count"]
        assert updated == initial + 1

    def test_audit_nonexistent_case(self, client: TestClient):
        res = client.get("/api/cases/CASE-9999-999999/audit")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/cases/{case_id}/status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    def test_update_status(self, client: TestClient):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.patch(f"/api/cases/{case_id}/status", json={"status": "review"})
        assert res.status_code == 200
        assert res.json()["case"]["status"] == "review"

    def test_invalid_status(self, client: TestClient):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.patch(f"/api/cases/{case_id}/status", json={"status": "invalid_status"})
        assert res.status_code == 400

    def test_status_change_appears_in_audit(self, client: TestClient):
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        client.patch(f"/api/cases/{case_id}/status", json={"status": "closed", "actor": "analyst"})
        audit = client.get(f"/api/cases/{case_id}/audit").json()["audit"]
        status_entries = [e for e in audit if e["action"] == "case_status_changed"]
        assert len(status_entries) == 1
        assert status_entries[0]["details"]["to"] == "closed"


# ---------------------------------------------------------------------------
# POST /api/analyze — backward-compatibility shim
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointDeprecated:
    """POST /api/analyze was removed in Convergence Sprint 1.

    It bypassed the case system and emitted thin findings without evidence
    references, audit trail, or tuning provenance.  It now returns 410 Gone
    for all inputs.  See tests/test_convergence/ for the replacement tests.
    """

    def test_returns_410_for_any_upload(self, client: TestClient):
        res = client.post(
            "/api/analyze",
            files={"file": ("flight.ulg", io.BytesIO(b"fake"), "application/octet-stream")},
        )
        assert res.status_code == 410

    def test_returns_gone_error_key(self, client: TestClient):
        res = client.post(
            "/api/analyze",
            files={"file": ("empty.ulg", io.BytesIO(b""), "application/octet-stream")},
        )
        assert res.json()["error"] == "gone"

    def test_returns_alternatives(self, client: TestClient):
        res = client.post(
            "/api/analyze",
            files={"file": ("x.ulg", io.BytesIO(b"x"), "application/octet-stream")},
        )
        assert "alternatives" in res.json()
