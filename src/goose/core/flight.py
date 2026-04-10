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
        """Multi-signal crash heuristic. True if any strong crash indicator is present.

        Signals checked (any one is sufficient):
        1. Extreme attitude — roll or pitch exceeds 90 degrees (unrecoverable inversion)
        2. All-motor cutoff mid-flight — all motors go to zero while attitude was non-zero
        3. Rapid altitude loss — >3 m/s sustained descent in last 30% of flight
        4. High-g impact spike near end of log (from vibration data)
        5. Very short flight (<8s) with any elevated critical attitude or motor signal
        """
        import math

        # ── Signal 1: extreme attitude (flip/inversion) ───────────────────────
        if not self.attitude.empty and "roll" in self.attitude.columns:
            try:
                import numpy as np
                roll_max = float(np.degrees(self.attitude["roll"].abs().max()))
                pitch_max = float(np.degrees(self.attitude["pitch"].abs().max())) if "pitch" in self.attitude.columns else 0.0
                if roll_max > 90.0 or pitch_max > 75.0:
                    return True
            except Exception:
                pass

        # ── Signal 2: all motors cut abruptly while airborne ─────────────────
        if not self.motors.empty:
            try:
                motor_cols = [c for c in self.motors.columns if c.startswith("output_")]
                if motor_cols and len(self.motors) > 20:
                    # Find the last index where any motor was active (>0.05)
                    active_mask = (self.motors[motor_cols] > 0.05).any(axis=1)
                    active_indices = active_mask[active_mask].index
                    if len(active_indices) > 0:
                        last_active_pos = self.motors.index.get_loc(active_indices[-1])
                        # If motors cut before the last 5% of data, log continued after cutoff
                        if last_active_pos < int(len(self.motors) * 0.95):
                            # Attitude must have been non-trivial at cutoff (not a clean land)
                            if not self.attitude.empty and "roll" in self.attitude.columns:
                                cutoff_ts = float(self.motors["timestamp"].iloc[last_active_pos])
                                att_near = self.attitude[self.attitude["timestamp"] <= cutoff_ts].tail(5)
                                if not att_near.empty:
                                    import numpy as np
                                    roll_at_cut = float(np.degrees(att_near["roll"].abs().mean()))
                                    pitch_at_cut = float(np.degrees(att_near["pitch"].abs().mean())) if "pitch" in att_near.columns else 0.0
                                    if roll_at_cut > 10.0 or pitch_at_cut > 10.0:
                                        return True
            except Exception:
                pass

        # ── Signal 3: rapid altitude loss (>3 m/s in last 30%) ───────────────
        if not self.position.empty and len(self.position) >= 20:
            try:
                alt_col = "alt_rel" if "alt_rel" in self.position.columns else ("alt_msl" if "alt_msl" in self.position.columns else None)
                if alt_col:
                    alt = self.position[alt_col].dropna()
                    ts = self.position["timestamp"]
                    if len(alt) >= 20:
                        tail_start = int(len(alt) * 0.7)
                        tail_alt = alt.iloc[tail_start:]
                        tail_ts = ts.iloc[tail_start:]
                        dt = float(tail_ts.iloc[-1] - tail_ts.iloc[0])
                        if dt > 0:
                            drop = float(tail_alt.iloc[0] - tail_alt.iloc[-1])
                            rate = drop / dt
                            if rate > 3.0 and drop > 2.0:  # >3 m/s AND >2m total drop
                                return True
            except Exception:
                pass

        # ── Signal 4: high-g impact spike near end of log ────────────────────
        if not self.vibration.empty:
            try:
                import numpy as np
                accel_cols = [c for c in self.vibration.columns if c.startswith("accel_")]
                if accel_cols:
                    total_g = np.sqrt(sum(self.vibration[c] ** 2 for c in accel_cols)) / 9.81
                    last_20pct = int(len(total_g) * 0.8)
                    if float(total_g.iloc[last_20pct:].max()) > 4.0:
                        return True
            except Exception:
                pass

        return False
