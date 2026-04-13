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

    rate_ctrl_status: pd.DataFrame = field(default_factory=_empty_df)
    # PID integrators: rollspeed_integ, pitchspeed_integ, yawspeed_integ

    failure_detector: pd.DataFrame = field(default_factory=_empty_df)
    # Failure detector flags (0/1): fd_roll, fd_pitch, fd_battery, fd_imbalanced_prop, fd_motor_failure

    hover_thrust: pd.DataFrame = field(default_factory=_empty_df)
    # Hover thrust estimate: hover_thrust, hover_thrust_var, valid

    imu_status: pd.DataFrame = field(default_factory=_empty_df)
    # IMU health: accel_clipping_total, gyro_clipping_total, accel_vib_metric, gyro_vib_metric

    estimator_bias: pd.DataFrame = field(default_factory=_empty_df)
    # EKF sensor bias: accel_bias_0..2, gyro_bias_0..2, mag_bias_0..2

    control_allocator: pd.DataFrame = field(default_factory=_empty_df)
    # Mixer saturation: unallocated_thrust, unallocated_torque_x/y/z, handled_motor_failure_mask

    esc_status: pd.DataFrame = field(default_factory=_empty_df)
    # ESC telemetry: esc_rpm_{n}, esc_voltage_{n}, esc_current_{n} for each ESC (up to 8)

    ekf_innovations: pd.DataFrame = field(default_factory=_empty_df)
    # EKF innovation test ratios: innovation_vel_pos, innovation_mag, innovation_tas

    distance_sensor: pd.DataFrame = field(default_factory=_empty_df)
    # Distance sensor: current_distance, min_distance, max_distance, signal_quality

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

    def crash_assessment(self) -> dict:
        """Multi-signal crash confidence assessment.

        Returns a dict with:
            confidence: float 0.0–1.0  (combined evidence weight)
            signals:    list[str]       (which signals fired and why)
            crashed:    bool            (confidence >= 0.60)

        Signal weights (independent — combined via 1 - prod(1 - w)):
            extreme_attitude:  0.95  roll >90° or pitch >75° (inversion)
            motor_cutoff:      0.75  motors → 0 mid-flight, attitude was tilted >15°
            altitude_freefall: 0.78  >5 m/s drop in last 30% AND >3 m total
            impact_spike:      0.72  >6g in last 20% of vibration data

        Conservative thresholds prevent labeling clean landings or ground
        tests as crashes. Confidence <0.60 → not classified as crash.
        """
        try:
            import numpy as np
        except ImportError:
            return {"confidence": 0.0, "signals": [], "crashed": False}

        weights: list[float] = []
        signals: list[str] = []

        # ── Signal 1: extreme attitude (flip / inversion) ─────────────────────
        if not self.attitude.empty and "roll" in self.attitude.columns:
            try:
                roll_max = float(np.degrees(self.attitude["roll"].abs().max()))
                pitch_max = float(np.degrees(self.attitude["pitch"].abs().max())) if "pitch" in self.attitude.columns else 0.0
                if roll_max > 90.0:
                    weights.append(0.95)
                    signals.append(f"extreme_attitude: roll {roll_max:.0f}° (inversion)")
                elif pitch_max > 75.0:
                    weights.append(0.90)
                    signals.append(f"extreme_attitude: pitch {pitch_max:.0f}°")
            except Exception:  # noqa: BLE001, S110 — resilience: never let signal extraction abort crash scoring
                pass

        # ── Signal 2: motors cut abruptly while tilted (not a clean land) ─────
        if not self.motors.empty:
            try:
                motor_cols = [c for c in self.motors.columns if c.startswith("output_")]
                if motor_cols and len(self.motors) > 30:
                    active_mask = (self.motors[motor_cols] > 0.05).any(axis=1)
                    active_indices = active_mask[active_mask].index
                    if len(active_indices) > 0:
                        last_active_pos = self.motors.index.get_loc(active_indices[-1])
                        cutoff_frac = last_active_pos / len(self.motors)
                        if cutoff_frac < 0.92:  # motors died before last 8% of log
                            if not self.attitude.empty and "roll" in self.attitude.columns:
                                cutoff_ts = float(self.motors["timestamp"].iloc[last_active_pos])
                                att_near = self.attitude[self.attitude["timestamp"] <= cutoff_ts].tail(5)
                                if not att_near.empty:
                                    roll_c = float(np.degrees(att_near["roll"].abs().mean()))
                                    pitch_c = float(np.degrees(att_near["pitch"].abs().mean())) if "pitch" in att_near.columns else 0.0
                                    tilt = max(roll_c, pitch_c)
                                    if tilt > 15.0:  # raised from 10° to reduce false positives
                                        weights.append(0.75)
                                        signals.append(f"motor_cutoff: motors stopped at {cutoff_frac:.0%} of log, tilt={tilt:.0f}°")
            except Exception:  # noqa: BLE001, S110 — resilience: never let signal extraction abort crash scoring
                pass

        # ── Signal 3: rapid altitude freefall (conservative thresholds) ───────
        if not self.position.empty and len(self.position) >= 30:
            try:
                alt_col = "alt_rel" if "alt_rel" in self.position.columns else ("alt_msl" if "alt_msl" in self.position.columns else None)
                if alt_col:
                    alt = self.position[alt_col].dropna()
                    ts = self.position["timestamp"]
                    if len(alt) >= 30:
                        # Must have achieved meaningful altitude first
                        alt_peak = float(alt.max())
                        if alt_peak > 3.0:  # only flag if aircraft actually flew
                            tail_start = int(len(alt) * 0.7)
                            tail_alt = alt.iloc[tail_start:]
                            tail_ts = ts.iloc[tail_start:]
                            dt = float(tail_ts.iloc[-1] - tail_ts.iloc[0])
                            if dt > 0:
                                drop = float(tail_alt.iloc[0] - tail_alt.iloc[-1])
                                rate = drop / dt
                                if rate > 5.0 and drop > 3.0:  # raised from 3m/s & 2m
                                    weights.append(0.78)
                                    signals.append(f"altitude_freefall: {rate:.1f} m/s descent, {drop:.1f} m drop")
            except Exception:  # noqa: BLE001, S110 — resilience: never let signal extraction abort crash scoring
                pass

        # ── Signal 4: high-g impact spike near end of log ─────────────────────
        if not self.vibration.empty:
            try:
                accel_cols = [c for c in self.vibration.columns if c.startswith("accel_")]
                if accel_cols and len(self.vibration) > 20:
                    total_g = np.sqrt(sum(self.vibration[c] ** 2 for c in accel_cols)) / 9.81
                    last_20pct = int(len(total_g) * 0.8)
                    peak_g = float(total_g.iloc[last_20pct:].max())
                    if peak_g > 6.0:  # raised from 4g to reduce false positives
                        weights.append(0.72)
                        signals.append(f"impact_spike: {peak_g:.1f}g in last 20% of log")
            except Exception:  # noqa: BLE001, S110 — resilience: never let signal extraction abort crash scoring
                pass

        # ── Combine signals (independent evidence model) ───────────────────────
        if not weights:
            confidence = 0.0
        else:
            not_crash_prob = 1.0
            for w in weights:
                not_crash_prob *= 1.0 - w
            confidence = round(1.0 - not_crash_prob, 3)

        return {
            "confidence": confidence,
            "signals": signals,
            "crashed": confidence >= 0.60,
        }

    @property
    def crashed(self) -> bool:
        """True if crash confidence >= 0.60. See crash_assessment() for detail."""
        return self.crash_assessment()["crashed"]

    @property
    def crash_confidence(self) -> float:
        """Float 0.0–1.0 indicating crash evidence strength. See crash_assessment()."""
        return self.crash_assessment()["confidence"]

    @property
    def crash_signals(self) -> list[str]:
        """List of signal descriptions that contributed to crash_confidence."""
        return self.crash_assessment()["signals"]
