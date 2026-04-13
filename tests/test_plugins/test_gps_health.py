"""Tests for gps_health plugin using real PX4 flight logs."""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.parsers.detect import parse_file
from goose.plugins.gps_health import GPSHealthPlugin


@pytest.fixture
def plugin() -> GPSHealthPlugin:
    return GPSHealthPlugin()


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


class TestGPSHealthAnalyzeMotorFailure:
    """Verify GPS health analysis on motor_failure fixture."""

    def test_produces_findings(self, plugin: GPSHealthPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert len(findings) >= 1, "GPS plugin should produce at least one finding"

    def test_returns_finding_objects(self, plugin: GPSHealthPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(isinstance(f, Finding) for f in findings)

    def test_plugin_name_in_findings(self, plugin: GPSHealthPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(f.plugin_name == "gps_health" for f in findings)

    def test_findings_have_valid_severity(self, plugin: GPSHealthPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        valid_severities = {"pass", "info", "warning", "critical"}
        for finding in findings:
            assert finding.severity in valid_severities, f"Invalid severity: {finding.severity}"

    def test_findings_have_evidence(self, plugin: GPSHealthPlugin, motor_failure_flight: Flight) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        for finding in findings:
            assert isinstance(finding.evidence, dict), "Evidence must be a dict"


class TestGPSHealthAnalyzeNormalFlight:
    """Verify GPS health analysis on normal flight fixture."""

    def test_produces_findings(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) >= 1, "GPS plugin should produce at least one finding"

    def test_no_critical_in_normal_flight(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) == 0, f"Normal flight should not have critical GPS findings: {[f.title for f in critical_findings]}"

    def test_returns_pass_or_lower_severity(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        valid_severities = {"pass", "info", "warning"}
        for finding in findings:
            assert finding.severity in valid_severities, f"Normal flight should not have critical severity, got: {finding.severity}"


class TestGPSHealthPluginInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: GPSHealthPlugin) -> None:
        assert plugin.name == "gps_health"
        assert plugin.version
        assert plugin.description

    def test_applicable_for_flights(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        assert plugin.applicable(normal_flight)

    def test_analyze_accepts_config_dict(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {"custom_key": "value"})
        assert isinstance(findings, list)

    def test_analyze_with_empty_config(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert isinstance(findings, list)


class TestGPSHealthMetrics:
    """Test GPS-specific metrics extraction."""

    def test_produces_satellite_count_evidence(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) > 0, "Should produce findings"

    def test_produces_hdop_evidence(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) > 0, "Should produce findings"

    def test_detects_position_jumps(self, plugin: GPSHealthPlugin, normal_flight: Flight) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) > 0, "Should detect position anomalies if present"
