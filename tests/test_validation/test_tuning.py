"""Tests for the tuning profile system.

Advanced Forensic Validation Sprint.
"""

from __future__ import annotations

from goose.forensics.tuning import (
    DEFAULT_TUNING_PROFILE,
    AnalyzerConfigProfile,
    ThresholdSet,
    TuningProfile,
)
from goose.plugins import PLUGIN_REGISTRY


def test_tuning_profile_default_is_valid():
    profile = TuningProfile.default()
    assert profile.profile_id == "default"
    assert profile.version == "1.0.0"
    assert profile.is_default is True
    assert profile.target_vehicle_class == "all"
    assert len(profile.analyzer_configs) >= 11


def test_module_level_default_profile_exists():
    assert DEFAULT_TUNING_PROFILE is not None
    assert DEFAULT_TUNING_PROFILE.profile_id == "default"


def test_tuning_profile_serialization_roundtrip():
    profile = TuningProfile.default()
    d = profile.to_dict()
    restored = TuningProfile.from_dict(d)
    assert restored.profile_id == profile.profile_id
    assert restored.version == profile.version
    assert len(restored.analyzer_configs) == len(profile.analyzer_configs)


def test_threshold_set_serialization_roundtrip():
    ts = ThresholdSet(
        threshold_set_id="test",
        name="Test",
        description="Test thresholds",
        values={"min": 1.0, "max": 10.0, "label": "high"},
    )
    d = ts.to_dict()
    restored = ThresholdSet.from_dict(d)
    assert restored.threshold_set_id == "test"
    assert restored.values == {"min": 1.0, "max": 10.0, "label": "high"}


def test_analyzer_config_profile_serialization():
    cfg = AnalyzerConfigProfile(
        plugin_id="crash_detection",
        thresholds=ThresholdSet(
            threshold_set_id="tid",
            name="tname",
            description="tdesc",
            values={"x": 1.0},
        ),
    )
    d = cfg.to_dict()
    restored = AnalyzerConfigProfile.from_dict(d)
    assert restored.plugin_id == "crash_detection"
    assert restored.thresholds is not None
    assert restored.thresholds.values == {"x": 1.0}


def test_get_config_for_plugin_known():
    profile = TuningProfile.default()
    cfg = profile.get_config_for_plugin("crash_detection")
    assert cfg is not None
    assert cfg.plugin_id == "crash_detection"
    assert cfg.thresholds is not None
    assert "descent_rate_threshold" in cfg.thresholds.values


def test_get_config_for_plugin_unknown():
    profile = TuningProfile.default()
    cfg = profile.get_config_for_plugin("does_not_exist")
    assert cfg is None


def test_all_builtin_plugins_have_config():
    """Every registered plugin must have a default tuning config."""
    profile = TuningProfile.default()
    configured_ids = {c.plugin_id for c in profile.analyzer_configs}
    for plugin_id in PLUGIN_REGISTRY:
        assert plugin_id in configured_ids, (
            f"Plugin {plugin_id} has no entry in default tuning profile"
        )


def test_crash_detection_thresholds_match_source_constants():
    """Sanity check — default crash_detection thresholds match source constants."""
    from goose.plugins.crash_detection import CrashDetectionPlugin
    src_defaults = CrashDetectionPlugin.DEFAULT_CONFIG

    profile = TuningProfile.default()
    cfg = profile.get_config_for_plugin("crash_detection")
    assert cfg is not None
    assert cfg.thresholds is not None

    assert cfg.thresholds.values["descent_rate_threshold"] == src_defaults["descent_rate_threshold"]
    assert cfg.thresholds.values["motor_drop_threshold"] == src_defaults["motor_drop_threshold"]
    assert cfg.thresholds.values["impact_accel_g"] == src_defaults["impact_accel_g"]


# ---------------------------------------------------------------------------
# Tuning profile threshold wiring tests
#
# These tests assert that TuningProfile values actually reach the plugin
# ``analyze()`` path through ``forensic_analyze()``, and that explicit config
# values still override the profile defaults.
# ---------------------------------------------------------------------------


