"""Tests for the Flight dataclass and related models."""

from __future__ import annotations

import pandas as pd

from goose.core.flight import (
    Flight,
    FlightEvent,
    FlightMetadata,
    FlightPhase,
    ModeChange,
)


def _make_metadata(**kwargs: object) -> FlightMetadata:
    defaults = {
        "source_file": "test.ulg",
        "autopilot": "px4",
        "firmware_version": "1.15.0",
        "vehicle_type": "quadcopter",
        "frame_type": None,
        "hardware": "Pixhawk 6C",
        "duration_sec": 300.0,
        "start_time_utc": None,
        "log_format": "ulog",
        "motor_count": 4,
    }
    defaults.update(kwargs)
    return FlightMetadata(**defaults)  # type: ignore[arg-type]


class TestFlightMetadata:
    def test_creation(self) -> None:
        meta = _make_metadata()
        assert meta.autopilot == "px4"
        assert meta.vehicle_type == "quadcopter"
        assert meta.motor_count == 4
        assert meta.log_format == "ulog"

    def test_all_vehicle_types(self) -> None:
        for vtype in ("quadcopter", "hexcopter", "octocopter", "fixedwing", "vtol"):
            meta = _make_metadata(vehicle_type=vtype)
            assert meta.vehicle_type == vtype


class TestModeChange:
    def test_creation(self) -> None:
        mc = ModeChange(timestamp=10.0, from_mode="manual", to_mode="position")
        assert mc.timestamp == 10.0
        assert mc.from_mode == "manual"
        assert mc.to_mode == "position"


class TestFlightEvent:
    def test_creation(self) -> None:
        evt = FlightEvent(
            timestamp=5.0,
            event_type="error",
            severity="critical",
            message="Motor 3 failure",
        )
        assert evt.event_type == "error"
        assert evt.severity == "critical"


class TestFlightPhase:
    def test_creation(self) -> None:
        phase = FlightPhase(start_time=0.0, end_time=10.0, phase_type="takeoff")
        assert phase.phase_type == "takeoff"
        assert phase.end_time - phase.start_time == 10.0


class TestFlight:
    def test_default_empty_dataframes(self) -> None:
        flight = Flight(metadata=_make_metadata())
        assert flight.position.empty
        assert flight.attitude.empty
        assert flight.battery.empty
        assert flight.motors.empty
        assert flight.vibration.empty
        assert flight.gps.empty
        assert flight.ekf.empty
        assert flight.cpu.empty

    def test_default_empty_lists(self) -> None:
        flight = Flight(metadata=_make_metadata())
        assert flight.mode_changes == []
        assert flight.events == []
        assert flight.phases == []
        assert flight.parameters == {}
        assert flight.primary_mode == "manual"

    def test_has_position_setpoints_false(self) -> None:
        flight = Flight(metadata=_make_metadata())
        assert flight.has_position_setpoints is False

    def test_has_position_setpoints_true(self) -> None:
        flight = Flight(
            metadata=_make_metadata(),
            position_setpoint=pd.DataFrame({"x": [1.0], "y": [2.0]}),
        )
        assert flight.has_position_setpoints is True

    def test_has_attitude_setpoints_false(self) -> None:
        flight = Flight(metadata=_make_metadata())
        assert flight.has_attitude_setpoints is False

    def test_crashed_false_empty(self) -> None:
        flight = Flight(metadata=_make_metadata())
        assert flight.crashed is False

    def test_crashed_true_rapid_alt_loss(self) -> None:
        # Simulate 100 altitude samples where last 10% drops by >5m
        import numpy as np

        n = 100
        alt = np.concatenate([np.full(90, 50.0), np.linspace(50.0, 0.0, 10)])
        flight = Flight(
            metadata=_make_metadata(),
            position=pd.DataFrame(
                {
                    "timestamp": np.linspace(0, 100, n),
                    "lat": np.zeros(n),
                    "lon": np.zeros(n),
                    "alt_msl": alt,
                    "alt_rel": alt,
                }
            ),
        )
        assert flight.crashed is True

    def test_crashed_false_stable_alt(self) -> None:
        import numpy as np

        n = 100
        alt = np.full(n, 50.0)
        flight = Flight(
            metadata=_make_metadata(),
            position=pd.DataFrame(
                {
                    "timestamp": np.linspace(0, 100, n),
                    "lat": np.zeros(n),
                    "lon": np.zeros(n),
                    "alt_msl": alt,
                    "alt_rel": alt,
                }
            ),
        )
        assert flight.crashed is False
