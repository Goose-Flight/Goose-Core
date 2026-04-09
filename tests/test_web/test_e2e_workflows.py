"""Phase 3 — End-to-End Workflow and GUI Testing.

Tests Core as a product: every major user-facing workflow through the HTTP API.
Uses real fixture ULG files for analysis tests; synthetic bytes for CRUD-only tests.

Routes verified here:
  GET  /
  GET  /api/runs/recent
  GET  /api/plugins
  GET  /api/profiles
  GET  /api/profiles/{profile_id}
  GET  /api/features
  POST /api/quick-analysis
  POST /api/cases
  GET  /api/cases
  GET  /api/cases/{case_id}
  POST /api/cases/{case_id}/evidence
  GET  /api/cases/{case_id}/evidence
  POST /api/cases/{case_id}/analyze
  GET  /api/cases/{case_id}/runs
  GET  /api/cases/{case_id}/runs/{run_id}
  GET  /api/cases/{case_id}/findings
  GET  /api/cases/{case_id}/hypotheses
  GET  /api/cases/{case_id}/timeline
  GET  /api/cases/{case_id}/audit
  GET  /api/cases/{case_id}/charts/data
  GET  /api/cases/{case_id}/exports
  POST /api/cases/{case_id}/exports/bundle
  GET  /api/cases/{case_id}/exports/reports/mission-summary
  GET  /api/cases/{case_id}/exports/reports/anomaly
  GET  /api/cases/{case_id}/exports/reports/crash
  POST /api/analyze (deprecated → 410)
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.web.app import create_app
from goose.web import cases_api

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
FIXTURE_ULG = FIXTURE_DIR / "px4_vibration_crash.ulg"
NORMAL_ULG = FIXTURE_DIR / "px4_normal_flight.ulg"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_svc(tmp_path: Path) -> CaseService:
    return CaseService(base_dir=tmp_path / "cases")


@pytest.fixture
def client(tmp_svc: CaseService) -> TestClient:
    cases_api._set_service(tmp_svc)
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def fake_ulg() -> bytes:
    """Minimal valid-looking ULog header bytes — enough for evidence upload tests."""
    return b"ULog\x00" + b"\xff" * 256


@pytest.fixture
def analyzed_case(client: TestClient, tmp_svc: CaseService) -> tuple[str, str]:
    """Create a case, upload a real ULG, run analysis, return (case_id, run_id)."""
    # Create case
    res = client.post("/api/cases", json={"created_by": "e2e_test", "notes": "e2e golden path"})
    assert res.status_code == 201, f"Case creation failed: {res.text}"
    case_id = res.json()["case"]["case_id"]

    # Upload real evidence
    ulg_bytes = FIXTURE_ULG.read_bytes()
    res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("px4_vibration_crash.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
    )
    assert res.status_code == 201, f"Evidence upload failed: {res.text}"

    # Run analysis
    res = client.post(f"/api/cases/{case_id}/analyze")
    assert res.status_code == 200, f"Analysis failed: {res.text}"
    run_id = res.json()["run_id"]

    return case_id, run_id


# ===========================================================================
# Class 1: TestWelcomeAndHealth
# ===========================================================================

class TestWelcomeAndHealth:
    """Basic health endpoints — confirm the app is wired up correctly."""

    def test_root_returns_html(self, client: TestClient):
        """GET / → 200 and HTML content-type (or 404 if index.html missing in test env)."""
        res = client.get("/")
        # In test environments without static/ the handler returns 404.
        assert res.status_code in (200, 404)
        if res.status_code == 200:
            ct = res.headers.get("content-type", "")
            assert "html" in ct

    def test_recent_runs_empty_state(self, client: TestClient):
        """GET /api/runs/recent → 200 with empty runs list when no cases exist."""
        res = client.get("/api/runs/recent")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "runs" in data
        assert "count" in data
        assert isinstance(data["runs"], list)

    def test_plugins_returns_list(self, client: TestClient):
        """GET /api/plugins → 200 with plugin list."""
        res = client.get("/api/plugins")
        assert res.status_code == 200
        data = res.json()
        assert "plugins" in data
        assert "count" in data
        assert data["count"] >= 11  # at least 11 plugins expected
        p = data["plugins"][0]
        assert "name" in p
        assert "version" in p

    def test_plugins_returns_17(self, client: TestClient):
        """Confirm plugin count is exactly 17 per sprint spec."""
        res = client.get("/api/plugins")
        data = res.json()
        assert data["count"] == 17

    def test_profiles_returns_list(self, client: TestClient):
        """GET /api/profiles → 200 with profiles dict."""
        res = client.get("/api/profiles")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "profiles" in data
        assert isinstance(data["profiles"], dict)
        assert data["count"] >= 1
        # Default profile must always be present
        assert "default" in data["profiles"]

    def test_profiles_default_shape(self, client: TestClient):
        """Each profile object has expected fields."""
        res = client.get("/api/profiles")
        data = res.json()
        for pid, cfg in data["profiles"].items():
            assert "profile_id" in cfg, f"profile_id missing for {pid}"
            assert "name" in cfg, f"name missing for {pid}"

    def test_get_single_profile(self, client: TestClient):
        """GET /api/profiles/default → 200 with single profile."""
        res = client.get("/api/profiles/default")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "profile" in data
        assert data["profile"]["profile_id"] == "default"

    def test_get_unknown_profile_fallback(self, client: TestClient):
        """GET /api/profiles/nonexistent → 200 with fallback to default."""
        res = client.get("/api/profiles/nonexistent_profile_xyz")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data.get("fallback") is True

    def test_features_endpoint(self, client: TestClient):
        """GET /api/features → 200 with feature gate state."""
        res = client.get("/api/features")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True


# ===========================================================================
# Class 2: TestQuickAnalysisFlow
# ===========================================================================

class TestQuickAnalysisFlow:
    """Quick Analysis session-only triage flow (no persistent case created)."""

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_quick_analysis_with_real_ulg(self, client: TestClient):
        """POST /api/quick-analysis with real ULG → 200, full response."""
        ulg_bytes = FIXTURE_ULG.read_bytes()
        res = client.post(
            "/api/quick-analysis",
            files={"file": ("px4_vibration_crash.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
        )
        assert res.status_code == 200, f"Quick analysis failed: {res.text[:500]}"
        data = res.json()
        assert data["ok"] is True
        assert "quick_analysis_id" in data
        assert data["quick_analysis_id"].startswith("QA-")
        assert "findings" in data
        assert isinstance(data["findings"], list)
        assert "overall_score" in data
        assert isinstance(data["overall_score"], int)
        assert "summary" in data
        assert "persisted" in data
        assert data["persisted"] is False  # session-only, never persisted

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_quick_analysis_findings_shape(self, client: TestClient):
        """Each finding from quick-analysis has required forensic fields."""
        ulg_bytes = FIXTURE_ULG.read_bytes()
        res = client.post(
            "/api/quick-analysis",
            files={"file": ("px4_vibration_crash.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
        )
        assert res.status_code == 200
        data = res.json()
        if data["findings"]:
            f = data["findings"][0]
            assert "title" in f
            assert "severity" in f
            assert "description" in f

    def test_quick_analysis_empty_file_rejected(self, client: TestClient):
        """POST /api/quick-analysis with empty file → 400."""
        res = client.post(
            "/api/quick-analysis",
            files={"file": ("empty.ulg", io.BytesIO(b""), "application/octet-stream")},
        )
        assert res.status_code == 400

    def test_quick_analysis_txt_file_rejected(self, client: TestClient):
        """POST /api/quick-analysis with .txt file → 422 (parse error)."""
        res = client.post(
            "/api/quick-analysis",
            files={"file": ("not_a_log.txt", io.BytesIO(b"this is not a flight log"), "text/plain")},
        )
        assert res.status_code in (400, 422)

    def test_quick_analysis_no_file_rejected(self, client: TestClient):
        """POST /api/quick-analysis with no file → 400 or 422."""
        res = client.post("/api/quick-analysis")
        assert res.status_code in (400, 422)


# ===========================================================================
# Class 3: TestInvestigationCaseFlow — THE GOLDEN PATH
# ===========================================================================

class TestInvestigationCaseFlow:
    """Full investigation case lifecycle from creation to analysis to findings retrieval."""

    def test_step1_create_case_201(self, client: TestClient):
        """POST /api/cases → 201, returns case_id."""
        res = client.post("/api/cases", json={"created_by": "e2e_test"})
        assert res.status_code == 201
        data = res.json()
        assert data["ok"] is True
        assert "case" in data
        assert data["case"]["case_id"].startswith("CASE-")

    def test_step2_get_case_200(self, client: TestClient):
        """GET /api/cases/{case_id} → 200, returns case object."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["case"]["case_id"] == case_id
        assert "status" in data["case"]
        assert "evidence_items" in data["case"]
        assert "analysis_runs" in data["case"]

    def test_step3_upload_evidence_201(self, client: TestClient, fake_ulg: bytes):
        """POST /api/cases/{case_id}/evidence → 201, evidence item returned."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("flight.ulg", io.BytesIO(fake_ulg), "application/octet-stream")},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["ok"] is True
        ev = data["evidence"]
        assert ev["evidence_id"].startswith("EV-")
        assert ev["filename"] == "flight.ulg"
        assert ev["immutable"] is True
        assert len(ev["sha256"]) == 64

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_step4_analyze_returns_200(self, client: TestClient):
        """POST /api/cases/{case_id}/analyze → 200 with run_id."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        ulg_bytes = FIXTURE_ULG.read_bytes()
        client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("px4_vibration_crash.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
        )
        res = client.post(f"/api/cases/{case_id}/analyze")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "run_id" in data
        assert data["run_id"].startswith("RUN-")

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_step4_analyze_response_fields(self, client: TestClient):
        """Analysis response includes core fields."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        ulg_bytes = FIXTURE_ULG.read_bytes()
        client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("px4_vibration_crash.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
        )
        res = client.post(f"/api/cases/{case_id}/analyze")
        data = res.json()
        for field in ("ok", "run_id", "case_id", "overall_score", "findings", "hypotheses", "summary", "metadata"):
            assert field in data, f"Missing field: {field}"

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_step5_list_runs(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/runs → 200, at least 1 run."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/runs")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] >= 1
        assert isinstance(data["runs"], list)
        run = data["runs"][0]
        assert "run_id" in run
        assert "status" in run
        assert "started_at" in run

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_step6_get_findings(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/findings → 200, findings list."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/findings")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "findings" in data
        assert isinstance(data["findings"], list)
        assert "count" in data

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_step6_findings_have_forensic_fields(self, analyzed_case: tuple[str, str], client: TestClient):
        """Findings from analysis have plugin_id and severity."""
        case_id, _ = analyzed_case
        data = client.get(f"/api/cases/{case_id}/findings").json()
        if data["findings"]:
            f = data["findings"][0]
            assert "title" in f
            assert "severity" in f
            assert "plugin_id" in f

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_step7_get_hypotheses(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/hypotheses → 200, hypotheses list."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/hypotheses")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "hypotheses" in data
        assert isinstance(data["hypotheses"], list)
        assert "count" in data

    def test_step8_get_timeline_empty(self, client: TestClient):
        """GET /api/cases/{case_id}/timeline → 200, even before analysis."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/timeline")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "events" in data
        assert isinstance(data["events"], list)
        # Verify structured schema v2.0
        assert "timeline_version" in data
        assert data["timeline_version"].startswith("2.0")

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_step8_timeline_after_analysis(self, analyzed_case: tuple[str, str], client: TestClient):
        """Timeline has events after analysis."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/timeline")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        # Timeline may or may not have events depending on findings
        assert "events" in data
        assert "count" in data

    def test_step9_audit_log(self, client: TestClient, fake_ulg: bytes):
        """GET /api/cases/{case_id}/audit → 200, audit entries include case_created."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/audit")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] >= 1
        actions = [e["action"] for e in data["audit"]]
        assert "case_created" in actions

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_audit_grows_after_analysis(self, client: TestClient):
        """Audit log has more entries after analysis than after creation."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        count_before = client.get(f"/api/cases/{case_id}/audit").json()["count"]

        ulg_bytes = FIXTURE_ULG.read_bytes()
        client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("px4_vibration_crash.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
        )
        client.post(f"/api/cases/{case_id}/analyze")

        count_after = client.get(f"/api/cases/{case_id}/audit").json()["count"]
        assert count_after > count_before


# ===========================================================================
# Class 4: TestChartEndpoints
# ===========================================================================

class TestChartEndpoints:
    """Chart time-series data endpoints."""

    def test_charts_data_empty_case(self, client: TestClient):
        """GET /api/cases/{case_id}/charts/data → 200, empty streams without evidence."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/charts/data")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "streams" in data
        assert isinstance(data["streams"], dict)
        assert "available_streams" in data
        assert isinstance(data["available_streams"], list)

    def test_charts_data_available_streams_list(self, client: TestClient):
        """Available streams list is non-empty."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        data = client.get(f"/api/cases/{case_id}/charts/data").json()
        assert len(data["available_streams"]) >= 8

    def test_charts_data_404_nonexistent_case(self, client: TestClient):
        """GET /api/cases/nonexistent/charts/data → 404."""
        res = client.get("/api/cases/CASE-0000-000000/charts/data")
        assert res.status_code == 404

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_charts_data_with_evidence(self, analyzed_case: tuple[str, str], client: TestClient):
        """After analysis, requesting known streams returns data."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/charts/data?streams=altitude_m,battery_voltage")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        # Streams may or may not be present depending on fixture content
        assert isinstance(data["streams"], dict)


