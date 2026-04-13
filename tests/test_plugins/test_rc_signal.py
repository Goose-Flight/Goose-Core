"""Tests for RcSignalPlugin using mock Flight objects."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata
from goose.plugins.rc_signal import RcSignalPlugin

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


def _make_flight(rc_input: pd.DataFrame, primary_mode: str = "manual") -> Flight:
    return Flight(
        metadata=_make_metadata(),
        rc_input=rc_input,
        primary_mode=primary_mode,
    )


def _good_rc(n: int = 200, duration: float = 60.0) -> pd.DataFrame:
    """RC data with good RSSI and no dropouts."""
    ts = np.linspace(0.0, duration, n)
    rssi = np.full(n, 90.0)
    chan1 = np.sin(np.linspace(0, 4 * np.pi, n)) * 500 + 1500
    chan2 = np.cos(np.linspace(0, 4 * np.pi, n)) * 500 + 1500
    return pd.DataFrame({"timestamp": ts, "rssi": rssi, "chan1": chan1, "chan2": chan2})


def _weak_rssi_rc(n: int = 200, rssi_val: float = 60.0) -> pd.DataFrame:
    """RC data with consistently weak RSSI (warning level)."""
    ts = np.linspace(0.0, 60.0, n)
    rssi = np.full(n, rssi_val)
    chan1 = np.sin(np.linspace(0, 4 * np.pi, n)) * 200 + 1500
    return pd.DataFrame({"timestamp": ts, "rssi": rssi, "chan1": chan1})


def _critical_rssi_rc(n: int = 200, rssi_val: float = 30.0) -> pd.DataFrame:
    """RC data with critically low RSSI."""
    ts = np.linspace(0.0, 60.0, n)
    rssi = np.full(n, rssi_val)
    return pd.DataFrame({"timestamp": ts, "rssi": rssi})


def _rc_with_dropout(gap_sec: float = 5.0) -> pd.DataFrame:
    """RC data with a synthetic dropout gap."""
    ts1 = np.linspace(0.0, 10.0, 100)
    ts2 = np.linspace(10.0 + gap_sec, 60.0, 100)
    ts = np.concatenate([ts1, ts2])
    rssi = np.full(len(ts), 85.0)
    return pd.DataFrame({"timestamp": ts, "rssi": rssi})


def _rc_with_stuck_channel() -> pd.DataFrame:
    """RC data with a stuck channel (constant value)."""
    n = 300
    ts = np.linspace(0.0, 60.0, n)
    rssi = np.full(n, 85.0)
    chan1 = np.full(n, 1500.0)  # stuck
    chan2 = np.sin(np.linspace(0, 4 * np.pi, n)) * 500 + 1500  # normal
    return pd.DataFrame({"timestamp": ts, "rssi": rssi, "chan1": chan1, "chan2": chan2})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def plugin() -> RcSignalPlugin:
    return RcSignalPlugin()


@pytest.fixture
def good_flight(plugin: RcSignalPlugin) -> Flight:
    return _make_flight(_good_rc())


@pytest.fixture
def weak_rssi_flight() -> Flight:
    return _make_flight(_weak_rssi_rc(rssi_val=60.0))


@pytest.fixture
def critical_rssi_flight() -> Flight:
    return _make_flight(_critical_rssi_rc(rssi_val=30.0))


@pytest.fixture
def dropout_flight() -> Flight:
    return _make_flight(_rc_with_dropout(gap_sec=5.0))


@pytest.fixture
def stuck_channel_flight() -> Flight:
    return _make_flight(_rc_with_stuck_channel())


@pytest.fixture
def empty_rc_flight() -> Flight:
    return _make_flight(pd.DataFrame())


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------

class TestRcSignalPluginInterface:
    def test_has_required_attributes(self, plugin: RcSignalPlugin) -> None:
        assert plugin.name == "rc_signal"
        assert plugin.version == "1.0.0"
        assert plugin.description

    def test_min_mode_is_manual(self, plugin: RcSignalPlugin) -> None:
        assert plugin.min_mode == "manual"

    def test_applicable_for_manual_mode(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        assert plugin.applicable(good_flight)

    def test_analyze_returns_list(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        result = plugin.analyze(good_flight, {})
        assert isinstance(result, list)

    def test_all_findings_are_finding_instances(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        result = plugin.analyze(good_flight, {})
        assert all(isinstance(f, Finding) for f in result)

    def test_plugin_name_in_all_findings(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        result = plugin.analyze(good_flight, {})
        assert all(f.plugin_name == "rc_signal" for f in result)

    def test_valid_severities(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        valid = {"pass", "info", "warning", "critical"}
        for finding in plugin.analyze(good_flight, {}):
            assert finding.severity in valid

    def test_score_in_range(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        for finding in plugin.analyze(good_flight, {}):
            assert 0 <= finding.score <= 100


# ---------------------------------------------------------------------------
# Empty data
# ---------------------------------------------------------------------------

class TestRcSignalEmptyData:
    def test_empty_rc_returns_info(self, plugin: RcSignalPlugin, empty_rc_flight: Flight) -> None:
        findings = plugin.analyze(empty_rc_flight, {})
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert findings[0].score == 50

    def test_missing_rssi_col_returns_info(self, plugin: RcSignalPlugin) -> None:
        # DataFrame with timestamp but no rssi column
        rc = pd.DataFrame({"timestamp": [0.0, 1.0, 2.0], "chan1": [1500, 1500, 1500]})
        flight = _make_flight(rc)
        findings = plugin.analyze(flight, {})
        assert len(findings) == 1
        assert findings[0].severity == "info"


# ---------------------------------------------------------------------------
# Good signal
# ---------------------------------------------------------------------------

class TestRcSignalGoodFlight:
    def test_produces_findings(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        assert len(plugin.analyze(good_flight, {})) >= 1

    def test_rssi_finding_is_pass(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        rssi_findings = [f for f in findings if "signal strength" in f.title.lower() or "rssi" in f.title.lower()]
        assert len(rssi_findings) >= 1
        assert rssi_findings[0].severity == "pass"

    def test_no_critical_findings(self, plugin: RcSignalPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        assert not any(f.severity == "critical" for f in findings)


# ---------------------------------------------------------------------------
# RSSI degradation
# ---------------------------------------------------------------------------

class TestRcSignalWeakRssi:
    def test_warning_severity(self, plugin: RcSignalPlugin, weak_rssi_flight: Flight) -> None:
        findings = plugin.analyze(weak_rssi_flight, {})
        severities = {f.severity for f in findings}
        assert "warning" in severities or "critical" in severities

    def test_evidence_contains_rssi_values(self, plugin: RcSignalPlugin, weak_rssi_flight: Flight) -> None:
        findings = plugin.analyze(weak_rssi_flight, {})
        rssi_finding = next(
            (f for f in findings if "rssi" in f.title.lower() or "signal" in f.title.lower()), None
        )
        assert rssi_finding is not None
        assert "min_rssi_pct" in rssi_finding.evidence


class TestRcSignalCriticalRssi:
    def test_critical_severity(self, plugin: RcSignalPlugin, critical_rssi_flight: Flight) -> None:
        findings = plugin.analyze(critical_rssi_flight, {})
        severities = {f.severity for f in findings}
        assert "critical" in severities

    def test_low_score(self, plugin: RcSignalPlugin, critical_rssi_flight: Flight) -> None:
        findings = plugin.analyze(critical_rssi_flight, {})
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert all(f.score <= 30 for f in critical_findings)


# ---------------------------------------------------------------------------
# Dropout detection
# ---------------------------------------------------------------------------

class TestRcSignalDropouts:
    def test_dropout_finding_produced(self, plugin: RcSignalPlugin, dropout_flight: Flight) -> None:
        findings = plugin.analyze(dropout_flight, {})
        dropout_findings = [f for f in findings if "dropout" in f.title.lower()]
        assert len(dropout_findings) >= 1

    def test_dropout_severity_not_pass(self, plugin: RcSignalPlugin, dropout_flight: Flight) -> None:
        findings = plugin.analyze(dropout_flight, {})
        dropout_findings = [f for f in findings if "dropout" in f.title.lower()]
        assert all(f.severity != "pass" for f in dropout_findings)

    def test_dropout_evidence_has_count(self, plugin: RcSignalPlugin, dropout_flight: Flight) -> None:
        findings = plugin.analyze(dropout_flight, {})
        dropout_findings = [f for f in findings if "dropout" in f.title.lower()]
        for f in dropout_findings:
            assert "dropout_count" in f.evidence
            assert f.evidence["dropout_count"] >= 1


# ---------------------------------------------------------------------------
# Stuck channel detection
# ---------------------------------------------------------------------------

class TestRcSignalStuckChannel:
    def test_stuck_finding_produced(self, plugin: RcSignalPlugin, stuck_channel_flight: Flight) -> None:
        findings = plugin.analyze(stuck_channel_flight, {})
        stuck_findings = [f for f in findings if "stuck" in f.title.lower()]
        assert len(stuck_findings) >= 1

    def test_stuck_severity_is_warning(self, plugin: RcSignalPlugin, stuck_channel_flight: Flight) -> None:
        findings = plugin.analyze(stuck_channel_flight, {})
        stuck_findings = [f for f in findings if "stuck" in f.title.lower()]
        assert all(f.severity == "warning" for f in stuck_findings)

    def test_stuck_evidence_has_channels(self, plugin: RcSignalPlugin, stuck_channel_flight: Flight) -> None:
        findings = plugin.analyze(stuck_channel_flight, {})
        stuck_findings = [f for f in findings if "stuck" in f.title.lower()]
        for f in stuck_findings:
            assert "stuck_channels" in f.evidence
            assert len(f.evidence["stuck_channels"]) >= 1
