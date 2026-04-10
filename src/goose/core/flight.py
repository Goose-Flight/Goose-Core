"""Core Flight dataclass — the normalized representation of any drone flight log."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd


@dataclass
class FlightMetadata:
    """Metadata extracted from a flight log header."""

    source_file: str
    autopilot: str  # "px4" | "ardupilot"
    firmware_version: str
    vehicle_type: str  # "quadcopter" | "hexcopter" | "octocopter" | "fixedwing" | "vtol"
    frame_type: str | None  # e.g. "x500" if available
    hardware: str | None  # e.g. "Pixhawk 6C" if available
    duration_sec: float
    start_time_utc: datetime | None
    log_format: str  # "ulog" | "dataflash" | "tlog" | "csv"
    motor_count: int


@dataclass
class ModeChange:
    """A flight mode transition."""

    timestamp: float  # seconds from log start
    from_mode: str
    to_mode: str


@dataclass
class FlightEvent:
    """A discrete event recorded during flight."""

    timestamp: float
    event_type: str  # "error" | "warning" | "info" | "failsafe"
    severity: str  # "critical" | "warning" | "info"
    message: str


@dataclass
class FlightPhase:
    """A detected phase of flight."""

    start_time: float
    end_time: float
    phase_type: str  # "preflight" | "takeoff" | "climb" | "on_mission" | "return" | "descent" | "landing" | "postflight"


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


@dataclass
class Flight:
    """Normalized flight data extracted from any supported log format."""

    metadata: FlightMetadata

    # Time-series (pandas DataFrames, 'timestamp' col in seconds from start)
    position: pd.DataFrame = field(default_factory=_empty_df)
    position_setpoint: pd.DataFrame = field(default_factory=_empty_df)
    velocity: pd.DataFrame = field(default_factory=_empty_df)
    velocity_setpoint: pd.DataFrame = field(default_factory=_empty_df)
    attitude: pd.DataFrame = field(default_factory=_empty_df)
    attitude_setpoint: pd.DataFrame = field(default_factory=_empty_df)
    attitude_rate: pd.DataFrame = field(default_factory=_empty_df)
    attitude_rate_setpoint: pd.DataFrame = field(default_factory=_empty_df)
    battery: pd.DataFrame = field(default_factory=_empty_df)
    gps: pd.DataFrame = field(default_factory=_empty_df)
    motors: pd.DataFrame = field(default_factory=_empty_df)
    vibration: pd.DataFrame = field(default_factory=_empty_df)
    rc_input: pd.DataFrame = field(default_factory=_empty_df)
    ekf: pd.DataFrame = field(default_factory=_empty_df)
    cpu: pd.DataFrame = field(default_factory=_empty_df)

    manual_control: pd.DataFrame = field(default_factory=_empty_df)
    # Stick inputs: x (roll), y (pitch), r (yaw), z (throttle)

    actuator_controls: pd.DataFrame = field(default_factory=_empty_df)
    # Demand signals before mixer: roll, pitch, yaw, thrust

    magnetometer: pd.DataFrame = field(default_factory=_empty_df)
    # Compass: mag_x, mag_y, mag_z (Gauss), heading_deg (computed)

    airspeed: pd.DataFrame = field(default_factory=_empty_df)
    # Fixed-wing: indicated, true_airspeed

    wind: pd.DataFrame = field(default_factory=_empty_df)
    # Estimated wind: wind_x (east), wind_y (north), wind_z (up), wind_speed

    rc_channels: pd.DataFrame = field(default_factory=_empty_df)
    # Individual RC channels: chan1..chan8 (normalized), rssi

    raw_accel: pd.DataFrame = field(default_factory=_empty_df)
    # High-rate accelerometer: accel_x, accel_y, accel_z (m/s²)

    raw_gyro: pd.DataFrame = field(default_factory=_empty_df)
    # High-rate gyroscope: gyro_x, gyro_y, gyro_z (deg/s)

    barometer: pd.DataFrame = field(default_factory=_empty_df)
    # Raw barometer: pressure_pa, temperature_c, baro_alt_meter

    # Discrete
    mode_changes: list[ModeChange] = field(default_factory=list)
    events: list[FlightEvent] = field(default_factory=list)
    parameters: dict[str, float] = field(default_factory=dict)

    # Derived (computed after parsing)
    phases: list[FlightPhase] = field(default_factory=list)
    primary_mode: str = "manual"

    @property
    def has_position_setpoints(self) -> bool:
        """True if position setpoint data is available."""
        return not self.position_setpoint.empty

    @property
    def has_attitude_setpoints(self) -> bool:
        """True if attitude setpoint data is available."""
        return not self.attitude_setpoint.empty

    @property
    def crashed(self) -> bool:
        """True if an impact was detected (rapid altitude loss + data stop)."""
        if self.position.empty or len(self.position) < 10:
            return False
        # Simple heuristic: check if altitude drops rapidly near end of log
        alt_col = "alt_rel" if "alt_rel" in self.position.columns else "alt_msl"
        if alt_col not in self.position.columns:
            return False
        alt = self.position[alt_col]
        if len(alt) < 20:
            return False
        # Check last 10% of flight for rapid descent
        tail_start = int(len(alt) * 0.9)
        tail = alt.iloc[tail_start:]
        if tail.empty:
            return False
        alt_drop = tail.iloc[0] - tail.iloc[-1]
        return bool(alt_drop > 5.0)  # >5m drop in last 10% of flight