# ===========================================================================
# Class 5: TestExportFlow
# ===========================================================================

class TestExportFlow:
    """Export bundle creation and listing."""

    def test_list_exports_empty(self, client: TestClient):
        """GET /api/cases/{case_id}/exports → 200, empty list initially."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/exports")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["exports"] == []
        assert data["count"] == 0

    def test_create_bundle(self, client: TestClient):
        """POST /api/cases/{case_id}/exports/bundle → 200, bundle created."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.post(f"/api/cases/{case_id}/exports/bundle")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "bundle_id" in data
        assert data["bundle_id"].startswith("BDL-")
        assert "filename" in data
        assert data["filename"].startswith("bundle_")
        assert data["size_bytes"] > 0

    def test_bundle_appears_in_list(self, client: TestClient):
        """Created bundle shows in exports list."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        client.post(f"/api/cases/{case_id}/exports/bundle")
        res = client.get(f"/api/cases/{case_id}/exports")
        data = res.json()
        assert data["count"] == 1
        assert data["exports"][0]["filename"].startswith("bundle_")

    def test_exports_404_nonexistent_case(self, client: TestClient):
        """GET /api/cases/nonexistent/exports → 404."""
        res = client.get("/api/cases/CASE-0000-000000/exports")
        assert res.status_code == 404

    def test_bundle_404_nonexistent_case(self, client: TestClient):
        """POST /api/cases/nonexistent/exports/bundle → 404."""
        res = client.post("/api/cases/CASE-0000-000000/exports/bundle")
        assert res.status_code == 404

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_mission_summary_report(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/exports/reports/mission-summary → 200."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/exports/reports/mission-summary")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "report" in data

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_anomaly_report(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/exports/reports/anomaly → 200."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/exports/reports/anomaly")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "report" in data

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_crash_report(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/exports/reports/crash → 200."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/exports/reports/crash")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "report" in data


# ===========================================================================
# Class 6: TestErrorAndEmptyStates
# ===========================================================================

class TestErrorAndEmptyStates:
    """Error handling and empty/missing resource states."""

    def test_get_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent-id → 404."""
        res = client.get("/api/cases/CASE-9999-999999")
        assert res.status_code == 404

    def test_get_runs_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent/runs → 404."""
        res = client.get("/api/cases/CASE-9999-999999/runs")
        assert res.status_code == 404

    def test_get_findings_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent/findings → 404."""
        res = client.get("/api/cases/CASE-9999-999999/findings")
        assert res.status_code == 404

    def test_get_hypotheses_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent/hypotheses → 404."""
        res = client.get("/api/cases/CASE-9999-999999/hypotheses")
        assert res.status_code == 404

    def test_get_audit_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent/audit → 404."""
        res = client.get("/api/cases/CASE-9999-999999/audit")
        assert res.status_code == 404

    def test_get_timeline_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent/timeline → 404."""
        res = client.get("/api/cases/CASE-9999-999999/timeline")
        assert res.status_code == 404

    def test_get_charts_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent/charts/data → 404."""
        res = client.get("/api/cases/CASE-9999-999999/charts/data")
        assert res.status_code == 404

    def test_analyze_without_evidence_422(self, client: TestClient):
        """POST /api/cases/{case_id}/analyze with no evidence → 422."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.post(f"/api/cases/{case_id}/analyze")
        assert res.status_code == 422

    def test_recent_runs_empty_when_no_cases(self, client: TestClient):
        """GET /api/runs/recent → 200, empty list, when no cases exist."""
        res = client.get("/api/runs/recent")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["runs"] == []
        assert data["count"] == 0

    def test_deprecated_analyze_endpoint_returns_410(self, client: TestClient):
        """POST /api/analyze → 410 Gone (deprecated endpoint)."""
        res = client.post(
            "/api/analyze",
            files={"file": ("flight.ulg", io.BytesIO(b"fake_ulg_data"), "application/octet-stream")},
        )
        assert res.status_code == 410

    def test_deprecated_analyze_returns_gone_error(self, client: TestClient):
        """POST /api/analyze returns error=gone JSON body."""
        res = client.post(
            "/api/analyze",
            files={"file": ("x.ulg", io.BytesIO(b"x"), "application/octet-stream")},
        )
        data = res.json()
        assert data["error"] == "gone"
        assert "alternatives" in data

    def test_evidence_upload_to_nonexistent_case_404(self, client: TestClient, fake_ulg: bytes):
        """POST /api/cases/nonexistent/evidence → 404."""
        res = client.post(
            "/api/cases/CASE-9999-999999/evidence",
            files={"file": ("flight.ulg", io.BytesIO(fake_ulg), "application/octet-stream")},
        )
        assert res.status_code == 404

    def test_runs_empty_before_analysis(self, client: TestClient):
        """GET /api/cases/{case_id}/runs → count = 0 before any analysis."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/runs")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 0
        assert data["runs"] == []

    def test_findings_empty_before_analysis(self, client: TestClient):
        """GET /api/cases/{case_id}/findings → count = 0 before analysis."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/findings")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["findings"] == []
        assert data["count"] == 0

    def test_hypotheses_empty_before_analysis(self, client: TestClient):
        """GET /api/cases/{case_id}/hypotheses → count = 0 before analysis."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        res = client.get(f"/api/cases/{case_id}/hypotheses")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["hypotheses"] == []
        assert data["count"] == 0


