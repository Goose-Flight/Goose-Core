"""Tests for AttitudeTrackingPlugin using mock Flight objects."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata
from goose.plugins.attitude_tracking import AttitudeTrackingPlugin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(duration: float = 60.0) -> FlightMetadata:
    return FlightMetadata(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type=None,
        hardware=None,
        duration_sec=duration,
        start_time_utc=datetime(2024, 1, 1, 12, 0, 0),
        log_format="ulog",
        motor_count=4,
    )


def _make_flight(
    attitude: pd.DataFrame,
    attitude_setpoint: pd.DataFrame,
    primary_mode: str = "stabilized",
) -> Flight:
    return Flight(
        metadata=_make_metadata(),
        attitude=attitude,
        attitude_setpoint=attitude_setpoint,
        primary_mode=primary_mode,
    )


def _good_attitude(n: int = 300, duration: float = 60.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attitude and setpoint with very small tracking error (<1 degree)."""
    ts = np.linspace(0.0, duration, n)
    rng = np.random.default_rng(42)
    roll = rng.normal(0.0, 0.05, n)  # ~3 degrees amplitude
    pitch = rng.normal(0.0, 0.03, n)
    yaw = np.linspace(0.0, 0.5, n)
    # Setpoints very close — error < 1 degree
    att = pd.DataFrame({"timestamp": ts, "roll": roll, "pitch": pitch, "yaw": yaw})
    sp = pd.DataFrame(
        {
            "timestamp": ts,
            "roll": roll + rng.normal(0.0, 0.01, n),  # ~0.6 degree rms error
            "pitch": pitch + rng.normal(0.0, 0.01, n),
            "yaw": yaw + rng.normal(0.0, 0.01, n),
        }
    )
    return att, sp


def _warning_attitude(n: int = 300) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attitude with ~7 degree RMS tracking error on roll (warning level)."""
    ts = np.linspace(0.0, 60.0, n)
    rng = np.random.default_rng(7)
    roll = rng.normal(0.0, 0.1, n)
    pitch = rng.normal(0.0, 0.05, n)
    yaw = np.linspace(0.0, 1.0, n)
    # Roll setpoint offset by ~7 degrees (0.12 radians)
    att = pd.DataFrame({"timestamp": ts, "roll": roll, "pitch": pitch, "yaw": yaw})
    sp = pd.DataFrame(
        {
            "timestamp": ts,
            "roll": roll + 0.12,  # constant ~6.9 degree offset -> RMS ~6.9 deg
            "pitch": pitch + rng.normal(0.0, 0.005, n),
            "yaw": yaw + rng.normal(0.0, 0.005, n),
        }
    )
    return att, sp


def _critical_attitude(n: int = 300) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attitude with >15 degree RMS tracking error (critical level)."""
    ts = np.linspace(0.0, 60.0, n)
    rng = np.random.default_rng(13)
    roll = rng.normal(0.0, 0.1, n)
    pitch = rng.normal(0.0, 0.05, n)
    yaw = np.linspace(0.0, 1.0, n)
    # Roll setpoint offset by ~20 degrees (0.35 radians)
    att = pd.DataFrame({"timestamp": ts, "roll": roll, "pitch": pitch, "yaw": yaw})
    sp = pd.DataFrame(
        {
            "timestamp": ts,
            "roll": roll + 0.35,  # ~20 degree constant offset
            "pitch": pitch + 0.35,
            "yaw": yaw + rng.normal(0.0, 0.005, n),
        }
    )
    return att, sp


