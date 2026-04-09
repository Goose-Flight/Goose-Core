"""Tests for v11 Strategy Sprint feature gate scaffolding."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.features import (
    CAPABILITY_REQUIREMENTS,
    CapabilityGroup,
    EntitlementLevel,
    FeatureGate,
    get_feature_status,
)
from goose.forensics.case_service import CaseService
from goose.web import cases_api
from goose.web.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    svc = CaseService(base_dir=tmp_path / "cases")
    cases_api._set_service(svc)
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_level():
    """Ensure FeatureGate is reset to OSS_CORE between tests."""
    FeatureGate.set_level(EntitlementLevel.OSS_CORE)
    yield
    FeatureGate.set_level(EntitlementLevel.OSS_CORE)


class TestFeatureGateLevels:
    def test_default_level_is_oss_core(self):
        assert FeatureGate.current_level() == EntitlementLevel.OSS_CORE

    def test_oss_core_enables_core_case_workflow(self):
        assert FeatureGate.is_enabled(CapabilityGroup.CORE_CASE_WORKFLOW)

    def test_oss_core_does_not_enable_hosted_collaboration(self):
        assert not FeatureGate.is_enabled(CapabilityGroup.HOSTED_COLLABORATION)

    def test_oss_core_does_not_enable_advanced_reports(self):
        assert not FeatureGate.is_enabled(CapabilityGroup.ADVANCED_REPORTS)

    def test_local_pro_enables_advanced_reports(self):
        FeatureGate.set_level(EntitlementLevel.LOCAL_PRO)
        assert FeatureGate.is_enabled(CapabilityGroup.ADVANCED_REPORTS)
        assert FeatureGate.is_enabled(CapabilityGroup.PREMIUM_PLUGINS)
        assert FeatureGate.is_enabled(CapabilityGroup.CORE_CASE_WORKFLOW)

    def test_local_pro_does_not_enable_hosted(self):
        FeatureGate.set_level(EntitlementLevel.LOCAL_PRO)
        assert not FeatureGate.is_enabled(CapabilityGroup.HOSTED_COLLABORATION)

    def test_enterprise_gov_enables_strict_plugin_policy(self):
        FeatureGate.set_level(EntitlementLevel.ENTERPRISE_GOV)
        assert FeatureGate.is_enabled(CapabilityGroup.STRICT_PLUGIN_POLICY)
        assert FeatureGate.is_enabled(CapabilityGroup.ENTERPRISE_CONTROLS)
        # And everything below it
        assert FeatureGate.is_enabled(CapabilityGroup.CORE_CASE_WORKFLOW)
        assert FeatureGate.is_enabled(CapabilityGroup.ADVANCED_REPORTS)

    def test_require_raises_when_capability_missing(self):
        with pytest.raises(PermissionError):
            FeatureGate.require(CapabilityGroup.HOSTED_COLLABORATION)

    def test_require_passes_when_capability_available(self):
        # Should not raise
        FeatureGate.require(CapabilityGroup.CORE_CASE_WORKFLOW)


class TestFeatureGateToDict:
    def test_to_dict_returns_current_level(self):
        d = FeatureGate.to_dict()
        assert d["current_level"] == "oss_core"

    def test_to_dict_includes_all_capabilities(self):
        d = FeatureGate.to_dict()
        caps = d["capabilities"]
        for cap in CapabilityGroup:
            assert cap.value in caps

    def test_to_dict_capability_values_are_bool(self):
        d = FeatureGate.to_dict()
        for v in d["capabilities"].values():
            assert isinstance(v, bool)

    def test_requirements_mapping_complete(self):
        # Every capability has a requirement
        for cap in CapabilityGroup:
            assert cap in CAPABILITY_REQUIREMENTS


class TestFeatureGateAPI:
    def test_get_features_route(self, client: TestClient):
        r = client.get("/api/features")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["current_level"] == "oss_core"
        assert "capabilities" in data
        assert data["capabilities"]["core_case_workflow"] is True
        assert data["capabilities"]["hosted_collaboration"] is False


def test_get_feature_status_helper():
    d = get_feature_status()
    assert "current_level" in d
    assert "capabilities" in d