# ===========================================================================
# Class 7: TestOpenRecentFlow
# ===========================================================================

class TestOpenRecentFlow:
    """Open Recent UX flow — /api/runs/recent returns sorted run list."""

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_recent_runs_after_analysis(self, client: TestClient):
        """After analysis /api/runs/recent shows the run."""
        case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
        ulg_bytes = FIXTURE_ULG.read_bytes()
        client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("px4_vibration_crash.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
        )
        client.post(f"/api/cases/{case_id}/analyze")

        res = client.get("/api/runs/recent")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] >= 1
        run = data["runs"][0]
        # Required fields for "Open Recent" UX
        for field in ("case_id", "run_id", "profile", "started_at", "findings_count"):
            assert field in run, f"Missing field in recent run: {field}"

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_recent_runs_sorted_most_recent_first(self, client: TestClient):
        """Recent runs are sorted by started_at descending."""
        ulg_bytes = FIXTURE_ULG.read_bytes()

        run_ids = []
        for i in range(2):
            case_id = client.post("/api/cases", json={}).json()["case"]["case_id"]
            client.post(
                f"/api/cases/{case_id}/evidence",
                files={"file": (f"flight{i}.ulg", io.BytesIO(ulg_bytes), "application/octet-stream")},
            )
            res = client.post(f"/api/cases/{case_id}/analyze")
            run_ids.append(res.json()["run_id"])

        recent = client.get("/api/runs/recent").json()["runs"]
        # The second (most recent) run should be first
        assert len(recent) >= 2
        times = [r["started_at"] for r in recent]
        assert times == sorted(times, reverse=True), "Runs are not sorted most-recent-first"

    def test_recent_runs_respects_limit(self, client: TestClient):
        """GET /api/runs/recent?limit=5 → at most 5 results."""
        res = client.get("/api/runs/recent?limit=5")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] <= 5
        assert len(data["runs"]) <= 5


# ===========================================================================
# Class 8: TestRunDetailEndpoints
# ===========================================================================

class TestRunDetailEndpoints:
    """Run-level detail endpoints."""

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_get_run_detail(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/runs/{run_id} → 200 with run detail."""
        case_id, run_id = analyzed_case
        res = client.get(f"/api/cases/{case_id}/runs/{run_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "run" in data
        run = data["run"]
        assert run["run_id"] == run_id
        assert "status" in run
        assert "started_at" in run

    @pytest.mark.skipif(not FIXTURE_ULG.exists(), reason="px4_vibration_crash.ulg fixture missing")
    def test_get_nonexistent_run_404(self, analyzed_case: tuple[str, str], client: TestClient):
        """GET /api/cases/{case_id}/runs/RUN-NONEXISTENT → 404."""
        case_id, _ = analyzed_case
        res = client.get(f"/api/cases/{case_id}/runs/RUN-DOESNOTEXIST")
        assert res.status_code == 404

    def test_get_run_nonexistent_case_404(self, client: TestClient):
        """GET /api/cases/nonexistent/runs/RUN-X → 404."""
        res = client.get("/api/cases/CASE-9999-999999/runs/RUN-X")
        assert res.status_code == 404
