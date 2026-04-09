"""Tests for the v11 Strategy Sprint Quick Analysis flow."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.web import cases_api
from goose.web.app import create_app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE_ULG = FIXTURES / "px4_normal_flight.ulg"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    svc = CaseService(base_dir=tmp_path / "cases")
    cases_api._set_service(svc)
    app = create_app()
    return TestClient(app)


def _load_fixture() -> bytes:
    if not SAMPLE_ULG.exists():
        pytest.skip(f"Sample ULG fixture missing: {SAMPLE_ULG}")
    return SAMPLE_ULG.read_bytes()


class TestQuickAnalysis:
    def test_returns_findings(self, client: TestClient):
        content = _load_fixture()
        files = {"file": ("flight.ulg", content, "application/octet-stream")}
        r = client.post(
            "/api/quick-analysis",
            files=files,
            data={"profile": "default"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["persisted"] is False
        assert "findings" in data
        assert "hypotheses" in data
        assert "summary" in data
        assert data["profile"]["profile_id"] == "default"

    def test_uses_profile_default_plugins(self, client: TestClient):
        content = _load_fixture()
        files = {"file": ("flight.ulg", content, "application/octet-stream")}
        r = client.post(
            "/api/quick-analysis",
            files=files,
            data={"profile": "racer"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Racer profile declares 4 default plugins — runner should use them
        # (or fall back to all, but never zero).
        assert data["summary"]["plugins_run"] >= 1
        assert data["profile"]["profile_id"] == "racer"

    def test_no_case_created(self, client: TestClient):
        # Confirm no cases exist before
        before = client.get("/api/cases").json()
        assert before["count"] == 0

        content = _load_fixture()
        files = {"file": ("flight.ulg", content, "application/octet-stream")}
        r = client.post(
            "/api/quick-analysis",
            files=files,
            data={"profile": "shop_repair"},
        )
        assert r.status_code == 200

        # Still zero cases
        after = client.get("/api/cases").json()
        assert after["count"] == 0

    def test_empty_file_rejected(self, client: TestClient):
        files = {"file": ("empty.ulg", b"", "application/octet-stream")}
        r = client.post("/api/quick-analysis", files=files, data={"profile": "default"})
        assert r.status_code == 400

    def test_save_as_case_creates_case(self, client: TestClient):
        content = _load_fixture()
        files = {"file": ("flight.ulg", content, "application/octet-stream")}
        r = client.post(
            "/api/quick-analysis/save-as-case",
            files=files,
            data={"profile": "research", "notes": "save test"},
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["ok"] is True
        case_id = data["case_id"]

        # Confirm the case is now present with profile stamped
        detail = client.get(f"/api/cases/{case_id}").json()
        assert detail["case"]["profile"] == "research"
        assert detail["case"]["evidence_count"] == 1
