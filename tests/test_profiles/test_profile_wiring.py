"""Tests for v11 Strategy Sprint — profile-aware analysis pipeline wiring.

These tests verify that the Investigation Case analyze route honors the
case's ``profile`` field:

- Primary plugins (from ``ProfileConfig.default_plugins``) run first.
- Advanced profile (empty default list) runs every registered plugin.
- Findings are ordered per the profile's ``findings_sort_priority``.
- The AnalysisRun record captures the profile that was active.
- GET /api/cases/{id} returns a ``profile_config`` blob.
- Deprioritized plugins still execute, just last.

Profiles never change forensic truth — only ordering and defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.forensics.profiles import get_profile
from goose.plugins import PLUGIN_REGISTRY
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


def _fixture_bytes() -> bytes:
    if not SAMPLE_ULG.exists():
        pytest.skip(f"Sample ULG fixture missing: {SAMPLE_ULG}")
    return SAMPLE_ULG.read_bytes()


def _create_case_with_profile(client: TestClient, profile: str) -> str:
    res = client.post("/api/cases", json={"profile": profile, "created_by": "test"})
    assert res.status_code == 201, res.text
    return res.json()["case"]["case_id"]


def _ingest(client: TestClient, case_id: str) -> None:
    content = _fixture_bytes()
    r = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("flight.ulg", content, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text


def _analyze(client: TestClient, case_id: str) -> dict:
    r = client.post(f"/api/cases/{case_id}/analyze")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# GET /api/cases/{id} — profile_config embedded in response
# ---------------------------------------------------------------------------


class TestCaseDetailProfileConfig:
    def test_detail_includes_profile_config_for_default(self, client: TestClient):
        case_id = _create_case_with_profile(client, "default")
        res = client.get(f"/api/cases/{case_id}")
        assert res.status_code == 200
        data = res.json()
        assert "profile_config" in data
        cfg = data["profile_config"]
        assert cfg["profile_id"] == "default"
        assert "wording" in cfg
        assert "visible_case_fields" in cfg
        assert "chart_presets" in cfg

    def test_detail_includes_profile_config_for_gov_mil(self, client: TestClient):
        case_id = _create_case_with_profile(client, "gov_mil")
        res = client.get(f"/api/cases/{case_id}")
        data = res.json()
        cfg = data["profile_config"]
        assert cfg["profile_id"] == "gov_mil"
        assert cfg["wording"]["workflow_label"] == "Sortie"
        assert "mission_id" in cfg["visible_case_fields"]

    def test_detail_falls_back_when_profile_missing(self, client: TestClient):
        # Create with default, then rewrite profile to something unknown on disk.
        case_id = _create_case_with_profile(client, "default")
        svc = cases_api.get_service()
        case = svc.get_case(case_id)
        case.profile = "not_a_real_profile"
        svc.save_case(case)

        res = client.get(f"/api/cases/{case_id}")
        data = res.json()
        # Unknown profile_id must resolve to the default profile_config,
        # never 500 or None.
        assert data["profile_config"]["profile_id"] == "default"


# ---------------------------------------------------------------------------
# Plugin selection by profile
# ---------------------------------------------------------------------------


class TestAnalyzeUsesProfilePlugins:
    def test_racer_runs_its_default_plugins(self, client: TestClient):
        case_id = _create_case_with_profile(client, "racer")
        _ingest(client, case_id)
        _analyze(client, case_id)

        # The racer profile primary plugins should all appear in the
        # recorded plugin run list (unless they aren't registered).
        racer_cfg = get_profile("racer")
        expected = [p for p in racer_cfg.default_plugins if p in PLUGIN_REGISTRY]
        assert len(expected) > 0

        detail = client.get(f"/api/cases/{case_id}").json()["case"]
        run = detail["analysis_runs"][-1]
        plugin_ids = run["plugin_ids_used"]
        for pid in expected:
            assert pid in plugin_ids, f"Racer primary plugin {pid} was not run"

    def test_primary_plugins_run_first(self, client: TestClient):
        case_id = _create_case_with_profile(client, "racer")
        _ingest(client, case_id)
        _analyze(client, case_id)

        # Plugin execution order is persisted to plugin_diagnostics.json.
        svc = cases_api.get_service()
        import json
        diag_path = svc.case_dir(case_id) / "analysis" / "plugin_diagnostics.json"
        assert diag_path.exists()
        bundle = json.loads(diag_path.read_text(encoding="utf-8"))
        order = bundle["plugin_execution_order"]
        primary = bundle["profile_primary_plugins"]
        assert len(primary) > 0
        # Every primary plugin must appear before any non-primary plugin.
        primary_indices = [order.index(p) for p in primary]
        non_primary_indices = [
            i for i, p in enumerate(order) if p not in primary
        ]
        assert max(primary_indices) < min(non_primary_indices)

    def test_advanced_profile_runs_all_plugins(self, client: TestClient):
        case_id = _create_case_with_profile(client, "advanced")
        _ingest(client, case_id)
        _analyze(client, case_id)

        detail = client.get(f"/api/cases/{case_id}").json()["case"]
        run = detail["analysis_runs"][-1]
        plugin_ids_used = set(run["plugin_ids_used"])
        registry_ids = set(PLUGIN_REGISTRY.keys())
        assert plugin_ids_used == registry_ids

    def test_deprioritized_plugins_still_run_but_ordered_last(self, client: TestClient):
        # Racer deprioritizes log_health.
        case_id = _create_case_with_profile(client, "racer")
        _ingest(client, case_id)
        _analyze(client, case_id)

        svc = cases_api.get_service()
        import json
        bundle = json.loads(
            (svc.case_dir(case_id) / "analysis" / "plugin_diagnostics.json").read_text(encoding="utf-8")
        )
        order = bundle["plugin_execution_order"]
        deprio = bundle["profile_deprioritized_plugins"]
        assert "log_health" in deprio
        # Deprioritized plugins must still be present — availability, not filtering.
        assert "log_health" in order
        # And they must come after every non-deprioritized entry.
        log_idx = order.index("log_health")
        for pid in order:
            if pid in deprio:
                continue
            assert order.index(pid) < log_idx


# ---------------------------------------------------------------------------
# Findings ordering
# ---------------------------------------------------------------------------


class TestFindingsOrdering:
    def test_findings_ordered_by_profile_priority(self, client: TestClient):
        case_id = _create_case_with_profile(client, "gov_mil")
        _ingest(client, case_id)
        data = _analyze(client, case_id)

        findings = data["findings"]
        if not findings:
            pytest.skip("No findings emitted for fixture — ordering check trivially passes")

        gov = get_profile("gov_mil")
        priorities = gov.findings_sort_priority
        # Build a rank map: lower == earlier.
        if "critical" not in priorities:
            expected_ranks = ["critical", *priorities]
        else:
            expected_ranks = ["critical"] + [s for s in priorities if s != "critical"]
        rank = {s: i for i, s in enumerate(expected_ranks)}

        last_rank = -1
        for f in findings:
            r = rank.get(f["severity"], len(rank) + 1)
            assert r >= last_rank, (
                f"Finding severity {f['severity']} (rank {r}) appeared "
                f"after a severity with rank {last_rank}"
            )
            last_rank = r


# ---------------------------------------------------------------------------
# Run metadata records the profile
# ---------------------------------------------------------------------------


class TestRunMetadataCapturesProfile:
    def test_run_records_profile_id(self, client: TestClient):
        case_id = _create_case_with_profile(client, "gov_mil")
        _ingest(client, case_id)
        _analyze(client, case_id)

        detail = client.get(f"/api/cases/{case_id}").json()["case"]
        run = detail["analysis_runs"][-1]
        assert run["profile_id"] == "gov_mil"

    def test_plugin_diagnostics_records_profile(self, client: TestClient):
        case_id = _create_case_with_profile(client, "shop_repair")
        _ingest(client, case_id)
        _analyze(client, case_id)

        svc = cases_api.get_service()
        import json
        bundle = json.loads(
            (svc.case_dir(case_id) / "analysis" / "plugin_diagnostics.json").read_text(encoding="utf-8")
        )
        assert bundle["profile_id"] == "shop_repair"
        assert isinstance(bundle["profile_primary_plugins"], list)
        # shop_repair has explicit primary plugins.
        assert len(bundle["profile_primary_plugins"]) > 0

    def test_analyze_response_includes_profile(self, client: TestClient):
        case_id = _create_case_with_profile(client, "research")
        _ingest(client, case_id)
        data = _analyze(client, case_id)
        assert "profile" in data
        assert data["profile"]["profile_id"] == "research"