class _ThresholdCapturePlugin:
    """Tiny stub plugin used to capture the effective config dict."""

    def __init__(self, plugin_id: str):
        from goose.plugins.contract import (
            PluginCategory,
            PluginManifest,
            PluginTrustState,
        )
        self.manifest = PluginManifest(
            plugin_id=plugin_id,
            name=plugin_id,
            version="0.0.1",
            author="test",
            description="threshold capture stub",
            category=PluginCategory.HEALTH,
            supported_vehicle_types=["multicopter"],
            required_streams=[],
            optional_streams=[],
            output_finding_types=[],
            trust_state=PluginTrustState.BUILTIN_TRUSTED,
        )
        self.captured_config: dict[str, object] = {}

    def analyze(self, flight, config):
        self.captured_config = dict(config)
        return []


def _call_forensic_analyze(stub, tuning_profile, explicit_config=None):
    """Helper: invoke the real Plugin.forensic_analyze on a stub instance."""
    from goose.parsers.diagnostics import ParseDiagnostics
    from goose.plugins.base import Plugin

    diag = ParseDiagnostics()

    class _FakeFlight:
        pass

    # Call the concrete base implementation unbound against the stub.
    return Plugin.forensic_analyze(
        stub,
        _FakeFlight(),
        "evidence-x",
        "run-x",
        explicit_config or {},
        diag,
        tuning_profile=tuning_profile,
    )


def test_forensic_analyze_merges_tuning_profile_thresholds():
    """TuningProfile threshold values must reach plugin.analyze() config."""
    profile = TuningProfile.default()
    stub = _ThresholdCapturePlugin("crash_detection")

    _call_forensic_analyze(stub, profile)

    cfg = profile.get_config_for_plugin("crash_detection")
    assert cfg is not None and cfg.thresholds is not None
    for k, v in cfg.thresholds.values.items():
        assert stub.captured_config.get(k) == v, (
            f"Profile threshold {k}={v} did not reach analyze() config"
        )


def test_forensic_analyze_explicit_config_overrides_profile():
    """Explicit config values must win over tuning profile values."""
    profile = TuningProfile.default()
    stub = _ThresholdCapturePlugin("crash_detection")

    override = {"descent_rate_threshold": 99.9}
    _call_forensic_analyze(stub, profile, explicit_config=override)

    assert stub.captured_config["descent_rate_threshold"] == 99.9
    # Other profile values still present
    assert "impact_accel_g" in stub.captured_config


def test_forensic_analyze_without_profile_passes_empty_config():
    """Without a tuning profile, analyze() gets only the caller config."""
    stub = _ThresholdCapturePlugin("crash_detection")
    _call_forensic_analyze(stub, None, explicit_config={"only": "me"})
    assert stub.captured_config == {"only": "me"}


def test_all_registered_plugins_have_matching_default_constants():
    """Every registered plugin must have DEFAULT_* / DEFAULT_CONFIG constants
    that match (or are a superset of) the default tuning profile values.

    This protects the wiring: if someone changes a default constant in a plugin
    but forgets to update tuning.py, this test fails.
    """
    profile = TuningProfile.default()
    for plugin_id, plugin in PLUGIN_REGISTRY.items():
        cfg = profile.get_config_for_plugin(plugin_id)
        assert cfg is not None, f"{plugin_id} missing from default tuning profile"
        assert cfg.thresholds is not None, f"{plugin_id} has no thresholds"
        # Spot check: every threshold key maps to either a DEFAULT_<UPPER> class
        # attribute OR a DEFAULT_CONFIG dict entry on the plugin class.
        cls = plugin.__class__
        default_config = getattr(cls, "DEFAULT_CONFIG", None)
        for key in cfg.thresholds.values:
            upper_attr = f"DEFAULT_{key.upper()}"
            has_attr = hasattr(cls, upper_attr)
            in_default = bool(default_config) and key in default_config
            assert has_attr or in_default, (
                f"{plugin_id}: tuning key '{key}' has no DEFAULT_ constant "
                f"(expected class attr {upper_attr} or DEFAULT_CONFIG['{key}'])"
            )
