"""Tests for the crash root cause engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from goose.core.crash_detector import (
    MOTOR_FAILURE,
    POWER_LOSS,
    UNKNOWN,
    CrashAnalysis,
    analyze_crash,
)
from goose.core.finding import Finding
from goose.core.flight import Flight, FlightMetadata


def _make_metadata(**overrides: object) -> FlightMetadata:
    defaults = dict(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.15.2",
        vehicle_type="quadcopter",
        frame_type=None,
        hardware="Pixhawk 6C",
        duration_sec=300.0,
        start_time_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
        log_format="ulog",
        motor_count=4,
    )
    defaults.update(overrides)
    return FlightMetadata(**defaults)  # type: ignore[arg-type]


def _make_flight(crashed: bool = False, **kwargs: object) -> Flight:
    """Create a Flight with controllable crash state."""
    meta = _make_metadata()
    flight = Flight(metadata=meta)

    if crashed:
        # Create position data with a rapid altitude drop at the end
        n = 100
        timestamps = [float(i) for i in range(n)]
        altitudes = [50.0] * 90 + [50.0 - i * 6 for i in range(10)]
        flight.position = pd.DataFrame(
            {
                "timestamp": timestamps,
                "lat": [47.0] * n,
                "lon": [8.0] * n,
                "alt_msl": [400.0] * n,
                "alt_rel": altitudes,
            }
        )
    return flight


def _motor_failure_findings() -> list[Finding]:
    """Findings that indicate a motor failure crash."""
    return [
        Finding(
            plugin_name="crash_detection",
            title="Impact detected",
            severity="critical",
            score=6,
            description="Motor 3 output dropped to 0% at t=342s",
            evidence={"classification": MOTOR_FAILURE},
            timestamp_start=348.0,
        ),
        Finding(
            plugin_name="motor_saturation",
            title="Motor 3 failure detected",
            severity="critical",
            score=10,
            description="Motor 3 output dropped to 0%",
            evidence={"motor_id": 3},
            timestamp_start=342.0,
        ),
        Finding(
            plugin_name="vibration",
            title="Z-axis vibration spike",
            severity="warning",
            score=68,
            description="Z-axis 38.2 m/s² peak (limit: 30)",
            timestamp_start=328.0,
        ),
        Finding(
            plugin_name="attitude_tracking",
            title="Attitude divergence",
            severity="warning",
            score=45,
            description="40°+ roll error post-failure",
            timestamp_start=343.0,
        ),
        Finding(
            plugin_name="battery_sag",
            title="Battery nominal",
            severity="pass",
            score=91,
            description="Cells nominal, 3.48V min",
        ),
    ]


def _power_loss_findings() -> list[Finding]:
    """Findings that indicate a power loss crash."""
    return [
        Finding(
            plugin_name="crash_detection",
            title="Impact detected",
            severity="critical",
            score=8,
            description="Complete power loss at t=200s",
            evidence={"classification": POWER_LOSS},
            timestamp_start=205.0,
        ),
        Finding(
            plugin_name="battery_sag",
            title="Battery voltage collapse",
            severity="critical",
            score=5,
            description="Voltage dropped below 3.0V/cell",
            timestamp_start=198.0,
        ),
    ]


def _normal_flight_findings() -> list[Finding]:
    """Findings from a normal, healthy flight."""
    return [
        Finding(
            plugin_name="vibration",
            title="Vibration nominal",
            severity="pass",
            score=95,
            description="All axes within limits",
        ),
        Finding(
            plugin_name="battery_sag",
            title="Battery nominal",
            severity="pass",
            score=92,
            description="Cells nominal",
        ),
    ]


class TestCrashAnalysisDataclass:
    def test_defaults(self) -> None:
        analysis = CrashAnalysis(
            crashed=False,
            confidence=0.0,
            classification="none",
            root_cause="No crash",
        )
        assert analysis.crashed is False
        assert analysis.evidence_chain == []
        assert analysis.contributing_factors == []
        assert analysis.inspect_checklist == []
        assert analysis.timeline == []

    def test_full_construction(self) -> None:
        analysis = CrashAnalysis(
            crashed=True,
            confidence=0.94,
            classification=MOTOR_FAILURE,
            root_cause="Motor 3 failed",
            evidence_chain=["motor output dropped"],
            contributing_factors=["vibration spike"],
            inspect_checklist=["Motor 3 bearings"],
            timeline=[{"timestamp": 342.0, "event": "Motor 3 drop", "severity": "critical"}],
        )
        assert analysis.crashed is True
        assert analysis.confidence == 0.94
        assert analysis.classification == MOTOR_FAILURE


class TestAnalyzeCrash:
    def test_no_crash_detected(self) -> None:
        flight = _make_flight(crashed=False)
        findings = _normal_flight_findings()
        result = analyze_crash(flight, findings)

        assert result.crashed is False
        assert result.classification == "none"
        assert result.root_cause == "No crash detected"
        assert result.confidence == 0.0

    def test_motor_failure_crash(self) -> None:
        flight = _make_flight(crashed=True)
        findings = _motor_failure_findings()
        result = analyze_crash(flight, findings)

        assert result.crashed is True
        assert result.classification == MOTOR_FAILURE
        assert result.confidence > 0.5
        assert "Motor 3" in result.root_cause
        assert len(result.timeline) > 0
        assert len(result.inspect_checklist) > 0
        # Specific motor checklist items
        assert any("Motor 3" in item for item in result.inspect_checklist)

    def test_power_loss_crash(self) -> None:
        flight = _make_flight(crashed=True)
        findings = _power_loss_findings()
        result = analyze_crash(flight, findings)

        assert result.crashed is True
        assert result.classification == POWER_LOSS
        assert result.confidence > 0.5

    def test_crash_from_flight_data_only(self) -> None:
        """Crash detected from flight data even without crash_detection plugin findings."""
        flight = _make_flight(crashed=True)
        findings: list[Finding] = []
        result = analyze_crash(flight, findings)

        assert result.crashed is True
        assert result.classification == UNKNOWN
        assert result.confidence > 0.0

    def test_crash_with_no_findings_uses_flight_data(self) -> None:
        flight = _make_flight(crashed=True)
        result = analyze_crash(flight, [])

        assert result.crashed is True

    def test_no_crash_with_empty_findings(self) -> None:
        flight = _make_flight(crashed=False)
        result = analyze_crash(flight, [])

        assert result.crashed is False

    def test_timeline_sorted_by_timestamp(self) -> None:
        flight = _make_flight(crashed=True)
        findings = _motor_failure_findings()
        result = analyze_crash(flight, findings)

        timestamps = [e["timestamp"] for e in result.timeline]
        assert timestamps == sorted(timestamps)

    def test_contributing_factors_from_warnings(self) -> None:
        flight = _make_flight(crashed=True)
        findings = _motor_failure_findings()
        result = analyze_crash(flight, findings)

        # vibration and attitude_tracking are warning-level
        assert any("vibration" in f for f in result.contributing_factors)

    def test_evidence_chain_includes_critical_findings(self) -> None:
        flight = _make_flight(crashed=True)
        findings = _motor_failure_findings()
        result = analyze_crash(flight, findings)

        assert any("motor_saturation" in e for e in result.evidence_chain)
