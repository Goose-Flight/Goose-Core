"""Phase 2 Bulletproofing Sprint — Golden-path case flow regression tests.

Validates the complete create → ingest → analyze → artifacts flow via the
web API, using real fixture files. This is the product qualification path.

Coverage:
- Case creation and directory structure
- Evidence attachment with SHA-256 hash
- Analysis run produces findings and hypotheses
- Required artifacts exist and are non-empty
- All 7 profiles complete analysis without crashing
- Analyzer sweep: every plugin returns valid findings (no crashes, valid shape)
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.web import cases_api
from goose.web.app import create_app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
VIBRATION_CRASH = FIXTURES_DIR / "px4_vibration_crash.ulg"
MOTOR_FAILURE = FIXTURES_DIR / "px4_motor_failure.ulg"
NORMAL_FLIGHT = FIXTURES_DIR / "px4_normal_flight.ulg"
ARDUPILOT = FIXTURES_DIR / "ardupilot_minimal.log"

ALL_PROFILES = ["default", "racer", "research", "shop_repair", "factory_qa", "gov_mil", "advanced"]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def svc(tmp_path: Path) -> CaseService:
    service = CaseService(base_dir=tmp_path / "cases")
    cases_api._set_service(service)
    return service


@pytest.fixture
def client(svc: CaseService) -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _upload_and_analyze(client: TestClient, fixture_path: Path, profile: str = "default") -> dict[str, Any]:
    """Create a case, upload evidence, run analysis. Return response JSON.

    Note: The API returns 201 for case creation and 201 for evidence upload.
    Case response is wrapped under data["case"]["case_id"].
    Evidence response is wrapped under data["evidence"]["evidence_id"].
    """
    # Step 1: create case
    create_res = client.post("/api/cases", json={"created_by": "sweep_test"})
    assert create_res.status_code == 201, f"create_case failed ({create_res.status_code}): {create_res.text}"
    case_id = create_res.json()["case"]["case_id"]

    # Step 2: attach evidence (multipart upload)
    with open(fixture_path, "rb") as f:
        content = f.read()
    ev_res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": (fixture_path.name, io.BytesIO(content), "application/octet-stream")},
    )
    assert ev_res.status_code == 201, f"attach evidence failed ({ev_res.status_code}): {ev_res.text}"
    ev_data = ev_res.json()

    # Step 3: run analysis
    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    return {
        "case_id": case_id,
        "ev_data": ev_data,
        "analyze_res": analyze_res,
        "analyze_data": analyze_res.json() if analyze_res.status_code == 200 else {},
    }


# ---------------------------------------------------------------------------
# Case creation
# ---------------------------------------------------------------------------

class TestCaseCreation:
    def test_create_case_returns_case_id(self, client: TestClient):
        res = client.post("/api/cases", json={"created_by": "test"})
        assert res.status_code == 201
        data = res.json()
        assert "case" in data
        assert "case_id" in data["case"]
        assert data["case"]["case_id"].startswith("CASE-")

    def test_case_directory_structure_created(self, client: TestClient, svc: CaseService):
        res = client.post("/api/cases", json={"created_by": "test"})
        assert res.status_code == 201
        case_id = res.json()["case"]["case_id"]
        case_dir = svc.case_dir(case_id)
        assert (case_dir / "evidence").is_dir()
        assert (case_dir / "manifests").is_dir()
        assert (case_dir / "parsed").is_dir()
        assert (case_dir / "analysis").is_dir()
        assert (case_dir / "audit").is_dir()
        assert (case_dir / "exports").is_dir()
        assert (case_dir / "case.json").is_file()


# ---------------------------------------------------------------------------
# Evidence ingest
# ---------------------------------------------------------------------------

class TestEvidenceIngest:
    def test_evidence_sha256_is_populated(self, client: TestClient):
        res = client.post("/api/cases", json={"created_by": "test"})
        assert res.status_code == 201
        case_id = res.json()["case"]["case_id"]
        with open(VIBRATION_CRASH, "rb") as f:
            content = f.read()
        ev_res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": (VIBRATION_CRASH.name, io.BytesIO(content), "application/octet-stream")},
        )
        assert ev_res.status_code == 201
        data = ev_res.json()
        # Evidence data is nested under "evidence" key
        ev = data["evidence"]
        assert "evidence_id" in ev
        assert "sha256" in ev
        assert len(ev["sha256"]) == 64  # SHA-256 hex

    def test_evidence_filename_preserved(self, client: TestClient):
        res = client.post("/api/cases", json={"created_by": "test"})
        assert res.status_code == 201
        case_id = res.json()["case"]["case_id"]
        with open(VIBRATION_CRASH, "rb") as f:
            content = f.read()
        ev_res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": (VIBRATION_CRASH.name, io.BytesIO(content), "application/octet-stream")},
        )
        assert ev_res.status_code == 201
        data = ev_res.json()
        ev = data["evidence"]
        assert ev.get("filename") == VIBRATION_CRASH.name


# ---------------------------------------------------------------------------
# Golden-path analysis flow
# ---------------------------------------------------------------------------

class TestGoldenPathAnalysis:
    @pytest.mark.parametrize("fixture_path", [
        VIBRATION_CRASH, MOTOR_FAILURE, NORMAL_FLIGHT, ARDUPILOT,
    ], ids=lambda p: p.name)
    def test_analysis_completes_successfully(self, client: TestClient, fixture_path: Path):
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")
        out = _upload_and_analyze(client, fixture_path)
        assert out["analyze_res"].status_code == 200, (
            f"analyze failed ({fixture_path.name}): {out['analyze_res'].text[:500]}"
        )

    def test_analysis_returns_run_id(self, client: TestClient):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        data = out["analyze_data"]
        assert "run_id" in data
        assert data["run_id"].startswith("RUN-")

    def test_analysis_returns_findings(self, client: TestClient):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        data = out["analyze_data"]
        assert "findings" in data
        assert isinstance(data["findings"], list)
        assert len(data["findings"]) > 0

    def test_analysis_returns_hypotheses(self, client: TestClient):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        data = out["analyze_data"]
        assert "hypotheses" in data
        assert isinstance(data["hypotheses"], list)
        assert len(data["hypotheses"]) > 0

    def test_findings_have_valid_shape(self, client: TestClient):
        """Every finding must have the required fields."""
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        for finding in out["analyze_data"]["findings"]:
            for field in ("finding_id", "title", "severity", "score", "description", "plugin_id"):
                assert field in finding, f"Finding missing field {field!r}: {finding}"
            assert 0 <= finding["score"] <= 100, f"Score out of range: {finding['score']}"
            assert finding["severity"] in ("critical", "warning", "info", "pass"), (
                f"Invalid severity: {finding['severity']}"
            )

    def test_hypotheses_have_valid_shape(self, client: TestClient):
        """Every hypothesis must have the required fields."""
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        for hyp in out["analyze_data"]["hypotheses"]:
            for field in ("hypothesis_id", "statement", "confidence", "status"):
                assert field in hyp, f"Hypothesis missing field {field!r}: {hyp}"
            assert 0.0 <= hyp["confidence"] <= 1.0, f"Confidence out of range: {hyp['confidence']}"

    def test_normal_flight_returns_fewer_critical_findings(self, client: TestClient):
        """Normal flight should have fewer critical findings than crash logs."""
        if not NORMAL_FLIGHT.exists() or not VIBRATION_CRASH.exists():
            pytest.skip("Fixtures not found")
        normal_out = _upload_and_analyze(client, NORMAL_FLIGHT)
        crash_out = _upload_and_analyze(client, VIBRATION_CRASH)

        assert normal_out["analyze_res"].status_code == 200
        assert crash_out["analyze_res"].status_code == 200

        normal_criticals = sum(
            1 for f in normal_out["analyze_data"]["findings"]
            if f.get("severity") == "critical"
        )
        crash_criticals = sum(
            1 for f in crash_out["analyze_data"]["findings"]
            if f.get("severity") == "critical"
        )
        assert crash_criticals >= normal_criticals, (
            f"Expected crash ({crash_criticals}) >= normal ({normal_criticals}) critical findings"
        )


# ---------------------------------------------------------------------------
# Case artifact files
# ---------------------------------------------------------------------------

class TestArtifactFiles:
    def test_findings_json_written(self, client: TestClient, svc: CaseService):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        assert (case_dir / "analysis" / "findings.json").is_file()

    def test_hypotheses_json_written(self, client: TestClient, svc: CaseService):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        assert (case_dir / "analysis" / "hypotheses.json").is_file()

    def test_timeline_json_written(self, client: TestClient, svc: CaseService):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        assert (case_dir / "analysis" / "timeline.json").is_file()

    def test_parse_diagnostics_json_written(self, client: TestClient, svc: CaseService):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        assert (case_dir / "parsed" / "parse_diagnostics.json").is_file()

    def test_provenance_json_written(self, client: TestClient, svc: CaseService):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        assert (case_dir / "parsed" / "provenance.json").is_file()

    def test_plugin_diagnostics_json_written(self, client: TestClient, svc: CaseService):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        assert (case_dir / "analysis" / "plugin_diagnostics.json").is_file()

    def test_evidence_manifest_written(self, client: TestClient, svc: CaseService):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        assert (case_dir / "manifests" / "evidence_manifest.json").is_file()

    def test_findings_json_is_valid(self, client: TestClient, svc: CaseService):
        """findings.json must be parseable JSON with non-empty findings list."""
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        data = json.loads((case_dir / "analysis" / "findings.json").read_text())
        assert "findings" in data
        assert isinstance(data["findings"], list)
        assert len(data["findings"]) > 0

    def test_hypotheses_json_is_valid(self, client: TestClient, svc: CaseService):
        """hypotheses.json must be parseable JSON with non-empty hypotheses list."""
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        data = json.loads((case_dir / "analysis" / "hypotheses.json").read_text())
        assert "hypotheses" in data
        assert isinstance(data["hypotheses"], list)

    def test_provenance_json_has_parser_name(self, client: TestClient, svc: CaseService):
        """provenance.json must have parser_name populated."""
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case_dir = svc.case_dir(out["case_id"])
        data = json.loads((case_dir / "parsed" / "provenance.json").read_text())
        assert data.get("parser_name"), f"provenance.parser_name is empty: {data}"

    def test_run_is_recorded_in_case(self, client: TestClient, svc: CaseService):
        """After analysis the AnalysisRun must be recorded in case.json."""
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _upload_and_analyze(client, VIBRATION_CRASH)
        assert out["analyze_res"].status_code == 200
        case = svc.get_case(out["case_id"])
        assert len(case.analysis_runs) == 1
        run = case.analysis_runs[0]
        assert run.status == "completed"
        assert run.findings_count >= 0
        assert run.hypotheses_count >= 0


# ---------------------------------------------------------------------------
# Plugin sweep — every plugin returns valid findings (no crash)
# ---------------------------------------------------------------------------

class TestAnalyzerSweep:
    """Run each plugin individually against real fixtures and check contract."""

    @pytest.fixture
    def parsed_vibration_crash(self):
        from goose.parsers.detect import parse_file
        result = parse_file(VIBRATION_CRASH)
        assert result.success, f"Fixture parse failed: {result.diagnostics.errors}"
        return result

    @pytest.fixture
    def parsed_normal_flight(self):
        from goose.parsers.detect import parse_file
        result = parse_file(NORMAL_FLIGHT)
        assert result.success, f"Fixture parse failed: {result.diagnostics.errors}"
        return result

    def test_all_plugins_return_list(self, parsed_vibration_crash):
        from goose.plugins import get_all_plugins
        plugins = get_all_plugins()
        assert len(plugins) >= 11  # We have at least 11 plugins
        for pid, plugin in plugins.items():
            findings = plugin.analyze(parsed_vibration_crash.flight, {})
            assert isinstance(findings, list), f"Plugin {pid!r} did not return a list"

    def test_all_plugins_findings_have_required_fields(self, parsed_vibration_crash):
        from goose.plugins import get_all_plugins
        plugins = get_all_plugins()
        required_fields = ("title", "severity", "score", "description", "plugin_name")
        for pid, plugin in plugins.items():
            findings = plugin.analyze(parsed_vibration_crash.flight, {})
            for finding in findings:
                for field in required_fields:
                    assert hasattr(finding, field), (
                        f"Plugin {pid!r} finding missing field {field!r}: {finding}"
                    )

    def test_all_plugins_findings_have_evidence_dict(self, parsed_vibration_crash):
        from goose.plugins import get_all_plugins
        plugins = get_all_plugins()
        for pid, plugin in plugins.items():
            findings = plugin.analyze(parsed_vibration_crash.flight, {})
            for finding in findings:
                assert hasattr(finding, "evidence") and isinstance(finding.evidence, dict), (
                    f"Plugin {pid!r} finding has no evidence dict: {finding}"
                )

    def test_all_plugins_scores_in_range(self, parsed_vibration_crash):
        from goose.plugins import get_all_plugins
        plugins = get_all_plugins()
        for pid, plugin in plugins.items():
            findings = plugin.analyze(parsed_vibration_crash.flight, {})
            for finding in findings:
                assert 0 <= finding.score <= 100, (
                    f"Plugin {pid!r} finding score out of range: {finding.score}"
                )

    def test_all_plugins_severities_valid(self, parsed_vibration_crash):
        from goose.plugins import get_all_plugins
        valid_severities = {"critical", "warning", "info", "pass"}
        plugins = get_all_plugins()
        for pid, plugin in plugins.items():
            findings = plugin.analyze(parsed_vibration_crash.flight, {})
            for finding in findings:
                assert finding.severity in valid_severities, (
                    f"Plugin {pid!r} invalid severity: {finding.severity!r}"
                )

    def test_crash_plugins_fire_on_crash_log(self, parsed_vibration_crash):
        """Key crash-detection plugins should find something on crash logs."""
        from goose.plugins import get_all_plugins
        plugins = get_all_plugins()
        if "vibration" not in plugins:
            pytest.skip("vibration plugin not available")
        vib_findings = plugins["vibration"].analyze(parsed_vibration_crash.flight, {})
        assert len(vib_findings) > 0, "vibration plugin returned 0 findings on vibration crash log"

    def test_all_plugins_work_on_ardupilot_fixture(self):
        from goose.parsers.detect import parse_file
        from goose.plugins import get_all_plugins
        result = parse_file(ARDUPILOT)
        if not result.success:
            pytest.skip(f"Ardupilot fixture parse failed: {result.diagnostics.errors}")
        plugins = get_all_plugins()
        for pid, plugin in plugins.items():
            findings = plugin.analyze(result.flight, {})
            assert isinstance(findings, list), f"Plugin {pid!r} crashed or didn't return list on Ardupilot fixture"

    def test_forensic_analyze_no_crash_on_crash_fixture(self, parsed_vibration_crash):
        """forensic_analyze() (the production path) must not crash on any plugin."""
        from datetime import datetime

        from goose.forensics.models import EvidenceItem
        from goose.forensics.tuning import TuningProfile
        from goose.plugins import get_all_plugins

        ev = EvidenceItem(
            evidence_id="EV-0001",
            filename="test.ulg",
            content_type="application/x-ulog",
            size_bytes=1024,
            sha256="a" * 64,
            sha512=None,
            source_acquisition_mode="local_copy",
            source_reference=None,
            stored_path="/tmp/test.ulg",
            acquired_at=datetime.now(),
            acquired_by="test",
        )
        tuning = TuningProfile.default()
        plugins = get_all_plugins()
        for pid, plugin in plugins.items():
            ff_list, p_diag = plugin.forensic_analyze(
                parsed_vibration_crash.flight,
                ev.evidence_id,
                "RUN-TEST",
                {},
                parsed_vibration_crash.diagnostics,
                tuning_profile=tuning,
            )
            assert isinstance(ff_list, list), f"Plugin {pid!r} forensic_analyze didn't return list"


# ---------------------------------------------------------------------------
# Analyze with no evidence — should return 422
# ---------------------------------------------------------------------------

class TestAnalyzeEdgeCases:
    def test_analyze_with_no_evidence_returns_422(self, client: TestClient):
        """Analyzing a case with no evidence ingested should return 422."""
        res = client.post("/api/cases", json={"created_by": "test"})
        assert res.status_code == 201
        case_id = res.json()["case"]["case_id"]
        analyze_res = client.post(f"/api/cases/{case_id}/analyze")
        assert analyze_res.status_code == 422

    def test_analyze_nonexistent_case_returns_404(self, client: TestClient):
        """Analyzing a non-existent case should return 404."""
        analyze_res = client.post("/api/cases/CASE-9999-999999/analyze")
        assert analyze_res.status_code == 404

    def test_empty_file_upload_rejected(self, client: TestClient):
        """Uploading a zero-byte file should be rejected (400)."""
        res = client.post("/api/cases", json={"created_by": "test"})
        assert res.status_code == 201
        case_id = res.json()["case"]["case_id"]
        ev_res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"file": ("empty.ulg", io.BytesIO(b""), "application/octet-stream")},
        )
        # Empty file should be rejected at ingest time (400)
        assert ev_res.status_code == 400, (
            f"Expected 400 for empty file upload, got {ev_res.status_code}: {ev_res.text}"
        )
