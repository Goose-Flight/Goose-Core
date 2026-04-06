"""Tests for battery_sag plugin using real PX4 flight logs."""

from __future__ import annotations

from pathlib import Path

import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.battery_sag import BatterySagPlugin
from goose.parsers.ulog import ULogParser


@pytest.fixture
def plugin() -> BatterySagPlugin:
    return BatterySagPlugin()


@pytest.fixture
def parser() -> ULogParser:
    return ULogParser()


@pytest.fixture
def motor_failure_flight(parser: ULogParser, motor_failure_path: Path) -> Flight:
    return parser.parse(motor_failure_path)


@pytest.fixture
def normal_flight(parser: ULogParser, normal_flight_path: Path) -> Flight:
    return parser.parse(normal_flight_path)


class TestBatterySagAnalyzeMotorFailure:
    """Verify battery sag analysis on motor_failure fixture."""

    def test_produces_findings(
        self, plugin: BatterySagPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert len(findings) >= 1, "Battery plugin should produce at least one finding"

    def test_returns_finding_objects(
        self, plugin: BatterySagPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(isinstance(f, Finding) for f in findings)

    def test_plugin_name_in_findings(
        self, plugin: BatterySagPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        assert all(f.plugin_name == "battery_sag" for f in findings)

    def test_findings_have_valid_severity(
        self, plugin: BatterySagPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        valid_severities = {"pass", "info", "warning", "critical"}
        for finding in findings:
            assert finding.severity in valid_severities, (
                f"Invalid severity: {finding.severity}"
            )

    def test_findings_have_evidence(
        self, plugin: BatterySagPlugin, motor_failure_flight: Flight
    ) -> None:
        findings = plugin.analyze(motor_failure_flight, {})
        for finding in findings:
            assert isinstance(finding.evidence, dict), "Evidence must be a dict"


class TestBatterySagAnalyzeNormalFlight:
    """Verify battery sag analysis on normal flight fixture."""

    def test_produces_findings(
        self, plugin: BatterySagPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert len(findings) >= 1, "Battery plugin should produce at least one finding"

    def test_no_critical_in_normal_flight(
        self, plugin: BatterySagPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) == 0, (
            f"Normal flight should not have critical battery findings: {[f.title for f in critical_findings]}"
        )

    def test_returns_pass_or_warning(
        self, plugin: BatterySagPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        valid_severities = {"pass", "info", "warning"}
        for finding in findings:
            assert finding.severity in valid_severities, (
                f"Normal flight should not have critical severity, got: {finding.severity}"
            )


class TestBatterySagPluginInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: BatterySagPlugin) -> None:
        assert plugin.name == "battery_sag"
        assert plugin.version
        assert plugin.description

    def test_applicable_for_flights(
        self, plugin: BatterySagPlugin, normal_flight: Flight
    ) -> None:
        assert plugin.applicable(normal_flight)

    def test_analyze_accepts_config_dict(
        self, plugin: BatterySagPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {"custom_key": "value"})
        assert isinstance(findings, list)

    def test_analyze_with_empty_config(
        self, plugin: BatterySagPlugin, normal_flight: Flight
    ) -> None:
        findings = plugin.analyze(normal_flight, {})
        assert isinstance(findings, list)
