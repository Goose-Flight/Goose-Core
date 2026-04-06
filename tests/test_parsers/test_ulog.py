"""Tests for the ULog parser against real PX4 flight logs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from goose.core.flight import Flight
from goose.parsers.ulog import ULogParser


class TestULogParserBasic:
    """Test parser can parse all fixture files and produce valid Flight objects."""

    def test_parser_format(self, ulog_parser: ULogParser) -> None:
        assert ulog_parser.format_name == "ulog"
        assert ".ulg" in ulog_parser.file_extensions

    def test_can_parse_ulg(self, ulog_parser: ULogParser) -> None:
        assert ulog_parser.can_parse("test.ulg") is True
        assert ulog_parser.can_parse("test.bin") is False
        assert ulog_parser.can_parse("test.csv") is False

    def test_file_not_found(self, ulog_parser: ULogParser) -> None:
        with pytest.raises(FileNotFoundError):
            ulog_parser.parse("nonexistent.ulg")


class TestULogNormalFlight:
    """Test parser against a normal (clean) PX4 flight log."""

    @pytest.fixture
    def flight(self, ulog_parser: ULogParser, normal_flight_path: Path) -> Flight:
        return ulog_parser.parse(normal_flight_path)

    def test_metadata_autopilot(self, flight: Flight) -> None:
        assert flight.metadata.autopilot == "px4"

    def test_metadata_log_format(self, flight: Flight) -> None:
        assert flight.metadata.log_format == "ulog"

    def test_metadata_duration_positive(self, flight: Flight) -> None:
        assert flight.metadata.duration_sec > 0

    def test_metadata_motor_count(self, flight: Flight) -> None:
        assert flight.metadata.motor_count > 0

    def test_metadata_source_file(self, flight: Flight, normal_flight_path: Path) -> None:
        assert str(normal_flight_path) in flight.metadata.source_file

    def test_position_populated(self, flight: Flight) -> None:
        assert not flight.position.empty
        assert "timestamp" in flight.position.columns
        assert "lat" in flight.position.columns
        assert "lon" in flight.position.columns

    def test_attitude_populated(self, flight: Flight) -> None:
        assert not flight.attitude.empty
        assert "timestamp" in flight.attitude.columns
        assert "roll" in flight.attitude.columns
        assert "pitch" in flight.attitude.columns
        assert "yaw" in flight.attitude.columns

    def test_attitude_values_radians(self, flight: Flight) -> None:
        """Attitude values should be in radians (roughly -pi to pi)."""
        import math

        assert flight.attitude["roll"].abs().max() < math.pi * 2
        assert flight.attitude["pitch"].abs().max() < math.pi * 2

    def test_motors_populated(self, flight: Flight) -> None:
        assert not flight.motors.empty
        assert "timestamp" in flight.motors.columns
        # Should have output_0 through output_N columns
        motor_cols = [c for c in flight.motors.columns if c.startswith("output_")]
        assert len(motor_cols) > 0

    def test_vibration_populated(self, flight: Flight) -> None:
        assert not flight.vibration.empty
        assert "accel_x" in flight.vibration.columns
        assert "accel_y" in flight.vibration.columns
        assert "accel_z" in flight.vibration.columns

    def test_parameters_populated(self, flight: Flight) -> None:
        assert len(flight.parameters) > 0

    def test_mode_changes_list(self, flight: Flight) -> None:
        assert isinstance(flight.mode_changes, list)

    def test_events_list(self, flight: Flight) -> None:
        assert isinstance(flight.events, list)

    def test_primary_mode_valid(self, flight: Flight) -> None:
        valid_modes = {"manual", "stabilized", "altitude", "position", "mission"}
        assert flight.primary_mode in valid_modes

    def test_timestamps_monotonic(self, flight: Flight) -> None:
        """Timestamps should be non-decreasing."""
        for name in ("position", "attitude", "vibration"):
            df = getattr(flight, name)
            if not df.empty and "timestamp" in df.columns:
                ts = df["timestamp"]
                assert (ts.diff().dropna() >= -0.001).all(), f"{name} timestamps not monotonic"

    def test_timestamps_start_near_zero(self, flight: Flight) -> None:
        """First timestamp should be near 0 (relative to log start)."""
        if not flight.attitude.empty:
            first_ts = flight.attitude["timestamp"].iloc[0]
            assert first_ts >= -1.0, f"First attitude timestamp {first_ts} too negative"


class TestULogMotorFailure:
    """Test parser against a motor failure crash log."""

    @pytest.fixture
    def flight(self, ulog_parser: ULogParser, motor_failure_path: Path) -> Flight:
        return ulog_parser.parse(motor_failure_path)

    def test_parses_successfully(self, flight: Flight) -> None:
        assert flight.metadata.autopilot == "px4"

    def test_metadata_complete(self, flight: Flight) -> None:
        assert flight.metadata.duration_sec > 0
        assert flight.metadata.firmware_version != ""
        assert flight.metadata.vehicle_type in (
            "quadcopter", "hexcopter", "octocopter", "fixedwing", "vtol"
        )

    def test_position_data(self, flight: Flight) -> None:
        assert not flight.position.empty

    def test_attitude_data(self, flight: Flight) -> None:
        assert not flight.attitude.empty

    def test_motors_data(self, flight: Flight) -> None:
        assert not flight.motors.empty

    def test_parameters_exist(self, flight: Flight) -> None:
        assert len(flight.parameters) > 0


class TestULogVibrationCrash:
    """Test parser against a vibration crash log."""

    @pytest.fixture
    def flight(self, ulog_parser: ULogParser, vibration_crash_path: Path) -> Flight:
        return ulog_parser.parse(vibration_crash_path)

    def test_parses_successfully(self, flight: Flight) -> None:
        assert flight.metadata.autopilot == "px4"

    def test_vibration_data_present(self, flight: Flight) -> None:
        assert not flight.vibration.empty
        assert "accel_x" in flight.vibration.columns

    def test_all_dataframe_fields_have_timestamp(self, flight: Flight) -> None:
        """Every non-empty DataFrame should have a timestamp column."""
        df_names = [
            "position", "position_setpoint", "velocity", "velocity_setpoint",
            "attitude", "attitude_setpoint", "attitude_rate",
            "attitude_rate_setpoint", "battery", "gps", "motors",
            "vibration", "rc_input", "ekf", "cpu",
        ]
        for name in df_names:
            df: pd.DataFrame = getattr(flight, name)
            if not df.empty:
                assert "timestamp" in df.columns, f"{name} missing 'timestamp' column"

    def test_metadata_hardware_string(self, flight: Flight) -> None:
        # Hardware should be a string or None
        assert flight.metadata.hardware is None or isinstance(flight.metadata.hardware, str)
