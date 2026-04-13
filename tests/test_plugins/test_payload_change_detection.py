"""Tests for the payload_change_detection plugin (Phase 1 candidate detector)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata
from goose.forensics.tuning import DEFAULT_TUNING_PROFILE, TuningProfile
from goose.parsers.diagnostics import ParseDiagnostics
from goose.plugins import PLUGIN_REGISTRY
from goose.plugins.contract import (
    PluginCategory,
    PluginDiagnostics,
    PluginTrustState,
)
from goose.plugins.payload_change_detection import PayloadChangeDetectionPlugin

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_metadata() -> FlightMetadata:
    return FlightMetadata(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type="x500",
        hardware="Pixhawk 6C",
        duration_sec=60.0,
        start_time_utc=datetime(2026, 1, 1, 0, 0, 0),
        log_format="ulog",
        motor_count=4,
    )


def _make_battery(timestamps: list[float], currents: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "current": currents,
            "voltage": [15.0] * len(timestamps),
        }
    )


def _make_flight(battery: pd.DataFrame | None = None) -> Flight:
    flight = Flight(metadata=_make_metadata())
    if battery is not None:
        flight.battery = battery
    return flight


def _make_parse_diagnostics() -> ParseDiagnostics:
    return ParseDiagnostics(
        parser_selected="ULogParser",
        detected_format="ulog",
        format_confidence=1.0,
        parser_confidence=1.0,
        supported=True,
    )


@pytest.fixture
def plugin() -> PayloadChangeDetectionPlugin:
    return PayloadChangeDetectionPlugin()


@pytest.fixture
def empty_flight() -> Flight:
    return _make_flight()


@pytest.fixture
def step_change_flight() -> Flight:
    """Flight with a clean current step-down at t=30s (simulating payload drop)."""
    # 60 seconds at 10 Hz = 600 samples
    timestamps = [i * 0.1 for i in range(600)]
    # Baseline ~15A before t=30s, ~9A after (6A drop — well above 3A default)
    currents = [15.0 if t < 30.0 else 9.0 for t in timestamps]
    battery = _make_battery(timestamps, currents)
    return _make_flight(battery=battery)


@pytest.fixture
def flat_current_flight() -> Flight:
    """Flight with constant current — no candidate events."""
    timestamps = [i * 0.1 for i in range(600)]
    currents = [15.0] * 600
    battery = _make_battery(timestamps, currents)
    return _make_flight(battery=battery)


@pytest.fixture
def short_flight() -> Flight:
    """Flight shorter than the minimum duration."""
    timestamps = [i * 0.1 for i in range(50)]  # 5 seconds
    currents = [15.0] * 50
    battery = _make_battery(timestamps, currents)
    return _make_flight(battery=battery)


# ---------------------------------------------------------------------------
# Manifest / registry
# ---------------------------------------------------------------------------


class TestManifest:
    def test_plugin_id(self, plugin: PayloadChangeDetectionPlugin) -> None:
        assert plugin.manifest.plugin_id == "payload_change_detection"

    def test_category(self, plugin: PayloadChangeDetectionPlugin) -> None:
        assert plugin.manifest.category == PluginCategory.MISSION_RULES

    def test_required_streams(self, plugin: PayloadChangeDetectionPlugin) -> None:
        assert "battery" in plugin.manifest.required_streams

    def test_output_finding_types(self, plugin: PayloadChangeDetectionPlugin) -> None:
        assert "possible_mass_reduction_event" in plugin.manifest.output_finding_types
        assert "possible_load_increase_event" in plugin.manifest.output_finding_types

    def test_trust_state_builtin(self, plugin: PayloadChangeDetectionPlugin) -> None:
        assert plugin.manifest.trust_state == PluginTrustState.BUILTIN_TRUSTED

    def test_registered_in_plugin_registry(self) -> None:
        assert "payload_change_detection" in PLUGIN_REGISTRY
        p = PLUGIN_REGISTRY["payload_change_detection"]
        assert isinstance(p, PayloadChangeDetectionPlugin)


# ---------------------------------------------------------------------------
# Analyze behaviour
# ---------------------------------------------------------------------------


class TestAnalyze:
    def test_empty_flight_returns_empty_findings(self, plugin: PayloadChangeDetectionPlugin, empty_flight: Flight) -> None:
        findings = plugin.analyze(empty_flight, {})
        assert findings == []

    def test_short_flight_returns_empty(self, plugin: PayloadChangeDetectionPlugin, short_flight: Flight) -> None:
        findings = plugin.analyze(short_flight, {})
        assert findings == []

    def test_flat_current_returns_empty(self, plugin: PayloadChangeDetectionPlugin, flat_current_flight: Flight) -> None:
        findings = plugin.analyze(flat_current_flight, {})
        assert findings == []

    def test_step_change_detected(self, plugin: PayloadChangeDetectionPlugin, step_change_flight: Flight) -> None:
        findings = plugin.analyze(step_change_flight, {})
        assert len(findings) >= 1, "Expected at least one candidate event"

        f = findings[0]
        assert isinstance(f, Finding)
        assert f.plugin_name == "payload_change_detection"
        # Step is a reduction — current dropped
        assert f.evidence["current_delta_amps"] < 0
        assert f.evidence["finding_type"] == "possible_mass_reduction_event"
        assert f.evidence["detection_phase"] == "phase_1_candidate"

    def test_phase_1_confidence_is_low(self, plugin: PayloadChangeDetectionPlugin, step_change_flight: Flight) -> None:
        findings = plugin.analyze(step_change_flight, {})
        assert findings
        for f in findings:
            # Phase 1 confidence 0.25–0.45 — score 25–45
            assert 25 <= f.score <= 45, f"Phase 1 score should be in [25,45], got {f.score}"

    def test_config_threshold_override_suppresses_event(self, plugin: PayloadChangeDetectionPlugin, step_change_flight: Flight) -> None:
        # Raise threshold well above the 6A step — no finding
        findings = plugin.analyze(step_change_flight, {"current_delta_threshold": 20.0})
        assert findings == []


# ---------------------------------------------------------------------------
# Detection primitives
# ---------------------------------------------------------------------------


class TestCandidateWindows:
    def test_clean_step_change_detected(self, plugin: PayloadChangeDetectionPlugin) -> None:
        times = [i * 0.1 for i in range(600)]
        currents = [15.0 if t < 30.0 else 9.0 for t in times]
        cands = plugin._find_candidate_windows(times, currents, delta_threshold=3.0, sustained_s=1.5, pre_post_s=5.0)
        assert len(cands) >= 1
        c = cands[0]
        assert c["delta_amps"] < 0
        assert abs(c["delta_amps"]) >= 3.0
        assert c["duration_s"] >= 1.5

    def test_no_change_returns_empty(self, plugin: PayloadChangeDetectionPlugin) -> None:
        times = [i * 0.1 for i in range(600)]
        currents = [15.0] * 600
        cands = plugin._find_candidate_windows(times, currents, delta_threshold=3.0, sustained_s=1.5, pre_post_s=5.0)
        assert cands == []


class TestThrottleExplainsChange:
    def test_matching_throttle_suppresses(self, plugin: PayloadChangeDetectionPlugin) -> None:
        # Build a throttle stream that rises sharply around the same event window
        throttle = [(t * 0.1, 0.4 if t * 0.1 < 30.0 else 0.8) for t in range(600)]
        assert (
            plugin._throttle_explains_change(
                throttle,
                start_time=29.5,
                end_time=31.0,
                delta_amps=5.0,
                tolerance=0.15,
            )
            is True
        )

    def test_flat_throttle_does_not_suppress(self, plugin: PayloadChangeDetectionPlugin) -> None:
        throttle = [(t * 0.1, 0.5) for t in range(600)]
        assert (
            plugin._throttle_explains_change(
                throttle,
                start_time=29.5,
                end_time=31.0,
                delta_amps=5.0,
                tolerance=0.15,
            )
            is False
        )

    def test_no_throttle_samples_returns_false(self, plugin: PayloadChangeDetectionPlugin) -> None:
        assert plugin._throttle_explains_change([], 29.5, 31.0, 5.0, 0.15) is False


# ---------------------------------------------------------------------------
# forensic_analyze wrapper (contract compliance)
# ---------------------------------------------------------------------------


class TestForensicAnalyze:
    def test_diagnostics_when_skipped(self, plugin: PayloadChangeDetectionPlugin, empty_flight: Flight) -> None:
        """No battery stream → plugin is skipped with correct diagnostics."""
        parse_diag = _make_parse_diagnostics()
        findings, diag = plugin.forensic_analyze(
            empty_flight,
            "EV-TEST",
            "RUN-TEST",
            {},
            parse_diag,
        )
        assert findings == []
        assert isinstance(diag, PluginDiagnostics)
        assert diag.skipped is True
        assert diag.executed is False
        assert diag.execution_status == "SKIPPED"
        assert "battery" in diag.missing_streams

    def test_diagnostics_when_ran(
        self,
        plugin: PayloadChangeDetectionPlugin,
        step_change_flight: Flight,
    ) -> None:
        parse_diag = _make_parse_diagnostics()
        findings, diag = plugin.forensic_analyze(
            step_change_flight,
            "EV-TEST",
            "RUN-TEST",
            {},
            parse_diag,
        )
        assert diag.executed is True
        assert diag.skipped is False
        assert diag.execution_status == "RAN"
        assert diag.missing_streams == []
        assert diag.findings_emitted == len(findings)


# ---------------------------------------------------------------------------
# Tuning profile integration
# ---------------------------------------------------------------------------


class TestTuningProfileIntegration:
    def test_plugin_in_default_tuning_profile(self) -> None:
        profile = TuningProfile.default()
        cfg = profile.get_config_for_plugin("payload_change_detection")
        assert cfg is not None
        assert cfg.thresholds is not None
        assert "current_delta_threshold" in cfg.thresholds.values
        assert "sustained_duration_s" in cfg.thresholds.values
        assert "min_flight_duration_s" in cfg.thresholds.values

    def test_default_profile_constant_contains_plugin(self) -> None:
        cfg = DEFAULT_TUNING_PROFILE.get_config_for_plugin("payload_change_detection")
        assert cfg is not None

    def test_default_thresholds_match_source(self, plugin: PayloadChangeDetectionPlugin) -> None:
        profile = TuningProfile.default()
        cfg = profile.get_config_for_plugin("payload_change_detection")
        assert cfg is not None and cfg.thresholds is not None
        values = cfg.thresholds.values
        assert values["current_delta_threshold"] == plugin.DEFAULT_CURRENT_DELTA_THRESHOLD
        assert values["sustained_duration_s"] == plugin.DEFAULT_SUSTAINED_DURATION_S
        assert values["pre_post_window_s"] == plugin.DEFAULT_PRE_POST_WINDOW_S
        assert values["command_tolerance"] == plugin.DEFAULT_COMMAND_TOLERANCE
        assert values["min_flight_duration_s"] == plugin.DEFAULT_MIN_FLIGHT_DURATION_S
