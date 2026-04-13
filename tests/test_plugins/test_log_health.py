"""Tests for log_health plugin using mock Flight objects."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata
from goose.plugins.log_health import LogHealthPlugin


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


def _make_dense_stream(n: int = 600, duration: float = 60.0) -> pd.DataFrame:
    """Create a dense DataFrame with timestamp and dummy data."""
    ts = np.linspace(0, duration, n)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "value": np.random.randn(n),
        }
    )


def _make_flight_all_streams() -> Flight:
    """Flight with all key data streams populated and consistent duration."""
    duration = 60.0
    pos = _make_dense_stream(600, duration)
    # Add position-specific columns
    pos["lat"] = 47.3
    pos["lon"] = 8.5
    pos["alt_rel"] = 50.0

    att = _make_dense_stream(600, duration)
    bat = _make_dense_stream(60, duration)
    gps = _make_dense_stream(60, duration)
    mot = _make_dense_stream(600, duration)

    return Flight(
        metadata=_make_metadata(duration),
        position=pos,
        attitude=att,
        battery=bat,
        gps=gps,
        motors=mot,
        primary_mode="manual",
    )


def _make_flight_no_streams() -> Flight:
    """Flight with all key data streams empty."""
    return Flight(
        metadata=_make_metadata(),
        primary_mode="manual",
    )


def _make_flight_missing_battery() -> Flight:
    """Flight with battery data missing."""
    duration = 60.0
    pos = _make_dense_stream(600, duration)
    att = _make_dense_stream(600, duration)
    gps = _make_dense_stream(60, duration)
    mot = _make_dense_stream(600, duration)

    return Flight(
        metadata=_make_metadata(duration),
        position=pos,
        attitude=att,
        gps=gps,
        motors=mot,
        primary_mode="manual",
    )


def _make_flight_with_dropout() -> Flight:
    """Flight with a data dropout in the position stream."""
    duration = 60.0

    # Normal dense data from 0-25s, then jump to 30s (5s gap), then 30-60s
    ts_before = np.linspace(0, 25, 250)
    ts_after = np.linspace(30, 60, 300)
    ts = np.concatenate([ts_before, ts_after])

    pos = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": 47.3 + np.random.randn(len(ts)) * 1e-6,
            "lon": 8.5 + np.random.randn(len(ts)) * 1e-6,
            "alt_rel": 50.0 + np.random.randn(len(ts)) * 0.1,
        }
    )
    att = _make_dense_stream(600, duration)
    bat = _make_dense_stream(60, duration)
    gps = _make_dense_stream(60, duration)
    mot = _make_dense_stream(600, duration)

    return Flight(
        metadata=_make_metadata(duration),
        position=pos,
        attitude=att,
        battery=bat,
        gps=gps,
        motors=mot,
        primary_mode="manual",
    )


def _make_flight_duration_mismatch() -> Flight:
    """Flight where measured data duration differs significantly from metadata."""
    # Metadata says 120s but data only covers 60s
    duration_data = 60.0
    pos = _make_dense_stream(600, duration_data)
    att = _make_dense_stream(600, duration_data)
    gps = _make_dense_stream(60, duration_data)

    return Flight(
        metadata=_make_metadata(duration=120.0),
        position=pos,
        attitude=att,
        gps=gps,
        primary_mode="manual",
    )


@pytest.fixture
def plugin() -> LogHealthPlugin:
    return LogHealthPlugin()


class TestLogHealthInterface:
    """Verify plugin conforms to base Plugin interface."""

    def test_has_required_attributes(self, plugin: LogHealthPlugin) -> None:
        assert plugin.name == "log_health"
        assert plugin.version == "1.0.0"
        assert plugin.description

    def test_min_mode_is_manual(self, plugin: LogHealthPlugin) -> None:
        assert plugin.min_mode == "manual"

    def test_analyze_returns_list(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        result = plugin.analyze(flight, {})
        assert isinstance(result, list)

    def test_all_findings_are_finding_objects(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        assert all(isinstance(f, Finding) for f in findings)

    def test_plugin_name_in_all_findings(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        assert all(f.plugin_name == "log_health" for f in findings)

    def test_valid_severity_in_all_findings(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        valid = {"pass", "info", "warning", "critical"}
        assert all(f.severity in valid for f in findings)

    def test_applicable_for_manual(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        assert plugin.applicable(flight)


class TestLogHealthAllStreams:
    """All streams present and continuous should produce pass findings."""

    def test_produces_findings(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        assert len(findings) >= 1

    def test_streams_present_finding_is_pass(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        streams_finding = [f for f in findings if "data streams present" in f.title.lower()]
        assert streams_finding, f"No streams-present finding in: {[f.title for f in findings]}"
        assert streams_finding[0].severity == "pass"
        assert streams_finding[0].score == 100

    def test_no_missing_stream_findings(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        missing_findings = [f for f in findings if "missing data stream" in f.title.lower()]
        assert len(missing_findings) == 0


class TestLogHealthNoStreams:
    """All key streams missing should produce info findings."""

    def test_produces_findings(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_no_streams()
        findings = plugin.analyze(flight, {})
        assert len(findings) >= 1

    def test_each_missing_stream_has_finding(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_no_streams()
        findings = plugin.analyze(flight, {})
        missing_findings = [f for f in findings if "missing data stream" in f.title.lower()]
        # All 5 key streams should be reported missing
        assert len(missing_findings) == 5

    def test_missing_findings_are_info(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_no_streams()
        findings = plugin.analyze(flight, {})
        missing_findings = [f for f in findings if "missing data stream" in f.title.lower()]
        assert all(f.severity == "info" for f in missing_findings)

    def test_missing_findings_have_evidence(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_no_streams()
        findings = plugin.analyze(flight, {})
        missing_findings = [f for f in findings if "missing data stream" in f.title.lower()]
        for f in missing_findings:
            assert "missing_stream" in f.evidence


class TestLogHealthMissingBattery:
    """Only one stream missing should produce exactly one missing-stream finding."""

    def test_battery_missing_finding(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_missing_battery()
        findings = plugin.analyze(flight, {})
        battery_missing = [f for f in findings if "battery" in f.title.lower() and "missing" in f.title.lower()]
        assert len(battery_missing) == 1

    def test_other_streams_not_reported_missing(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_missing_battery()
        findings = plugin.analyze(flight, {})
        missing_findings = [f for f in findings if "missing data stream" in f.title.lower()]
        assert len(missing_findings) == 1


class TestLogHealthDropouts:
    """Data dropouts should be detected and reported."""

    def test_dropout_finding_produced(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_with_dropout()
        findings = plugin.analyze(flight, {})
        dropout_findings = [f for f in findings if "dropout" in f.title.lower()]
        assert len(dropout_findings) >= 1, f"No dropout finding in: {[f.title for f in findings]}"

    def test_dropout_finding_is_warning_or_critical(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_with_dropout()
        findings = plugin.analyze(flight, {})
        dropout_findings = [f for f in findings if "dropout" in f.title.lower()]
        for f in dropout_findings:
            assert f.severity in ("warning", "critical")

    def test_dropout_evidence_has_gap_info(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_with_dropout()
        findings = plugin.analyze(flight, {})
        dropout_findings = [f for f in findings if "dropout" in f.title.lower()]
        for f in dropout_findings:
            assert "dropout_count" in f.evidence
            assert "max_gap_sec" in f.evidence
            assert f.evidence["dropout_count"] >= 1

    def test_dropout_has_timestamps(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_with_dropout()
        findings = plugin.analyze(flight, {})
        dropout_findings = [f for f in findings if "dropout" in f.title.lower()]
        for f in dropout_findings:
            assert f.timestamp_start is not None
            assert f.timestamp_end is not None


class TestLogHealthDuration:
    """Log duration checks."""

    def test_consistent_duration_is_pass(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        dur_findings = [f for f in findings if "duration" in f.title.lower()]
        assert dur_findings, "Expected a duration finding"
        assert dur_findings[0].severity == "pass"

    def test_mismatch_duration_is_warning_or_critical(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_duration_mismatch()
        findings = plugin.analyze(flight, {})
        dur_findings = [f for f in findings if "duration" in f.title.lower()]
        assert dur_findings, "Expected a duration finding"
        assert dur_findings[0].severity in ("warning", "critical")

    def test_duration_evidence_has_metadata_value(self, plugin: LogHealthPlugin) -> None:
        flight = _make_flight_all_streams()
        findings = plugin.analyze(flight, {})
        dur_findings = [f for f in findings if "duration" in f.title.lower()]
        assert dur_findings
        ev = dur_findings[0].evidence
        assert "metadata_duration_sec" in ev
        assert "measured_duration_sec" in ev
