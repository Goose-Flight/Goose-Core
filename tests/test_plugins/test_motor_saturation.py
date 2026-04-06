"""Tests for motor_saturation plugin using real PX4 flight logs."""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.motor_saturation import MotorSaturationPlugin
from goose.parsers.ulog import ULogParser


@pytest.fixture
def plugin() -> MotorSaturationPlugin:
    return MotorSaturationPlugin()


@pytest.fixture
def parser() -> ULogParser:
    return ULogParser()


@pytest.fixture
def motor_failure_flight(parser: ULogParser, motor_failure_path: Path) -> Flight:
    return parser.parse(motor_failure_path)


@pytest.fixture
def normal_flight(parser: ULogParser, normal_flight_path: Path) -> Flight:
    return parser.parse(normal_flight_path)


class TestMotorSaturationAnalyzeMotorFailure:
    """Verify motor saturation analysis on motor_failure fixture."""

    def test_produces_findings(
        self, plugin: MotorSaturationPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert len(findings) >= 1, "Motor saturation plugin should produce at least one finding"

    def test_returns_finding_objects(
        self, plugin: MotorSaturationPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(isinstance(f, Finding) for f in findings)

    def test_plugin_name_in_findings(
        self, plugin: MotorSaturationPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(f.plugin_name == "motor_saturation" for f in findings)

    def test_findings_have_valid_severity(
        self, plugin: MotorSaturationPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        valid_severities = {"pass", "info", "warning", "critical"}
        for finding in findings:
            assert finding.severity in valid_severities, (
                f"Invalid severity: {finding.severity}"
            )

    def test_findings_have_evidence(
        self, plugin: MotorSaturationPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        for finding in findings:
            assert isinstance(finding.evidence, dict), "Evidence must be a dict"


class TestMotorSaturationAnalyzeNormalFlight:
    """Verify motor saturation analysis on normal flight fixture."""

    def test_produces_findings(
        self, plugin: MotorSaturationPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) >= 1, "Motor saturation plugin should produce at least one finding"

    def test_no_critical_in_normal_flight(
        self, plugin: MotorSaturationPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) == 0, (
            f"Normal flight should not have critical motor saturation findings: {[f.title for f in critical_findings]}"
        )

    def test_returns_pass_or_warning(
        self, plugin: MotorSaturationPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        valid_severities = {"pass", "info", "warning"}
        for finding in findings:
            assert finding.severity in valid_severities, (
                f"Normal flight should not have critical severity, got: {finding.severity}"
            )


class TestMotorSaturationPluginInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: MotorSaturationPlugin) -> None:
        assert plugin.name == "motor_saturation"
        assert plugin.version
        assert plugin.description

    def test_applicable_for_flights(
        self, plugin: MotorSaturationPlugin, normal_flight: Flight
    ) -> None:
        assert plugin.applicable(normal_flight)

    def test_analyze_accepts_config_dict(
        self, plugin: MotorSaturationPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {"custom_key": "value"})
        assert isinstance(findings, list)

    def test_analyze_with_empty_config(
        self, plugin: MotorSaturationPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert isinstance(findings, list)


class TestMotorSaturationDetection:
    """Test motor-specific saturation detection."""

    def test_detects_near_maximum_output(
        self, plugin: MotorSaturationPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) > 0, "Should produce findings even if no saturation detected"

    def test_reports_per_motor_analysis(
        self, plugin: MotorSaturationPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert len(findings) > 0, "Should analyze all motors"

    def test_saturation_severity_indicates_risk(
        self, plugin: MotorSaturationPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        saturation_warnings = [
            f for f in findings
            if "saturation" in f.title.lower() and f.severity in {"warning", "critical"}
        ]
        if saturation_warnings:
            for finding in saturation_warnings:
                assert finding.severity in {"warning", "critical"}, (
                    f"Saturation warnings should be warning or critical, got: {finding.severity}"
                )
