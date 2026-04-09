"""Regression suite for API modularization.

Verifies all existing routes still return expected status codes and structure
after refactoring into route sub-modules.

Hardening Sprint — test_api_modularization
"""

from __future__ import annotations

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


class TestCasesCRUD:
    def test_create_case(self, client: TestClient):
        res = client.post("/api/cases", json={"created_by": "test", "tags": ["t1"]})
        assert res.status_code == 201
        data = res.json()
        assert data["ok"] is True
        assert data["case"]["case_id"].startswith("CASE-")

    def test_list_cases(self, client: TestClient, case_id: str):
        res = client.get("/api/cases")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] >= 1

    def test_get_case(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["case"]["case_id"] == case_id

    def test_get_case_404(self, client: TestClient):
        res = client.get("/api/cases/CASE-9999-999999")
        assert res.status_code == 404

    def test_update_status(self, client: TestClient, case_id: str):
        res = client.patch(
            f"/api/cases/{case_id}/status",
            json={"status": "review", "actor": "test"},
        )
        assert res.status_code == 200
        assert res.json()["case"]["status"] == "review"


class TestEvidenceRoutes:
    def test_list_evidence_empty(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/evidence")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] == 0

    def test_ingest_evidence(self, client: TestClient, case_id: str):
        res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("test.ulg", b"ULog\x00" + b"\xff" * 256, "application/octet-stream")},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["ok"] is True
        assert data["evidence"]["evidence_id"] == "EV-0001"


class TestAnalysisRoutes:
    def test_findings_no_analysis(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/findings")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["findings"] == []

    def test_hypotheses_no_analysis(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/hypotheses")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["hypotheses"] == []

    def test_diagnostics_no_analysis(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/diagnostics")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["diagnostics"] is None

    def test_audit_log(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/audit")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] >= 1  # case_created audit entry

    def test_plugins_route(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/plugins")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] == 12
        # New trust fields
        assert "policy_mode" in data
        m = data["manifests"][0]
        assert "computed_fingerprint" in m
        assert "trust_verified" in m


class TestTimelineRoute:
    def test_timeline_no_analysis(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/timeline")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] == 0


class TestChartsRoute:
    def test_charts_data_no_analysis(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/charts/data?streams=battery_voltage")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "available_streams" in data


class TestExportsRoute:
    def test_exports_empty(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/exports")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] == 0

    def test_create_bundle(self, client: TestClient, case_id: str):
        res = client.post(f"/api/cases/{case_id}/exports/bundle")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "bundle_id" in data
        assert "filename" in data


class TestRunsRoute:
    def test_list_runs_empty(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/runs")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["runs"] == []

    def test_get_run_404(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/runs/RUN-NONEXIST")
        assert res.status_code == 404


class TestReportsRoute:
    def test_mission_summary(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/exports/reports/mission-summary")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        report = data["report"]
        assert report["case_id"] == case_id
        assert "total_findings" in report

    def test_anomaly_report(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/exports/reports/anomaly")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        report = data["report"]
        assert report["case_id"] == case_id
        assert "findings" in report

    def test_crash_report(self, client: TestClient, case_id: str):
        res = client.get(f"/api/cases/{case_id}/exports/reports/crash")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        report = data["report"]
        assert report["case_id"] == case_id
        assert "crash_detected" in report
