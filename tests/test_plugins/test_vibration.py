"""Tests for vibration plugin using real PX4 flight logs."""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.parsers.detect import parse_file
from goose.plugins.vibration import VibrationPlugin


@pytest.fixture
def plugin() -> VibrationPlugin:
    return VibrationPlugin()


@pytest.fixture
def normal_flight(normal_flight_path: Path) -> Flight:
    result = parse_file(normal_flight_path)
    assert result.flight is not None
    return result.flight


@pytest.fixture
def vibration_crash_flight(vibration_crash_path: Path) -> Flight:
    result = parse_file(vibration_crash_path)
    assert result.flight is not None
    return result.flight


@pytest.fixture
def motor_failure_flight(motor_failure_path: Path) -> Flight:
    result = parse_file(motor_failure_path)
    assert result.flight is not None
    return result.flight


class TestVibrationNormalFlight:
    """Verify vibration levels correctly classified for normal flight."""

    def test_produces_findings(self, plugin: VibrationPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) >= 1

    def test_overall_classification_not_missing(self, plugin: VibrationPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        overall = findings[0]
        assert overall.severity in ("pass", "warning", "critical", "info")

    def test_has_axis_evidence(self, plugin: VibrationPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        overall = findings[0]
        if overall.evidence:
            axes = overall.evidence.get("axes", {})
            assert len(axes) >= 2, f"Expected axis data, got: {axes}"
            for axis_data in axes.values():
                assert "rms_ms2" in axis_data
                assert "peak_ms2" in axis_data
                assert "classification" in axis_data
                assert axis_data["classification"] in ("good", "warning", "bad")


class TestVibrationCrashFlight:
    """Verify vibration analysis runs on vibration_crash fixture."""

    def test_produces_findings(self, plugin: VibrationPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        assert len(findings) >= 1

    def test_classification_valid(self, plugin: VibrationPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        overall = findings[0]
        assert overall.severity in ("pass", "warning", "critical", "info")

    def test_has_axis_evidence(self, plugin: VibrationPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        overall = findings[0]
        if overall.evidence and "axes" in overall.evidence:
            for _axis, data in overall.evidence["axes"].items():
                assert "rms_ms2" in data
                assert "classification" in data


class TestVibrationMotorFailure:
    """Verify vibration analysis handles motor failure logs."""

    def test_produces_findings(self, plugin: VibrationPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert len(findings) >= 1

    def test_returns_finding_objects(self, plugin: VibrationPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(isinstance(f, Finding) for f in findings)


class TestVibrationPluginInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: VibrationPlugin) -> None:
        assert plugin.name == "vibration"
        assert plugin.version
        assert plugin.description

    def test_applicable_for_manual_mode(self, plugin: VibrationPlugin, normal_flight: Flight) -> None:
        assert plugin.applicable(normal_flight)

    def test_rms_and_peak_are_positive(self, plugin: VibrationPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        overall = findings[0]
        if overall.evidence and "axes" in overall.evidence:
            for _axis, data in overall.evidence["axes"].items():
                assert data["rms_ms2"] >= 0
                assert data["peak_ms2"] >= 0
