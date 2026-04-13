"""Tests for failsafe_events plugin using mock Flight objects."""

from __future__ import annotations

from datetime import datetime

import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightEvent, FlightMetadata, ModeChange
from goose.plugins.failsafe_events import FailsafeEventsPlugin


def _make_metadata() -> FlightMetadata:
    return FlightMetadata(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.13.0",
        vehicle_type="quadcopter",
        frame_type="x500",
        hardware="Pixhawk 6C",
        duration_sec=120.0,
        start_time_utc=datetime(2024, 1, 1, 12, 0, 0),
        log_format="ulog",
        motor_count=4,
    )


def _make_clean_flight() -> Flight:
    """Flight with no failsafes or emergency transitions."""
    return Flight(
        metadata=_make_metadata(),
        events=[
            FlightEvent(5.0, "info", "info", "ARM"),
            FlightEvent(10.0, "info", "info", "Takeoff"),
            FlightEvent(115.0, "info", "info", "Land"),
        ],
        mode_changes=[
            ModeChange(5.0, "manual", "position"),
            ModeChange(115.0, "position", "manual"),
        ],
        primary_mode="manual",
    )


def _make_flight_one_noncritical_failsafe() -> Flight:
    """Flight with a single non-critical failsafe event."""
    return Flight(
        metadata=_make_metadata(),
        events=[
            FlightEvent(5.0, "info", "info", "ARM"),
            FlightEvent(60.0, "failsafe", "warning", "RC signal lost briefly"),
            FlightEvent(115.0, "info", "info", "Land"),
        ],
        mode_changes=[
            ModeChange(5.0, "manual", "position"),
            ModeChange(60.0, "position", "loiter"),
            ModeChange(115.0, "loiter", "manual"),
        ],
        primary_mode="manual",
    )


def _make_flight_critical_failsafe() -> Flight:
    """Flight with a critical failsafe event."""
    return Flight(
        metadata=_make_metadata(),
        events=[
            FlightEvent(5.0, "info", "info", "ARM"),
            FlightEvent(60.0, "failsafe", "critical", "Battery critical — failsafe triggered"),
            FlightEvent(62.0, "info", "info", "Auto-landing initiated"),
        ],
        mode_changes=[
            ModeChange(5.0, "manual", "position"),
            ModeChange(60.0, "position", "land"),
        ],
        primary_mode="manual",
    )


def _make_flight_multiple_failsafes() -> Flight:
    """Flight with multiple failsafe events."""
    return Flight(
        metadata=_make_metadata(),
        events=[
            FlightEvent(5.0, "info", "info", "ARM"),
            FlightEvent(30.0, "failsafe", "warning", "RC link degraded"),
            FlightEvent(60.0, "failsafe", "critical", "GPS lost"),
            FlightEvent(90.0, "failsafe", "critical", "Battery low failsafe"),
        ],
        mode_changes=[
            ModeChange(5.0, "manual", "position"),
            ModeChange(60.0, "position", "rtl"),
            ModeChange(90.0, "rtl", "land"),
        ],
        primary_mode="manual",
    )


def _make_flight_emergency_transitions() -> Flight:
    """Flight with emergency mode transitions but no failsafe events."""
    return Flight(
        metadata=_make_metadata(),
        events=[
            FlightEvent(5.0, "info", "info", "ARM"),
            FlightEvent(60.0, "info", "info", "Mode change"),
        ],
        mode_changes=[
            ModeChange(5.0, "manual", "position"),
            ModeChange(60.0, "position", "rtl"),
        ],
        primary_mode="manual",
    )


@pytest.fixture
def plugin() -> FailsafeEventsPlugin:
    return FailsafeEventsPlugin()


class TestFailsafeEventsInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: FailsafeEventsPlugin) -> None:
        assert plugin.name == "failsafe_events"
        assert plugin.version == "1.0.0"
        assert plugin.description

    def test_min_mode_is_manual(self, plugin: FailsafeEventsPlugin) -> None:
        assert plugin.min_mode == "manual"

    def test_analyze_returns_list(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        result = plugin.analyze(flight, {})
        assert isinstance(result, list)

    def test_all_findings_are_finding_objects(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        findings = plugin.analyze(flight, {})
        assert all(isinstance(f, Finding) for f in findings)

    def test_plugin_name_in_all_findings(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        findings = plugin.analyze(flight, {})
        assert all(f.plugin_name == "failsafe_events" for f in findings)

    def test_valid_severity_in_all_findings(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        findings = plugin.analyze(flight, {})
        valid = {"pass", "info", "warning", "critical"}
        assert all(f.severity in valid for f in findings)

    def test_applicable_for_manual_mode(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        assert plugin.applicable(flight)


class TestFailsafeEventsCleanFlight:
    """Clean flight with no failsafes should produce a pass finding."""

    def test_produces_finding(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        findings = plugin.analyze(flight, {})
        assert len(findings) >= 1

    def test_finding_is_pass(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        findings = plugin.analyze(flight, {})
        assert findings[0].severity == "pass"
        assert findings[0].score == 100

    def test_finding_title_no_failsafe(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        findings = plugin.analyze(flight, {})
        assert "no failsafe" in findings[0].title.lower()

    def test_evidence_has_zero_count(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_clean_flight()
        findings = plugin.analyze(flight, {})
        assert findings[0].evidence["failsafe_count"] == 0


class TestFailsafeEventsOneFlight:
    """Single non-critical failsafe should score 80 with warning severity."""

    def test_produces_findings(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_one_noncritical_failsafe()
        findings = plugin.analyze(flight, {})
        assert len(findings) >= 1

    def test_summary_finding_is_warning(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_one_noncritical_failsafe()
        findings = plugin.analyze(flight, {})
        summary = findings[0]
        assert summary.severity in ("warning", "critical")

    def test_individual_event_finding_present(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_one_noncritical_failsafe()
        findings = plugin.analyze(flight, {})
        # Expect summary + individual event finding
        assert len(findings) >= 2

    def test_individual_finding_has_timestamp(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_one_noncritical_failsafe()
        findings = plugin.analyze(flight, {})
        event_findings = [f for f in findings if f.timestamp_start is not None]
        assert event_findings


class TestFailsafeEventsCritical:
    """Critical failsafe event."""

    def test_summary_score_is_low(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_critical_failsafe()
        findings = plugin.analyze(flight, {})
        assert findings[0].score <= 60

    def test_emergency_transition_detected(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_critical_failsafe()
        findings = plugin.analyze(flight, {})
        transition_findings = [f for f in findings if "transition" in f.title.lower()]
        assert len(transition_findings) >= 1

    def test_evidence_failsafe_count(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_critical_failsafe()
        findings = plugin.analyze(flight, {})
        summary = findings[0]
        assert summary.evidence["failsafe_count"] >= 1


class TestFailsafeEventsMultiple:
    """Multiple failsafes should score lowest."""

    def test_score_is_low(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_multiple_failsafes()
        findings = plugin.analyze(flight, {})
        assert findings[0].score <= 30

    def test_severity_is_critical(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_multiple_failsafes()
        findings = plugin.analyze(flight, {})
        assert findings[0].severity == "critical"

    def test_multiple_individual_findings(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_multiple_failsafes()
        findings = plugin.analyze(flight, {})
        # Summary + 3 events + 2 emergency transitions = at least 4
        assert len(findings) >= 4


class TestFailsafeEventsEmergencyTransitions:
    """Emergency mode transitions without explicit failsafe events."""

    def test_detects_rtl_transition(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_emergency_transitions()
        findings = plugin.analyze(flight, {})
        transition_findings = [f for f in findings if "transition" in f.title.lower()]
        assert len(transition_findings) >= 1

    def test_transition_finding_mentions_rtl(self, plugin: FailsafeEventsPlugin) -> None:
        flight = _make_flight_emergency_transitions()
        findings = plugin.analyze(flight, {})
        rtl_findings = [f for f in findings if "rtl" in f.title.lower()]
        assert len(rtl_findings) >= 1