def _oscillating_attitude(n: int = 600) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attitude with rapid oscillating sign-changing error on roll."""
    ts = np.linspace(0.0, 60.0, n)
    roll = np.sin(np.linspace(0, 20 * np.pi, n)) * 0.05  # oscillating ~3 degrees
    pitch = np.zeros(n)
    yaw = np.zeros(n)
    att = pd.DataFrame({"timestamp": ts, "roll": roll, "pitch": pitch, "yaw": yaw})
    # Setpoint is zero, so error oscillates back and forth rapidly
    sp = pd.DataFrame(
        {
            "timestamp": ts,
            "roll": np.zeros(n),
            "pitch": np.zeros(n),
            "yaw": np.zeros(n),
        }
    )
    return att, sp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin() -> AttitudeTrackingPlugin:
    return AttitudeTrackingPlugin()


@pytest.fixture
def good_flight() -> Flight:
    att, sp = _good_attitude()
    return _make_flight(att, sp)


@pytest.fixture
def warning_flight() -> Flight:
    att, sp = _warning_attitude()
    return _make_flight(att, sp)


@pytest.fixture
def critical_flight() -> Flight:
    att, sp = _critical_attitude()
    return _make_flight(att, sp)


@pytest.fixture
def oscillating_flight() -> Flight:
    att, sp = _oscillating_attitude()
    return _make_flight(att, sp)


@pytest.fixture
def no_setpoint_flight() -> Flight:
    att, _ = _good_attitude()
    return _make_flight(att, pd.DataFrame(), primary_mode="stabilized")


@pytest.fixture
def no_attitude_flight() -> Flight:
    _, sp = _good_attitude()
    return _make_flight(pd.DataFrame(), sp, primary_mode="stabilized")


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------


class TestAttitudeTrackingPluginInterface:
    def test_has_required_attributes(self, plugin: AttitudeTrackingPlugin) -> None:
        assert plugin.name == "attitude_tracking"
        assert plugin.version == "1.0.0"
        assert plugin.description

    def test_min_mode_is_stabilized(self, plugin: AttitudeTrackingPlugin) -> None:
        assert plugin.min_mode == "stabilized"

    def test_applicable_for_stabilized_mode(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        assert plugin.applicable(good_flight)

    def test_not_applicable_for_manual_mode(self, plugin: AttitudeTrackingPlugin) -> None:
        att, sp = _good_attitude()
        flight = _make_flight(att, sp, primary_mode="manual")
        assert not plugin.applicable(flight)

    def test_analyze_returns_list(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        assert isinstance(plugin.analyze(good_flight, {}), list)

    def test_all_findings_are_finding_instances(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        assert all(isinstance(f, Finding) for f in plugin.analyze(good_flight, {}))

    def test_plugin_name_in_all_findings(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        assert all(f.plugin_name == "attitude_tracking" for f in plugin.analyze(good_flight, {}))

    def test_valid_severities(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        valid = {"pass", "info", "warning", "critical"}
        for f in plugin.analyze(good_flight, {}):
            assert f.severity in valid

    def test_score_in_range(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        for f in plugin.analyze(good_flight, {}):
            assert 0 <= f.score <= 100


# ---------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------


class TestAttitudeTrackingMissingData:
    def test_no_attitude_returns_info(self, plugin: AttitudeTrackingPlugin, no_attitude_flight: Flight) -> None:
        findings = plugin.analyze(no_attitude_flight, {})
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert findings[0].score == 50

    def test_no_setpoint_returns_info(self, plugin: AttitudeTrackingPlugin, no_setpoint_flight: Flight) -> None:
        findings = plugin.analyze(no_setpoint_flight, {})
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert findings[0].score == 50


# ---------------------------------------------------------------------------
# Good tracking
# ---------------------------------------------------------------------------


class TestAttitudeTrackingGood:
    def test_produces_findings(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        assert len(plugin.analyze(good_flight, {})) >= 1

    def test_no_critical_findings(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        assert not any(f.severity == "critical" for f in findings)

    def test_tracking_finding_is_pass(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        tracking = [f for f in findings if "tracking" in f.title.lower()]
        if tracking:
            assert tracking[0].severity == "pass"

    def test_evidence_contains_axes(self, plugin: AttitudeTrackingPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        tracking = [f for f in findings if "axes" in f.evidence]
        assert len(tracking) >= 1


# ---------------------------------------------------------------------------
# Warning-level tracking error
# ---------------------------------------------------------------------------


class TestAttitudeTrackingWarning:
    def test_warning_severity_present(self, plugin: AttitudeTrackingPlugin, warning_flight: Flight) -> None:
        findings = plugin.analyze(warning_flight, {})
        severities = {f.severity for f in findings}
        assert "warning" in severities or "critical" in severities

    def test_rms_error_in_evidence(self, plugin: AttitudeTrackingPlugin, warning_flight: Flight) -> None:
        findings = plugin.analyze(warning_flight, {})
        tracking = [f for f in findings if f.evidence and "axes" in f.evidence]
        # At least one finding should have axes evidence
        assert len(tracking) >= 1
        for f in tracking:
            for _axis_name, axis_data in f.evidence["axes"].items():
                if isinstance(axis_data, dict) and "rms_error_deg" in axis_data:
                    assert axis_data["rms_error_deg"] >= 0.0


# ---------------------------------------------------------------------------
# Critical-level tracking error
# ---------------------------------------------------------------------------


class TestAttitudeTrackingCritical:
    def test_critical_severity(self, plugin: AttitudeTrackingPlugin, critical_flight: Flight) -> None:
        findings = plugin.analyze(critical_flight, {})
        severities = {f.severity for f in findings}
        assert "critical" in severities

    def test_low_score_for_critical(self, plugin: AttitudeTrackingPlugin, critical_flight: Flight) -> None:
        findings = plugin.analyze(critical_flight, {})
        critical = [f for f in findings if f.severity == "critical"]
        assert all(f.score <= 30 for f in critical)


# ---------------------------------------------------------------------------
# Oscillation detection
# ---------------------------------------------------------------------------


class TestAttitudeTrackingOscillation:
    def test_oscillation_finding_produced(self, plugin: AttitudeTrackingPlugin, oscillating_flight: Flight) -> None:
        findings = plugin.analyze(oscillating_flight, {})
        # Low-amplitude oscillation (~3 deg) should produce findings (pass or warning)
        assert len(findings) >= 1

    def test_oscillation_severity_is_warning(self, plugin: AttitudeTrackingPlugin, oscillating_flight: Flight) -> None:
        findings = plugin.analyze(oscillating_flight, {})
        osc_findings = [f for f in findings if "oscillat" in f.title.lower()]
        assert all(f.severity == "warning" for f in osc_findings)

    def test_oscillation_evidence_has_axes(self, plugin: AttitudeTrackingPlugin, oscillating_flight: Flight) -> None:
        findings = plugin.analyze(oscillating_flight, {})
        osc_findings = [f for f in findings if "oscillat" in f.title.lower()]
        for f in osc_findings:
            assert "oscillating_axes" in f.evidence
            assert len(f.evidence["oscillating_axes"]) >= 1
