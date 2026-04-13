"""Tests for the v11 Strategy Sprint profile system."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.forensics.profiles import (
    PROFILE_CONFIGS,
    ProfileConfig,
    UserProfile,
    WordingPack,
    get_profile,
)
from goose.web import cases_api
from goose.web.app import create_app

ALL_PROFILE_IDS = {p.value for p in UserProfile}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    svc = CaseService(base_dir=tmp_path / "cases")
    cases_api._set_service(svc)
    app = create_app()
    return TestClient(app)


class TestProfileRegistry:
    def test_all_profile_ids_present(self):
        assert set(PROFILE_CONFIGS.keys()) == ALL_PROFILE_IDS

    def test_default_entry_path_is_valid(self):
        for cfg in PROFILE_CONFIGS.values():
            assert cfg.default_entry_path in {"quick_analysis", "investigation_case"}

    def test_non_empty_plugin_lists_or_advanced(self):
        for pid, cfg in PROFILE_CONFIGS.items():
            if pid == "advanced":
                # advanced intentionally has empty preference lists
                assert cfg.default_plugins == []
            else:
                assert len(cfg.default_plugins) > 0, f"{pid} has empty default_plugins"

    def test_wording_pack_fields_populated(self):
        for pid, cfg in PROFILE_CONFIGS.items():
            w = cfg.wording
            assert w.profile_id == pid
            for field_name in (
                "workflow_label", "event_label", "operator_label",
                "platform_label", "analysis_label", "summary_heading",
            ):
                assert getattr(w, field_name), f"{pid} missing {field_name}"

    def test_report_defaults_non_empty(self):
        for pid, cfg in PROFILE_CONFIGS.items():
            assert len(cfg.report_defaults) > 0, f"{pid} has empty report_defaults"

    def test_findings_sort_priority_uses_valid_severities(self):
        valid = {"critical", "warning", "info", "pass"}
        for cfg in PROFILE_CONFIGS.values():
            for sev in cfg.findings_sort_priority:
                assert sev in valid


class TestProfileConfigRoundtrip:
    def test_all_profiles_roundtrip(self):
        for _pid, cfg in PROFILE_CONFIGS.items():
            d = cfg.to_dict()
            restored = ProfileConfig.from_dict(d)
            assert restored.profile_id == cfg.profile_id
            assert restored.name == cfg.name
            assert restored.default_plugins == cfg.default_plugins
            assert restored.wording.workflow_label == cfg.wording.workflow_label

    def test_from_dict_ignores_unknown_keys(self):
        d = PROFILE_CONFIGS["racer"].to_dict()
        d["future_field_we_do_not_know_yet"] = "xyz"
        restored = ProfileConfig.from_dict(d)
        assert restored.profile_id == "racer"

    def test_wording_pack_roundtrip(self):
        original = PROFILE_CONFIGS["gov_mil"].wording
        restored = WordingPack.from_dict(original.to_dict())
        assert restored == original


class TestGetProfile:
    def test_get_known_profile(self):
        cfg = get_profile("racer")
        assert cfg.profile_id == "racer"

    def test_unknown_profile_returns_default(self):
        cfg = get_profile("totally-not-a-profile")
        assert cfg.profile_id == "default"

    def test_empty_string_returns_default(self):
        cfg = get_profile("")
        assert cfg.profile_id == "default"


class TestProfileAPI:
    def test_list_all_profiles(self, client: TestClient):
        res = client.get("/api/profiles")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert set(data["profiles"].keys()) == ALL_PROFILE_IDS
        assert data["count"] == len(ALL_PROFILE_IDS)

    def test_get_single_profile(self, client: TestClient):
        res = client.get("/api/profiles/gov_mil")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["fallback"] is False
        assert data["profile"]["profile_id"] == "gov_mil"
        assert data["profile"]["wording"]["workflow_label"] == "Sortie"

    def test_unknown_profile_returns_default_with_fallback(self, client: TestClient):
        res = client.get("/api/profiles/not_a_real_profile")
        assert res.status_code == 200
        data = res.json()
        assert data["fallback"] is True
        assert data["profile"]["profile_id"] == "default"
