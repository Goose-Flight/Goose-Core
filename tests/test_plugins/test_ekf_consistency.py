"""Tests for EkfConsistencyPlugin using mock Flight objects."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata
from goose.plugins.ekf_consistency import EkfConsistencyPlugin

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


def _make_flight(ekf: pd.DataFrame, primary_mode: str = "position") -> Flight:
    return Flight(
        metadata=_make_metadata(),
        ekf=ekf,
        primary_mode=primary_mode,
    )


def _good_ekf(n: int = 300) -> pd.DataFrame:
    """EKF data with all innovations well within limits."""
    ts = np.linspace(0.0, 60.0, n)
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "timestamp": ts,
        "vel_innov_x": rng.normal(0.0, 0.2, n),
        "vel_innov_y": rng.normal(0.0, 0.2, n),
        "vel_innov_z": rng.normal(0.0, 0.2, n),
        "pos_innov_x": rng.normal(0.0, 0.3, n),
        "pos_innov_y": rng.normal(0.0, 0.3, n),
        "pos_innov_z": rng.normal(0.0, 0.3, n),
        "ekf_fault_flags": np.zeros(n, dtype=int),
    })


def _warning_ekf(n: int = 300) -> pd.DataFrame:
    """EKF data with velocity innovations at warning level."""
    ts = np.linspace(0.0, 60.0, n)
    rng = np.random.default_rng(7)
    vel = np.full(n, 0.85)  # above warning threshold 0.8
    return pd.DataFrame({
        "timestamp": ts,
        "vel_innov_x": vel,
        "vel_innov_y": rng.normal(0.0, 0.1, n),
        "vel_innov_z": rng.normal(0.0, 0.1, n),
        "ekf_fault_flags": np.zeros(n, dtype=int),
    })


def _critical_ekf(n: int = 300) -> pd.DataFrame:
    """EKF data with innovations exceeding critical threshold."""
    ts = np.linspace(0.0, 60.0, n)
    np.random.default_rng(13)
    vel = np.full(n, 1.2)  # above critical threshold 1.0
    return pd.DataFrame({
        "timestamp": ts,
        "vel_innov_x": vel,
        "vel_innov_y": vel,
        "vel_innov_z": vel,
        "ekf_fault_flags": np.zeros(n, dtype=int),
    })


def _faulted_ekf(n: int = 300) -> pd.DataFrame:
    """EKF data with fault flags set."""
    ts = np.linspace(0.0, 60.0, n)
    rng = np.random.default_rng(99)
    flags = np.zeros(n, dtype=int)
    flags[100:200] = 1  # fault for a portion of the flight (>5% triggers critical)
    return pd.DataFrame({
        "timestamp": ts,
        "vel_innov_x": rng.normal(0.0, 0.2, n),
        "ekf_fault_flags": flags,
    })


def _partial_fault_ekf(n: int = 300) -> pd.DataFrame:
    """EKF data with a small number of fault flags (below 5% critical threshold)."""
    ts = np.linspace(0.0, 60.0, n)
    rng = np.random.default_rng(55)
    flags = np.zeros(n, dtype=int)
    flags[5:10] = 1  # only ~1.7% faulted
    return pd.DataFrame({
        "timestamp": ts,
        "vel_innov_x": rng.normal(0.0, 0.2, n),
        "ekf_fault_flags": flags,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def plugin() -> EkfConsistencyPlugin:
    return EkfConsistencyPlugin()


@pytest.fixture
def good_flight() -> Flight:
    return _make_flight(_good_ekf())


@pytest.fixture
def warning_flight() -> Flight:
    return _make_flight(_warning_ekf())


@pytest.fixture
def critical_flight() -> Flight:
    return _make_flight(_critical_ekf())


@pytest.fixture
def faulted_flight() -> Flight:
    return _make_flight(_faulted_ekf())


@pytest.fixture
def empty_ekf_flight() -> Flight:
    return _make_flight(pd.DataFrame())


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------

class TestEkfConsistencyPluginInterface:
    def test_has_required_attributes(self, plugin: EkfConsistencyPlugin) -> None:
        assert plugin.name == "ekf_consistency"
        assert plugin.version == "1.0.0"
        assert plugin.description

    def test_min_mode_is_manual(self, plugin: EkfConsistencyPlugin) -> None:
        assert plugin.min_mode == "manual"

    def test_applicable_for_position_mode(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        assert plugin.applicable(good_flight)

    def test_analyze_returns_list(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        assert isinstance(plugin.analyze(good_flight, {}), list)

    def test_all_findings_are_finding_instances(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        assert all(isinstance(f, Finding) for f in plugin.analyze(good_flight, {}))

    def test_plugin_name_in_all_findings(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        assert all(f.plugin_name == "ekf_consistency" for f in plugin.analyze(good_flight, {}))

    def test_valid_severities(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        valid = {"pass", "info", "warning", "critical"}
        for f in plugin.analyze(good_flight, {}):
            assert f.severity in valid

    def test_score_in_range(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        for f in plugin.analyze(good_flight, {}):
            assert 0 <= f.score <= 100


# ---------------------------------------------------------------------------
# Empty data
# ---------------------------------------------------------------------------

class TestEkfConsistencyEmptyData:
    def test_empty_ekf_returns_info(self, plugin: EkfConsistencyPlugin, empty_ekf_flight: Flight) -> None:
        findings = plugin.analyze(empty_ekf_flight, {})
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert findings[0].score == 50

    def test_no_ekf_attribute(self, plugin: EkfConsistencyPlugin) -> None:
        flight = _make_flight(pd.DataFrame())
        findings = plugin.analyze(flight, {})
        assert findings[0].severity == "info"


# ---------------------------------------------------------------------------
# Good EKF
# ---------------------------------------------------------------------------

class TestEkfConsistencyGoodFlight:
    def test_produces_findings(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        assert len(plugin.analyze(good_flight, {})) >= 1

    def test_high_scores_for_good_flight(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        # Good flight should have mostly high scores
        scores = [f.score for f in findings]
        assert max(scores) >= 70

    def test_vel_innovations_pass(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        vel_findings = [f for f in findings if "velocity" in f.title.lower()]
        if vel_findings:
            assert vel_findings[0].severity == "pass"


# ---------------------------------------------------------------------------
# Warning-level innovations
# ---------------------------------------------------------------------------

class TestEkfConsistencyWarning:
    def test_warning_severity_present(self, plugin: EkfConsistencyPlugin, warning_flight: Flight) -> None:
        findings = plugin.analyze(warning_flight, {})
        severities = {f.severity for f in findings}
        assert "warning" in severities or "critical" in severities

    def test_evidence_contains_axes(self, plugin: EkfConsistencyPlugin, warning_flight: Flight) -> None:
        findings = plugin.analyze(warning_flight, {})
        innov_findings = [f for f in findings if "innov" in f.title.lower() or "innovation" in f.title.lower()]
        for f in innov_findings:
            assert "axes" in f.evidence


# ---------------------------------------------------------------------------
# Critical-level innovations
# ---------------------------------------------------------------------------

class TestEkfConsistencyCritical:
    def test_critical_severity(self, plugin: EkfConsistencyPlugin, critical_flight: Flight) -> None:
        findings = plugin.analyze(critical_flight, {})
        assert any(f.severity == "critical" for f in findings)

    def test_low_score_for_critical(self, plugin: EkfConsistencyPlugin, critical_flight: Flight) -> None:
        findings = plugin.analyze(critical_flight, {})
        critical = [f for f in findings if f.severity == "critical"]
        assert all(f.score <= 30 for f in critical)


# ---------------------------------------------------------------------------
# Fault flags
# ---------------------------------------------------------------------------

class TestEkfConsistencyFaultFlags:
    def test_fault_finding_produced(self, plugin: EkfConsistencyPlugin, faulted_flight: Flight) -> None:
        findings = plugin.analyze(faulted_flight, {})
        fault_findings = [f for f in findings if "fault" in f.title.lower()]
        assert len(fault_findings) >= 1

    def test_fault_severity_not_pass(self, plugin: EkfConsistencyPlugin, faulted_flight: Flight) -> None:
        findings = plugin.analyze(faulted_flight, {})
        fault_findings = [f for f in findings if "fault" in f.title.lower()]
        assert all(f.severity != "pass" for f in fault_findings)

    def test_no_fault_flags_produces_pass(self, plugin: EkfConsistencyPlugin, good_flight: Flight) -> None:
        findings = plugin.analyze(good_flight, {})
        fault_findings = [f for f in findings if "fault" in f.title.lower()]
        if fault_findings:
            assert fault_findings[0].severity == "pass"
