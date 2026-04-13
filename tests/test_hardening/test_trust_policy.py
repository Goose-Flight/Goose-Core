"""Tests for plugin trust policy and fingerprinting.

Hardening Sprint — test_trust_policy
"""

from __future__ import annotations

from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState
from goose.plugins.trust import TrustPolicy, fingerprint_plugin


def _make_manifest(
    plugin_id: str = "test_plugin",
    trust_state: PluginTrustState = PluginTrustState.BUILTIN_TRUSTED,
) -> PluginManifest:
    return PluginManifest(
        plugin_id=plugin_id,
        name="Test Plugin",
        version="1.0.0",
        author="test",
        description="A test plugin",
        category=PluginCategory.HEALTH,
        supported_vehicle_types=["multirotor"],
        required_streams=[],
        optional_streams=[],
        output_finding_types=["test"],
        trust_state=trust_state,
    )


class TestTrustPolicyPermissive:
    def test_allows_builtin_trusted(self):
        policy = TrustPolicy(mode=TrustPolicy.PolicyMode.PERMISSIVE)
        manifest = _make_manifest(trust_state=PluginTrustState.BUILTIN_TRUSTED)
        allowed, reason = policy.evaluate(manifest, "abc123")
        assert allowed is True
        assert reason == ""

    def test_allows_community(self):
        policy = TrustPolicy(mode=TrustPolicy.PolicyMode.PERMISSIVE)
        manifest = _make_manifest(trust_state=PluginTrustState.COMMUNITY)
        allowed, reason = policy.evaluate(manifest, "abc123")
        assert allowed is True

    def test_blocks_blocked_plugin(self):
        policy = TrustPolicy(mode=TrustPolicy.PolicyMode.PERMISSIVE)
        manifest = _make_manifest(trust_state=PluginTrustState.BLOCKED)
        allowed, reason = policy.evaluate(manifest, "abc123")
        assert allowed is False
        assert "blocked" in reason


class TestTrustPolicyAllowlistOnly:
    def test_allows_listed_plugin(self):
        policy = TrustPolicy(
            mode=TrustPolicy.PolicyMode.ALLOWLIST_ONLY,
            allowlist=["test_plugin"],
        )
        manifest = _make_manifest(plugin_id="test_plugin")
        allowed, reason = policy.evaluate(manifest, "abc123")
        assert allowed is True

    def test_blocks_unlisted_plugin(self):
        policy = TrustPolicy(
            mode=TrustPolicy.PolicyMode.ALLOWLIST_ONLY,
            allowlist=["other_plugin"],
        )
        manifest = _make_manifest(plugin_id="test_plugin")
        allowed, reason = policy.evaluate(manifest, "abc123")
        assert allowed is False
        assert "not in allowlist" in reason

    def test_blocks_blocked_even_if_in_allowlist(self):
        policy = TrustPolicy(
            mode=TrustPolicy.PolicyMode.ALLOWLIST_ONLY,
            allowlist=["test_plugin"],
        )
        manifest = _make_manifest(
            plugin_id="test_plugin",
            trust_state=PluginTrustState.BLOCKED,
        )
        allowed, reason = policy.evaluate(manifest, "abc123")
        assert allowed is False
        assert "blocked" in reason


class TestFingerprintPlugin:
    def test_returns_nonempty_for_real_plugin(self):
        from goose.plugins import PLUGIN_REGISTRY
        plugin = next(iter(PLUGIN_REGISTRY.values()))
        fp = fingerprint_plugin(plugin)
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA-256 hex

    def test_returns_consistent_fingerprint(self):
        from goose.plugins import PLUGIN_REGISTRY
        plugin = next(iter(PLUGIN_REGISTRY.values()))
        fp1 = fingerprint_plugin(plugin)
        fp2 = fingerprint_plugin(plugin)
        assert fp1 == fp2

    def test_returns_empty_for_non_inspectable(self):
        # A plain object without source shouldn't crash
        fp = fingerprint_plugin(42)
        assert fp == ""


class TestTrustPolicySerialization:
    def test_to_dict(self):
        policy = TrustPolicy(
            mode=TrustPolicy.PolicyMode.ALLOWLIST_ONLY,
            allowlist=["plugin_a", "plugin_b"],
        )
        d = policy.to_dict()
        assert d["mode"] == "allowlist_only"
        assert d["allowlist"] == ["plugin_a", "plugin_b"]

    def test_from_dict_roundtrip(self):
        d = {"mode": "warned", "allowlist": ["x"]}
        policy = TrustPolicy.from_dict(d)
        assert policy.mode == TrustPolicy.PolicyMode.WARNED
        assert policy.allowlist == ["x"]
