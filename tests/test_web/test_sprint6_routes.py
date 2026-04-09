"""Tests for Sprint 6 API routes.

Covers:
  GET  /api/cases/{id}/timeline    — timeline construction
  GET  /api/cases/{id}/charts/data — time-series chart data
  GET  /api/cases/{id}/exports     — export listing
  POST /api/cases/{id}/exports/bundle — bundle creation
  GET  /api/cases/{id}/plugins     — manifest + run info
  GET  /api/cases/{id}/findings    — forensic findings shape
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.web.app import create_app
from goose.web import cases_api


@pytest.fixture
def tmp_case_service(tmp_path: Path) -> CaseService:
    svc = CaseService(base_dir=tmp_path / "cases")
    return svc


@pytest.fixture
def client(tmp_case_service: CaseService) -> TestClient:
    cases_api._set_service(tmp_case_service)
    app = create_app()
    return TestClient(app)


@pytest.fixture
def case_id(client: TestClient) -> str:
    res = client.post("/api/cases", json={"created_by": "test"})
    return res.json()["case"]["case_id"]


@pytest.fixture
def fake_ulg() -> bytes:
    return b"ULog\x00" + b"\xff" * 256


# ---------------------------------------------------------------------------
# GET /api/cases/{id}/timeline
# ---------------------------------------------------------------------------

class TestTimeline:
    def test_timeline_returns_ok(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/timeline")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["timeline_version"] == "1.0"
        assert isinstance(data["events"], list)

    def test_timeline_empty_without_analysis(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/timeline")
        data = res.json()
        assert data["count"] == 0

    def test_timeline_404_nonexistent_case(self, client: TestClient):
        res = client.get("/api/cases/CASE-9999-999999/timeline")
        assert res.status_code == 404

    def test_timeline_populates_after_findings(self, client: TestClient, case_id: str, tmp_case_service: CaseService):
        """If findings are present with timestamps, timeline should include them."""
        case_dir = tmp_case_service.case_dir(case_id)
        analysis_dir = case_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        findings = {
            "findings_version": "2.0",
            "run_id": "RUN-TEST",
            "evidence_id": "EV-0001",
            "generated_at": "2026-01-01T00:00:00",
            "findings": [
                {
                    "finding_id": "FND-001",
                    "title": "Test finding",
                    "severity": "warning",
                    "start_time": 10.0,
                    "end_time": 20.0,
                    "description": "test",
                }
            ],
        }
        (analysis_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")

        res = client.get(f"/api/cases/{case_id}/timeline")
        data = res.json()
        assert data["count"] >= 1
        assert any(e["type"] == "finding" for e in data["events"])


# ---------------------------------------------------------------------------
# GET /api/cases/{id}/charts/data
# ---------------------------------------------------------------------------

class TestChartsData:
    def test_charts_data_returns_ok(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/charts/data")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert isinstance(data["streams"], dict)
        assert isinstance(data["available_streams"], list)

    def test_charts_data_empty_without_evidence(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/charts/data?streams=battery_voltage")
        data = res.json()
        assert data["streams"] == {} or data["message"]

    def test_charts_data_404_nonexistent_case(self, client: TestClient):
        res = client.get("/api/cases/CASE-9999-999999/charts/data")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/cases/{id}/exports
# ---------------------------------------------------------------------------

class TestExports:
    def test_exports_returns_ok(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/exports")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert isinstance(data["exports"], list)
        assert data["count"] == 0

    def test_exports_404_nonexistent_case(self, client: TestClient):
        res = client.get("/api/cases/CASE-9999-999999/exports")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/cases/{id}/exports/bundle
# ---------------------------------------------------------------------------

class TestExportBundle:
    def test_bundle_creates_file(self, client: TestClient, case_id: str, tmp_case_service: CaseService):
        res = client.post(f"/api/cases/{case_id}/exports/bundle")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "filename" in data
        assert data["filename"].startswith("bundle_")
        assert data["size_bytes"] > 0

        # Verify file exists on disk
        exports_dir = tmp_case_service.case_dir(case_id) / "exports"
        assert (exports_dir / data["filename"]).exists()

    def test_bundle_contains_case_data(self, client: TestClient, case_id: str, tmp_case_service: CaseService):
        client.post(f"/api/cases/{case_id}/exports/bundle")
        exports_dir = tmp_case_service.case_dir(case_id) / "exports"
        files = list(exports_dir.iterdir())
        assert len(files) == 1
        bundle = json.loads(files[0].read_text(encoding="utf-8"))
        assert bundle["bundle_version"] == "1.0"
        assert "case_metadata" in bundle
        assert "evidence_manifest" in bundle
        assert "bundle_id" in bundle
        assert "replay_metadata" in bundle

    def test_bundle_404_nonexistent_case(self, client: TestClient):
        res = client.post("/api/cases/CASE-9999-999999/exports/bundle")
        assert res.status_code == 404

    def test_bundle_shows_in_exports_list(self, client: TestClient, case_id: str):
        client.post(f"/api/cases/{case_id}/exports/bundle")
        res = client.get(f"/api/cases/{case_id}/exports")
        data = res.json()
        assert data["count"] == 1
        assert data["exports"][0]["filename"].startswith("bundle_")


# ---------------------------------------------------------------------------
# GET /api/cases/{id}/plugins
# ---------------------------------------------------------------------------

class TestPluginsRoute:
    def test_plugins_returns_manifests(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/plugins")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] == 11  # 11 builtin plugins
        assert isinstance(data["manifests"], list)
        # Check manifest shape
        m = data["manifests"][0]
        assert "plugin_id" in m
        assert "trust_state" in m
        assert "required_streams" in m
        assert "category" in m

    def test_plugins_includes_run_info_when_available(
        self, client: TestClient, case_id: str, tmp_case_service: CaseService
    ):
        """Plugin run info should be included if analysis was run."""
        case_dir = tmp_case_service.case_dir(case_id)
        analysis_dir = case_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        pd_data = {
            "run_id": "RUN-TEST",
            "diagnostics_version": "2.0",
            "plugin_diagnostics": [
                {
                    "plugin_id": "crash_detection",
                    "plugin_version": "1.0.0",
                    "run_id": "RUN-TEST",
                    "executed": True,
                    "skipped": False,
                    "findings_emitted": 3,
                    "execution_status": "RAN",
                    "trust_state": "builtin_trusted",
                }
            ],
        }
        (analysis_dir / "plugin_diagnostics.json").write_text(
            json.dumps(pd_data), encoding="utf-8"
        )

        res = client.get(f"/api/cases/{case_id}/plugins")
        data = res.json()
        assert len(data["plugin_run_info"]) == 1
        assert data["plugin_run_info"][0]["plugin_id"] == "crash_detection"
        assert data["plugin_run_info"][0]["execution_status"] == "RAN"
        assert data["plugin_run_info"][0]["trust_state"] == "builtin_trusted"


# ---------------------------------------------------------------------------
# GET /api/cases/{id}/findings — shape verification
# ---------------------------------------------------------------------------

class TestFindingsShape:
    def test_findings_include_forensic_fields(
        self, client: TestClient, case_id: str, tmp_case_service: CaseService
    ):
        """Findings should include plugin_id, plugin_version, evidence_references."""
        case_dir = tmp_case_service.case_dir(case_id)
        analysis_dir = case_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        findings = {
            "findings_version": "2.0",
            "run_id": "RUN-TEST",
            "evidence_id": "EV-0001",
            "generated_at": "2026-01-01T00:00:00",
            "findings": [
                {
                    "finding_id": "FND-001",
                    "plugin_id": "crash_detection",
                    "plugin_version": "1.0.0",
                    "title": "Crash detected",
                    "severity": "critical",
                    "description": "Test crash",
                    "evidence_references": [
                        {
                            "evidence_id": "EV-0001",
                            "stream_name": "position",
                            "time_range_start": 5.0,
                            "time_range_end": 10.0,
                            "support_summary": "Rapid altitude loss",
                        }
                    ],
                }
            ],
        }
        (analysis_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")

        res = client.get(f"/api/cases/{case_id}/findings")
        data = res.json()
        assert data["ok"] is True
        assert data["count"] == 1
        f = data["findings"][0]
        assert f["plugin_id"] == "crash_detection"
        assert f["plugin_version"] == "1.0.0"
        assert len(f["evidence_references"]) == 1
        assert f["evidence_references"][0]["stream_name"] == "position"
