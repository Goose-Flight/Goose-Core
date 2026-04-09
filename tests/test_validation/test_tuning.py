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
