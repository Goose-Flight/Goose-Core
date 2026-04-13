"""Tests for crash_detection plugin using real PX4 flight logs."""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.parsers.detect import parse_file
from goose.plugins.crash_detection import CrashDetectionPlugin


@pytest.fixture
def plugin() -> CrashDetectionPlugin:
    return CrashDetectionPlugin()


@pytest.fixture
def motor_failure_flight(motor_failure_path: Path) -> Flight:
    result = parse_file(motor_failure_path)
    assert result.flight is not None
    return result.flight


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


class TestCrashDetectionVibrationCrash:
    """Verify crash detected in vibration_crash fixture (abrupt ~1s flight)."""

    def test_detects_crash(self, plugin: CrashDetectionPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert len(crash_findings) >= 1, f"Expected crash finding, got: {[f.title for f in findings]}"

    def test_crash_severity_is_critical_or_warning(self, plugin: CrashDetectionPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert crash_findings, "No crash finding produced"
        for f in crash_findings:
            assert f.severity in ("critical", "warning")

    def test_crash_has_classification(self, plugin: CrashDetectionPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert crash_findings, "No crash finding produced"
        crash = crash_findings[0]
        assert "crash_type" in crash.evidence
        assert crash.evidence["crash_type"] in (
            "motor_failure",
            "power_loss",
            "gps_loss",
            "pilot_error",
            "mechanical",
            "unknown",
        )

    def test_crash_has_confidence(self, plugin: CrashDetectionPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert crash_findings, "No crash finding produced"
        confidence = crash_findings[0].evidence["confidence"]
        assert 0.0 <= confidence <= 1.0

    def test_crash_has_timeline(self, plugin: CrashDetectionPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert crash_findings, "No crash finding produced"
        timeline = crash_findings[0].evidence["timeline"]
        assert isinstance(timeline, list)

    def test_crash_has_root_cause_chain(self, plugin: CrashDetectionPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert crash_findings, "No crash finding produced"
        chain = crash_findings[0].evidence["root_cause_chain"]
        assert isinstance(chain, list)
        assert len(chain) >= 1

    def test_crash_score_is_low(self, plugin: CrashDetectionPlugin, vibration_crash_flight: Flight) -> None:
        findings = plugin.analyze(vibration_crash_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert crash_findings, "No crash finding produced"
        assert crash_findings[0].score <= 50


class TestCrashDetectionMotorFailure:
    """Verify crash detection on motor_failure fixture (ground test, motors never armed)."""

    def test_produces_findings(self, plugin: CrashDetectionPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert len(findings) >= 1

    def test_returns_finding_objects(self, plugin: CrashDetectionPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(isinstance(f, Finding) for f in findings)

    def test_plugin_name_in_findings(self, plugin: CrashDetectionPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(f.plugin_name == "crash_detection" for f in findings)


class TestCrashDetectionNormalFlight:
    """Verify no crash detected in normal flight fixture."""

    def test_no_crash_detected(self, plugin: CrashDetectionPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        crash_findings = [f for f in findings if f.title.lower().startswith("crash detected")]
        assert len(crash_findings) == 0, f"False positive crash detected: {[f.title for f in crash_findings]}"

    def test_pass_finding_returned(self, plugin: CrashDetectionPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        pass_findings = [f for f in findings if f.severity == "pass"]
        assert len(pass_findings) >= 1, f"Expected pass finding for normal flight, got: {[f.title for f in findings]}"

    def test_pass_score_is_high(self, plugin: CrashDetectionPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        pass_findings = [f for f in findings if f.severity == "pass"]
        assert pass_findings, "No pass finding"
        assert pass_findings[0].score >= 90


class TestCrashDetectionPluginInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: CrashDetectionPlugin) -> None:
        assert plugin.name == "crash_detection"
        assert plugin.version
        assert plugin.description

    def test_applicable_for_manual_mode(self, plugin: CrashDetectionPlugin, normal_flight: Flight) -> None:
        assert plugin.applicable(normal_flight)

    def test_returns_finding_objects(self, plugin: CrashDetectionPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert all(isinstance(f, Finding) for f in findings)
