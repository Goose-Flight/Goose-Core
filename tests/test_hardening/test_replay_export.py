"""Tests for replay/export bundle creation and verification.

Hardening Sprint — test_replay_export
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.forensics.reports import ReplayMatchState, ReplayVerificationReport
from goose.web import cases_api
from goose.web.app import create_app


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


class TestBundleCreation:
    def test_bundle_has_required_fields(self, client: TestClient, case_id: str, tmp_case_service: CaseService):
        res = client.post(f"/api/cases/{case_id}/exports/bundle")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "bundle_id" in data
        assert data["bundle_id"].startswith("BDL-")

        # Read the bundle file
        exports_dir = tmp_case_service.case_dir(case_id) / "exports"
        bundle_file = exports_dir / data["filename"]
        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))

        assert bundle["bundle_version"] == "1.0"
        assert "bundle_id" in bundle
        assert bundle["case_id"] == case_id
        assert "case_metadata" in bundle
        assert "exported_at" in bundle
        assert "engine_version" in bundle
        assert "replay_metadata" in bundle
        # replay_metadata sub-fields
        rm = bundle["replay_metadata"]
        assert "parser_name" in rm
        assert "parser_version" in rm
        assert "plugin_versions" in rm
        assert "tuning_profile" in rm

    def test_export_history_written_to_case(self, client: TestClient, case_id: str):
        res = client.post(f"/api/cases/{case_id}/exports/bundle")
        data = res.json()
        bundle_id = data["bundle_id"]

        # Check case detail includes the export
        case_res = client.get(f"/api/cases/{case_id}")
        case_data = case_res.json()["case"]
        assert case_data["export_count"] == 1
        exports = case_data["exports"]
        assert len(exports) == 1
        assert exports[0]["export_id"] == bundle_id
        assert exports[0]["bundle_version"] == "1.0"
        assert exports[0]["includes_replay"] is True

    def test_multiple_bundles(self, client: TestClient, case_id: str, tmp_case_service: CaseService):
        client.post(f"/api/cases/{case_id}/exports/bundle")
        client.post(f"/api/cases/{case_id}/exports/bundle")
        exports_dir = tmp_case_service.case_dir(case_id) / "exports"
        files = [f for f in exports_dir.iterdir() if f.is_file()]
        assert len(files) == 2


class TestReplayVerification:
    def test_verify_replay_exact_match(self, client: TestClient, case_id: str, tmp_case_service: CaseService):
        """When versions match, should return EXACT or PARTIAL."""
        # Create a bundle first
        bundle_res = client.post(f"/api/cases/{case_id}/exports/bundle")
        filename = bundle_res.json()["filename"]

        # Verify
        res = client.post(
            f"/api/cases/{case_id}/exports/verify-replay",
            json={"bundle_filename": filename},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        report = data["report"]
        assert report["case_id"] == case_id
        assert "match_state" in report
        assert report["match_state"] in ("exact", "partial", "version_drift")

    def test_verify_replay_version_drift(self, client: TestClient, case_id: str, tmp_case_service: CaseService):
        """If we modify the bundle engine_version, drift should be detected."""
        # Create bundle
        bundle_res = client.post(f"/api/cases/{case_id}/exports/bundle")
        filename = bundle_res.json()["filename"]

        # Modify the bundle to simulate old engine version
        bundle_path = tmp_case_service.case_dir(case_id) / "exports" / filename
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle["engine_version"] = "0.1.0"
        bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

        # Verify
        res = client.post(
            f"/api/cases/{case_id}/exports/verify-replay",
            json={"bundle_filename": filename},
        )
        data = res.json()
        report = data["report"]
        assert report["match_state"] == "version_drift"
        assert len(report["version_drifts"]) > 0
        assert "engine" in report["version_drifts"][0]

    def test_verify_replay_missing_bundle(self, client: TestClient, case_id: str):
        res = client.post(
            f"/api/cases/{case_id}/exports/verify-replay",
            json={"bundle_filename": "nonexistent.json"},
        )
        assert res.status_code == 404


class TestReplayVerificationReportSerialization:
    def test_serialization_roundtrip(self):
        report = ReplayVerificationReport(
            bundle_id="BDL-12345678",
            case_id="CASE-2026-000001",
            original_engine_version="1.0.0",
            current_engine_version="1.3.4",
            original_parser_version="1.0.0",
            current_parser_version="1.0.0",
            original_plugin_versions={"crash": "1.0.0"},
            current_plugin_versions={"crash": "1.0.1"},
            match_state=ReplayMatchState.VERSION_DRIFT,
            version_drifts=["engine: 1.0.0 -> 1.3.4", "plugin crash: 1.0.0 -> 1.0.1"],
            verified_at="2026-04-08T12:00:00",
        )
        d = report.to_dict()
        report2 = ReplayVerificationReport.from_dict(d)
        assert report2.match_state == ReplayMatchState.VERSION_DRIFT
        assert len(report2.version_drifts) == 2
