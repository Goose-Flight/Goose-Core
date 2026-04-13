"""Tests for position_tracking plugin using mock Flight objects."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata
from goose.plugins.position_tracking import PositionTrackingPlugin


def _make_metadata(duration: float = 60.0) -> FlightMetadata:
    return FlightMetadata(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.13.0",
        vehicle_type="quadcopter",
        frame_type="x500",
        hardware="Pixhawk 6C",
        duration_sec=duration,
        start_time_utc=datetime(2024, 1, 1, 12, 0, 0),
        log_format="ulog",
        motor_count=4,
    )


def _make_flight_no_setpoints() -> Flight:
    """Flight with no position setpoints."""
    n = 100
    ts = np.linspace(0, 60, n)
    pos = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": 47.3 + np.random.randn(n) * 1e-5,
            "lon": 8.5 + np.random.randn(n) * 1e-5,
            "alt_rel": 50.0 + np.random.randn(n) * 0.1,
        }
    )
    return Flight(
        metadata=_make_metadata(),
        position=pos,
        primary_mode="position",
    )


def _make_flight_good_tracking() -> Flight:
    """Flight with position setpoints and excellent tracking (error < 1m)."""
    n = 100
    ts = np.linspace(0, 60, n)
    lat_base = 47.3 + np.linspace(0, 0.001, n)
    lon_base = 8.5 + np.linspace(0, 0.001, n)
    alt_base = 50.0 + np.zeros(n)

    # Small noise so error is well below 3m
    pos = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": lat_base + np.random.randn(n) * 1e-6,
            "lon": lon_base + np.random.randn(n) * 1e-6,
            "alt_rel": alt_base + np.random.randn(n) * 0.1,
        }
    )
    sp = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": lat_base,
            "lon": lon_base,
            "alt_rel": alt_base,
        }
    )
    return Flight(
        metadata=_make_metadata(),
        position=pos,
        position_setpoint=sp,
        primary_mode="position",
    )


def _make_flight_poor_tracking() -> Flight:
    """Flight with large horizontal position errors (> 10m = critical)."""
    n = 100
    ts = np.linspace(0, 60, n)
    lat_base = 47.3 + np.zeros(n)
    lon_base = 8.5 + np.zeros(n)
    alt_base = 50.0 + np.zeros(n)

    # Offset actual position by ~0.001 degrees lat ≈ 111m — clearly critical
    pos = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": lat_base + 0.001,
            "lon": lon_base,
            "alt_rel": alt_base,
        }
    )
    sp = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": lat_base,
            "lon": lon_base,
            "alt_rel": alt_base,
        }
    )
    return Flight(
        metadata=_make_metadata(),
        position=pos,
        position_setpoint=sp,
        primary_mode="position",
    )


def _make_flight_warning_tracking() -> Flight:
    """Flight with horizontal error in warning range (3-10m)."""
    n = 100
    ts = np.linspace(0, 60, n)
    lat_base = 47.3 + np.zeros(n)
    lon_base = 8.5 + np.zeros(n)
    alt_base = 50.0 + np.zeros(n)

    # ~5m offset (0.0001 deg ≈ 11m, use smaller value for ~5m)
    pos = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": lat_base + 0.00005,  # ~5.5m
            "lon": lon_base,
            "alt_rel": alt_base,
        }
    )
    sp = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": lat_base,
            "lon": lon_base,
            "alt_rel": alt_base,
        }
    )
    return Flight(
        metadata=_make_metadata(),
        position=pos,
        position_setpoint=sp,
        primary_mode="position",
    )


@pytest.fixture
def plugin() -> PositionTrackingPlugin:
    return PositionTrackingPlugin()


class TestPositionTrackingInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: PositionTrackingPlugin) -> None:
        assert plugin.name == "position_tracking"
        assert plugin.version == "1.0.0"
        assert plugin.description

    def test_min_mode_is_position(self, plugin: PositionTrackingPlugin) -> None:
        assert plugin.min_mode == "position"

    def test_analyze_returns_list(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        result = plugin.analyze(flight, {})
        assert isinstance(result, list)

    def test_all_findings_are_finding_objects(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        findings = plugin.analyze(flight, {})
        assert all(isinstance(f, Finding) for f in findings)

    def test_plugin_name_in_all_findings(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        findings = plugin.analyze(flight, {})
        assert all(f.plugin_name == "position_tracking" for f in findings)

    def test_valid_severity_in_all_findings(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        findings = plugin.analyze(flight, {})
        valid = {"pass", "info", "warning", "critical"}
        assert all(f.severity in valid for f in findings)

    def test_applicable_position_mode(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        assert plugin.applicable(flight)

    def test_not_applicable_manual_mode(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        flight.primary_mode = "manual"
        assert not plugin.applicable(flight)


class TestPositionTrackingNoSetpoints:
    """Without setpoint data the plugin returns an info finding."""

    def test_returns_info_finding(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_no_setpoints()
        findings = plugin.analyze(flight, {})
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert findings[0].score == 50

    def test_info_finding_title_mentions_setpoint(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_no_setpoints()
        findings = plugin.analyze(flight, {})
        assert "setpoint" in findings[0].title.lower()


class TestPositionTrackingGoodFlight:
    """Good tracking should produce pass findings."""

    def test_produces_at_least_one_finding(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        findings = plugin.analyze(flight, {})
        assert len(findings) >= 1

    def test_no_critical_findings(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        findings = plugin.analyze(flight, {})
        critical = [f for f in findings if f.severity == "critical"]
        assert len(critical) == 0, f"Unexpected critical: {[f.title for f in critical]}"

    def test_horizontal_finding_is_pass(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_good_tracking()
        findings = plugin.analyze(flight, {})
        horiz = [f for f in findings if "horizontal" in f.title.lower()]
        assert horiz, "Expected a horizontal position finding"
        assert horiz[0].severity == "pass"
        assert horiz[0].score >= 90


class TestPositionTrackingPoorFlight:
    """Large errors should produce critical findings."""

    def test_produces_findings(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_poor_tracking()
        findings = plugin.analyze(flight, {})
        assert len(findings) >= 1

    def test_horizontal_finding_is_critical(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_poor_tracking()
        findings = plugin.analyze(flight, {})
        horiz = [f for f in findings if "horizontal" in f.title.lower()]
        assert horiz, "Expected a horizontal position finding"
        assert horiz[0].severity == "critical"
        assert horiz[0].score <= 20

    def test_evidence_contains_error_metrics(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_poor_tracking()
        findings = plugin.analyze(flight, {})
        horiz = [f for f in findings if "horizontal" in f.title.lower()]
        assert horiz
        ev = horiz[0].evidence
        assert "mean_error_m" in ev
        assert "max_error_m" in ev
        assert ev["mean_error_m"] > 10.0  # expect > critical threshold


class TestPositionTrackingWarningFlight:
    """Moderate errors should produce warning findings."""

    def test_horizontal_finding_is_warning(self, plugin: PositionTrackingPlugin) -> None:
        flight = _make_flight_warning_tracking()
        findings = plugin.analyze(flight, {})
        horiz = [f for f in findings if "horizontal" in f.title.lower()]
        assert horiz, "Expected a horizontal position finding"
        assert horiz[0].severity == "warning"
