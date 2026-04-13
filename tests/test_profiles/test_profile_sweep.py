"""Phase 2 Bulletproofing Sprint — Profile sweep regression tests.

Validates all 7 profiles end-to-end via the web API:
- No profile crashes analysis
- Profile-specific wording is different across profiles
- Each profile runs successfully on real fixture files
- Profile-ordered findings and hypotheses are returned
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.forensics.profiles import PROFILE_CONFIGS, UserProfile, get_profile
from goose.web import cases_api
from goose.web.app import create_app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
VIBRATION_CRASH = FIXTURES_DIR / "px4_vibration_crash.ulg"
NORMAL_FLIGHT = FIXTURES_DIR / "px4_normal_flight.ulg"

ALL_PROFILES = [p.value for p in UserProfile]  # 7 profiles
assert set(ALL_PROFILES) == {"racer", "research", "shop_repair", "factory_qa", "gov_mil", "advanced", "default"}


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


def _run_analysis_with_profile(
    client: TestClient,
    fixture_path: Path,
    profile: str,
) -> dict[str, Any]:
    """Create a case with a given profile, upload evidence, run analysis."""
    create_res = client.post("/api/cases", json={"created_by": "sweep_test", "profile": profile})
    assert create_res.status_code == 201, f"create_case failed: {create_res.text}"
    case_id = create_res.json()["case"]["case_id"]

    with open(fixture_path, "rb") as f:
        content = f.read()
    ev_res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": (fixture_path.name, io.BytesIO(content), "application/octet-stream")},
    )
    assert ev_res.status_code == 201, f"evidence upload failed: {ev_res.text}"

    analyze_res = client.post(f"/api/cases/{case_id}/analyze")
    return {
        "case_id": case_id,
        "profile": profile,
        "analyze_res": analyze_res,
        "analyze_data": analyze_res.json() if analyze_res.status_code == 200 else {},
    }


# ---------------------------------------------------------------------------
# Profile config validation
# ---------------------------------------------------------------------------


class TestProfileConfigCompleteness:
    def test_all_7_profiles_registered(self):
        assert set(PROFILE_CONFIGS.keys()) == set(ALL_PROFILES)

    def test_all_profiles_have_unique_wording_labels(self):
        """Each profile should have distinctive wording — not all identical."""
        workflow_labels = {cfg.wording.workflow_label for cfg in PROFILE_CONFIGS.values()}
        # Not all workflow_labels should be the same
        assert len(workflow_labels) > 1, "All profiles have identical workflow_labels"

    def test_wording_differs_between_racer_and_gov_mil(self):
        racer = get_profile("racer")
        gov_mil = get_profile("gov_mil")
        # These are deliberately different user profiles
        assert racer.wording.workflow_label != gov_mil.wording.workflow_label
        assert racer.wording.event_label != gov_mil.wording.event_label
        assert racer.wording.operator_label != gov_mil.wording.operator_label

    def test_advanced_profile_has_empty_plugin_preferences(self):
        adv = get_profile("advanced")
        assert adv.default_plugins == []
        assert adv.secondary_plugins == []
        assert adv.deprioritized_plugins == []

    def test_all_profiles_have_report_defaults(self):
        for pid, cfg in PROFILE_CONFIGS.items():
            assert len(cfg.report_defaults) > 0, f"{pid} has no report_defaults"

    def test_unknown_profile_falls_back_gracefully(self):
        cfg = get_profile("not_a_real_profile_xyz")
        assert cfg.profile_id == "default"

    def test_all_profiles_roundtrip_serialization(self):
        for _pid, cfg in PROFILE_CONFIGS.items():
            d = cfg.to_dict()
            from goose.forensics.profiles import ProfileConfig

            restored = ProfileConfig.from_dict(d)
            assert restored.profile_id == cfg.profile_id
            assert restored.wording.workflow_label == cfg.wording.workflow_label


# ---------------------------------------------------------------------------
# Analysis sweep: every profile must complete without crashing
# ---------------------------------------------------------------------------


class TestProfileAnalysisSweep:
    """Run analysis with each of the 7 profiles on the vibration crash fixture."""

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_analysis_completes_with_profile(self, client: TestClient, profile: str):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _run_analysis_with_profile(client, VIBRATION_CRASH, profile)
        assert out["analyze_res"].status_code == 200, f"Profile {profile!r} analysis failed ({out['analyze_res'].status_code}): {out['analyze_res'].text[:300]}"

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_analysis_returns_findings_with_profile(self, client: TestClient, profile: str):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _run_analysis_with_profile(client, VIBRATION_CRASH, profile)
        assert out["analyze_res"].status_code == 200
        data = out["analyze_data"]
        assert "findings" in data
        assert isinstance(data["findings"], list)

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_analysis_returns_hypotheses_with_profile(self, client: TestClient, profile: str):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _run_analysis_with_profile(client, VIBRATION_CRASH, profile)
        assert out["analyze_res"].status_code == 200
        data = out["analyze_data"]
        assert "hypotheses" in data
        assert isinstance(data["hypotheses"], list)

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_analysis_returns_profile_config_in_response(self, client: TestClient, profile: str):
        """The analyze response must include the resolved profile config."""
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _run_analysis_with_profile(client, VIBRATION_CRASH, profile)
        assert out["analyze_res"].status_code == 200
        data = out["analyze_data"]
        assert "profile" in data
        assert data["profile"]["profile_id"] == profile

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_analysis_run_id_present_with_profile(self, client: TestClient, profile: str):
        if not VIBRATION_CRASH.exists():
            pytest.skip("Fixture not found")
        out = _run_analysis_with_profile(client, VIBRATION_CRASH, profile)
        assert out["analyze_res"].status_code == 200
        assert out["analyze_data"]["run_id"].startswith("RUN-")

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_normal_flight_analysis_completes_with_profile(self, client: TestClient, profile: str):
        """All profiles must handle a normal (non-crash) flight without crashing."""
        if not NORMAL_FLIGHT.exists():
            pytest.skip("Fixture not found")
        out = _run_analysis_with_profile(client, NORMAL_FLIGHT, profile)
        assert out["analyze_res"].status_code == 200, f"Profile {profile!r} analysis failed on normal flight: {out['analyze_res'].text[:300]}"


# ---------------------------------------------------------------------------
# Profile API endpoint sweep
# ---------------------------------------------------------------------------


class TestProfileAPIEndpoints:
    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_get_profile_endpoint(self, client: TestClient, profile: str):
        res = client.get(f"/api/profiles/{profile}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["profile"]["profile_id"] == profile
        assert data["fallback"] is False

    def test_list_profiles_includes_all_7(self, client: TestClient):
        res = client.get("/api/profiles")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert set(data["profiles"].keys()) == set(ALL_PROFILES)
        assert data["count"] == len(ALL_PROFILES)

    def test_unknown_profile_api_returns_default(self, client: TestClient):
        res = client.get("/api/profiles/totally_unknown_profile")
        assert res.status_code == 200
        data = res.json()
        assert data["fallback"] is True
        assert data["profile"]["profile_id"] == "default"


# ---------------------------------------------------------------------------
# Profile wording distinctiveness
# ---------------------------------------------------------------------------


class TestProfileWordingDistinctiveness:
    """Ensure profile wording is distinct enough to differentiate user classes."""

    def test_racer_uses_run_not_case(self):
        cfg = get_profile("racer")
        assert cfg.wording.workflow_label == "Run"

    def test_gov_mil_uses_sortie(self):
        cfg = get_profile("gov_mil")
        assert cfg.wording.workflow_label == "Sortie"

    def test_shop_repair_uses_job(self):
        cfg = get_profile("shop_repair")
        assert cfg.wording.workflow_label == "Job"

    def test_research_uses_test(self):
        cfg = get_profile("research")
        assert cfg.wording.workflow_label == "Test"

    def test_factory_qa_uses_test(self):
        cfg = get_profile("factory_qa")
        assert cfg.wording.workflow_label == "Test"

    def test_advanced_uses_case(self):
        cfg = get_profile("advanced")
        assert cfg.wording.workflow_label == "Case"

    def test_racer_calls_events_crashes(self):
        cfg = get_profile("racer")
        assert cfg.wording.event_label == "Crash"

    def test_gov_mil_calls_events_mishaps(self):
        cfg = get_profile("gov_mil")
        assert cfg.wording.event_label == "Mishap"

    def test_all_profiles_have_summary_heading(self):
        for pid, cfg in PROFILE_CONFIGS.items():
            assert cfg.wording.summary_heading, f"{pid} has empty summary_heading"

    def test_all_profile_wordings_have_report_sections(self):
        for pid, cfg in PROFILE_CONFIGS.items():
            assert isinstance(cfg.wording.report_sections, dict), f"{pid} report_sections is not a dict"
