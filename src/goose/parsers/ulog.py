"""PX4 ULog parser — converts .ulg files into the normalized Flight dataclass."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyulog import ULog

from goose.core.flight import (
    Flight,
    FlightEvent,
    FlightMetadata,
    ModeChange,
)
from goose.parsers.base import BaseParser

# PX4 flight mode mapping (main_state values)
PX4_MODES: dict[int, str] = {
    0: "manual",
    1: "altitude",
    2: "position",
    3: "mission",
    4: "hold",
    5: "return",
    6: "acro",
    7: "offboard",
    8: "stabilized",
    9: "rattitude",
    10: "takeoff",
    11: "land",
    12: "follow_target",
    13: "precland",
    14: "orbit",
}

# Map PX4 modes to our hierarchy levels
MODE_TO_HIERARCHY: dict[str, str] = {
    "manual": "manual",
    "acro": "manual",
    "rattitude": "manual",
    "stabilized": "stabilized",
    "altitude": "altitude",
    "position": "position",
    "hold": "position",
    "return": "position",
    "takeoff": "position",
    "land": "position",
    "precland": "position",
    "orbit": "position",
    "follow_target": "position",
    "mission": "mission",
    "offboard": "position",
}


def _topic_to_df(ulog: ULog, topic_name: str) -> pd.DataFrame | None:
    """Extract a ULog topic as a pandas DataFrame, return None if not found."""
    for dataset in ulog.data_list:
        if dataset.name == topic_name:
            data: dict[str, Any] = {}
            for field_name in dataset.data:
                data[field_name] = dataset.data[field_name]
            return pd.DataFrame(data)
    return None


def _us_to_sec(df: pd.DataFrame, start_us: int) -> pd.DataFrame:
    """Convert 'timestamp' column from microseconds to seconds relative to log start."""
    if "timestamp" in df.columns:
        df = df.copy()
        df["timestamp"] = (df["timestamp"] - start_us) / 1e6
    return df


class ULogParser(BaseParser):
    """Parser for PX4 ULog (.ulg) flight log files."""

    format_name = "ulog"
    file_extensions = [".ulg"]

    def parse(self, filepath: str | Path) -> Flight:
        """Parse a .ulg file and return a normalized Flight object."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"ULog file not found: {filepath}")

        ulog = ULog(str(filepath))
        start_us = ulog.start_timestamp

        metadata = self._extract_metadata(ulog, filepath)
        position = self._extract_position(ulog, start_us)
        position_setpoint = self._extract_position_setpoint(ulog, start_us)
        velocity = self._extract_velocity(ulog, start_us)
        velocity_setpoint = self._extract_velocity_setpoint(ulog, start_us)
        attitude = self._extract_attitude(ulog, start_us)
        attitude_setpoint = self._extract_attitude_setpoint(ulog, start_us)
        attitude_rate = self._extract_attitude_rate(ulog, start_us)
        attitude_rate_setpoint = self._extract_attitude_rate_setpoint(ulog, start_us)
        battery = self._extract_battery(ulog, start_us)
        gps = self._extract_gps(ulog, start_us)
        motors = self._extract_motors(ulog, start_us, metadata.motor_count)
        vibration = self._extract_vibration(ulog, start_us)
        rc_input = self._extract_rc_input(ulog, start_us)
        ekf = self._extract_ekf(ulog, start_us)
        cpu = self._extract_cpu(ulog, start_us)
        mode_changes = self._extract_mode_changes(ulog, start_us)
        events = self._extract_events(ulog, start_us)
        parameters = self._extract_parameters(ulog)
        primary_mode = self._compute_primary_mode(mode_changes, metadata.duration_sec)

        return Flight(
            metadata=metadata,
            position=position,
            position_setpoint=position_setpoint,
            velocity=velocity,
            velocity_setpoint=velocity_setpoint,
            attitude=attitude,
            attitude_setpoint=attitude_setpoint,
            attitude_rate=attitude_rate,
            attitude_rate_setpoint=attitude_rate_setpoint,
            battery=battery,
            gps=gps,
            motors=motors,
            vibration=vibration,
            rc_input=rc_input,
            ekf=ekf,
            cpu=cpu,
            mode_changes=mode_changes,
            events=events,
            parameters=parameters,
            primary_mode=primary_mode,
        )

    def _extract_metadata(self, ulog: ULog, filepath: Path) -> FlightMetadata:
        """Extract flight metadata from ULog header and parameters."""
        params = {p: ulog.initial_parameters[p] for p in ulog.initial_parameters}

        # Duration
        duration_us = ulog.last_timestamp - ulog.start_timestamp
        duration_sec = duration_us / 1e6

        # Start time
        start_time_utc: datetime | None = None
        gps_df = _topic_to_df(ulog, "vehicle_gps_position")
        if gps_df is None:
            gps_df = _topic_to_df(ulog, "sensor_gps")
        if gps_df is not None and "time_utc_usec" in gps_df.columns:
            utc_vals = gps_df["time_utc_usec"]
            valid = utc_vals[utc_vals > 0]
            if len(valid) > 0:
                start_time_utc = datetime.fromtimestamp(
                    int(valid.iloc[0]) / 1e6, tz=timezone.utc
                )

        # Firmware version
        fw_version = "unknown"
        if "ver_sw" in ulog.msg_info_dict:
            fw_version = str(ulog.msg_info_dict["ver_sw"])
        elif "sys_autostart" in params:
            fw_version = f"autostart_{int(params['sys_autostart'])}"

        # Vehicle type from SYS_AUTOSTART parameter
        vehicle_type = "quadcopter"
        if "MAV_TYPE" in params:
            mav_type = int(params["MAV_TYPE"])
            vehicle_type = {
                1: "fixedwing",
                2: "quadcopter",
                13: "hexcopter",
                14: "octocopter",
                19: "vtol",
                20: "vtol",
                21: "vtol",
                22: "vtol",
            }.get(mav_type, "quadcopter")

        # Motor count
        motor_count = 4
        if vehicle_type == "hexcopter":
            motor_count = 6
        elif vehicle_type == "octocopter":
            motor_count = 8
        elif vehicle_type == "fixedwing":
            motor_count = 1

        # Hardware
        hardware: str | None = None
        if "ver_hw" in ulog.msg_info_dict:
            hardware = str(ulog.msg_info_dict["ver_hw"])

        return FlightMetadata(
            source_file=str(filepath),
            autopilot="px4",
            firmware_version=fw_version,
            vehicle_type=vehicle_type,
            frame_type=None,
            hardware=hardware,
            duration_sec=duration_sec,
            start_time_utc=start_time_utc,
            log_format="ulog",
            motor_count=motor_count,
        )

    def _extract_position(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract position from vehicle_local_position or vehicle_global_position."""
        # Try global position first (has lat/lon directly)
        df = _topic_to_df(ulog, "vehicle_global_position")
        if df is not None:
            result = pd.DataFrame()
            result["timestamp"] = (df["timestamp"] - start_us) / 1e6
            result["lat"] = df["lat"] if "lat" in df.columns else np.nan
            result["lon"] = df["lon"] if "lon" in df.columns else np.nan
            result["alt_msl"] = df["alt"] if "alt" in df.columns else np.nan
            result["alt_rel"] = df["alt"] - df["alt"].iloc[0] if "alt" in df.columns else np.nan
            return result

        # Fall back to local position (NED frame)
        df = _topic_to_df(ulog, "vehicle_local_position")
        if df is not None:
            result = pd.DataFrame()
            result["timestamp"] = (df["timestamp"] - start_us) / 1e6
            # Use ref lat/lon if available to convert
            ref_lat = df["ref_lat"].iloc[0] if "ref_lat" in df.columns else 0.0
            ref_lon = df["ref_lon"].iloc[0] if "ref_lon" in df.columns else 0.0
            if "x" in df.columns and "y" in df.columns:
                # Convert NED meters to approximate lat/lon
                result["lat"] = ref_lat + df["x"] / 111320.0
                result["lon"] = ref_lon + df["y"] / (111320.0 * np.cos(np.radians(ref_lat)))
            else:
                result["lat"] = np.nan
                result["lon"] = np.nan
            result["alt_msl"] = -df["z"] if "z" in df.columns else np.nan
            result["alt_rel"] = -df["z"] - (-df["z"].iloc[0]) if "z" in df.columns else np.nan
            return result

        return pd.DataFrame()

    def _extract_position_setpoint(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract position setpoints."""
        df = _topic_to_df(ulog, "vehicle_local_position_setpoint")
        if df is None:
            df = _topic_to_df(ulog, "position_setpoint_triplet")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6
        result["lat"] = df.get("x", pd.Series(dtype=float))
        result["lon"] = df.get("y", pd.Series(dtype=float))
        result["alt"] = -df["z"] if "z" in df.columns else np.nan
        return result

    def _extract_velocity(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract velocity from vehicle_local_position."""
        df = _topic_to_df(ulog, "vehicle_local_position")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6
        result["vx"] = df["vx"] if "vx" in df.columns else np.nan
        result["vy"] = df["vy"] if "vy" in df.columns else np.nan
        result["vz"] = df["vz"] if "vz" in df.columns else np.nan
        return result

    def _extract_velocity_setpoint(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract velocity setpoints."""
        df = _topic_to_df(ulog, "vehicle_local_position_setpoint")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6
        result["vx"] = df["vx"] if "vx" in df.columns else np.nan
        result["vy"] = df["vy"] if "vy" in df.columns else np.nan
        result["vz"] = df["vz"] if "vz" in df.columns else np.nan
        return result

    def _extract_attitude(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract attitude (roll, pitch, yaw) from vehicle_attitude."""
        df = _topic_to_df(ulog, "vehicle_attitude")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6

        # Convert quaternion to Euler angles if needed
        if "q[0]" in df.columns:
            q0, q1, q2, q3 = df["q[0]"], df["q[1]"], df["q[2]"], df["q[3]"]
            result["roll"] = np.arctan2(
                2.0 * (q0 * q1 + q2 * q3),
                1.0 - 2.0 * (q1 * q1 + q2 * q2),
            )
            result["pitch"] = np.arcsin(
                np.clip(2.0 * (q0 * q2 - q3 * q1), -1.0, 1.0)
            )
            result["yaw"] = np.arctan2(
                2.0 * (q0 * q3 + q1 * q2),
                1.0 - 2.0 * (q2 * q2 + q3 * q3),
            )
        elif "rollspeed" in df.columns:
            # Some logs might have direct Euler — unlikely for PX4 but handle it
            result["roll"] = df.get("roll", pd.Series(dtype=float))
            result["pitch"] = df.get("pitch", pd.Series(dtype=float))
            result["yaw"] = df.get("yaw", pd.Series(dtype=float))
        else:
            return pd.DataFrame()

        return result

    def _extract_attitude_setpoint(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract attitude setpoints."""
        df = _topic_to_df(ulog, "vehicle_attitude_setpoint")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6

        if "q_d[0]" in df.columns:
            q0, q1, q2, q3 = df["q_d[0]"], df["q_d[1]"], df["q_d[2]"], df["q_d[3]"]
            result["roll"] = np.arctan2(
                2.0 * (q0 * q1 + q2 * q3),
                1.0 - 2.0 * (q1 * q1 + q2 * q2),
            )
            result["pitch"] = np.arcsin(
                np.clip(2.0 * (q0 * q2 - q3 * q1), -1.0, 1.0)
            )
            result["yaw"] = np.arctan2(
                2.0 * (q0 * q3 + q1 * q2),
                1.0 - 2.0 * (q2 * q2 + q3 * q3),
            )
        elif "roll_body" in df.columns:
            result["roll"] = df["roll_body"]
            result["pitch"] = df["pitch_body"]
            result["yaw"] = df["yaw_body"]
        else:
            return pd.DataFrame()

        return result

    def _extract_attitude_rate(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract angular rates from vehicle_angular_velocity or vehicle_attitude."""
        df = _topic_to_df(ulog, "vehicle_angular_velocity")
        if df is None:
            # Fall back to vehicle_attitude which sometimes has rollspeed etc.
            df = _topic_to_df(ulog, "vehicle_attitude")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6

        if "xyz[0]" in df.columns:
            result["rollspeed"] = df["xyz[0]"]
            result["pitchspeed"] = df["xyz[1]"]
            result["yawspeed"] = df["xyz[2]"]
        elif "rollspeed" in df.columns:
            result["rollspeed"] = df["rollspeed"]
            result["pitchspeed"] = df["pitchspeed"]
            result["yawspeed"] = df["yawspeed"]
        else:
            return pd.DataFrame()

        return result

    def _extract_attitude_rate_setpoint(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract angular rate setpoints."""
        df = _topic_to_df(ulog, "vehicle_rates_setpoint")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6
        result["rollspeed"] = df.get("roll", pd.Series(dtype=float))
        result["pitchspeed"] = df.get("pitch", pd.Series(dtype=float))
        result["yawspeed"] = df.get("yaw", pd.Series(dtype=float))
        return result

    def _extract_battery(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract battery data from battery_status."""
        df = _topic_to_df(ulog, "battery_status")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6
        result["voltage"] = df["voltage_v"] if "voltage_v" in df.columns else (
            df["voltage_filtered_v"] if "voltage_filtered_v" in df.columns else np.nan
        )
        result["current"] = df["current_a"] if "current_a" in df.columns else (
            df["current_filtered_a"] if "current_filtered_a" in df.columns else np.nan
        )
        result["remaining_pct"] = df["remaining"] * 100.0 if "remaining" in df.columns else np.nan
        return result

    def _extract_gps(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract GPS data."""
        df = _topic_to_df(ulog, "vehicle_gps_position")
        if df is None:
            df = _topic_to_df(ulog, "sensor_gps")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6

        # Lat/lon may be in degrees * 1e7 (integer) or direct float
        if "lat" in df.columns:
            lat_vals = df["lat"]
            if lat_vals.abs().max() > 360:
                result["lat"] = lat_vals / 1e7
            else:
                result["lat"] = lat_vals
        if "lon" in df.columns:
            lon_vals = df["lon"]
            if lon_vals.abs().max() > 360:
                result["lon"] = lon_vals / 1e7
            else:
                result["lon"] = lon_vals

        result["alt"] = df["alt"] / 1e3 if "alt" in df.columns and df["alt"].abs().max() > 10000 else (
            df.get("alt", pd.Series(dtype=float))
        )
        result["fix_type"] = df.get("fix_type", pd.Series(dtype=float))
        result["satellites"] = df.get("satellites_used", pd.Series(dtype=float))
        result["hdop"] = df["hdop"] if "hdop" in df.columns else (
            df["eph"] / 100.0 if "eph" in df.columns else np.nan
        )
        result["vdop"] = df["vdop"] if "vdop" in df.columns else (
            df["epv"] / 100.0 if "epv" in df.columns else np.nan
        )
        return result

    def _extract_motors(self, ulog: ULog, start_us: int, motor_count: int) -> pd.DataFrame:
        """Extract motor outputs and normalize to 0-1."""
        df = _topic_to_df(ulog, "actuator_outputs")
        if df is None:
            # Try actuator_motors (newer PX4 versions)
            df = _topic_to_df(ulog, "actuator_motors")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6

        if "control[0]" in df.columns:
            # actuator_motors: already normalized -1 to 1, shift to 0-1
            for i in range(motor_count):
                col = f"control[{i}]"
                if col in df.columns:
                    result[f"output_{i}"] = (df[col] + 1.0) / 2.0
        elif "output[0]" in df.columns:
            # actuator_outputs: PWM values, normalize
            for i in range(motor_count):
                col = f"output[{i}]"
                if col in df.columns:
                    vals = df[col]
                    # PWM range typically 1000-2000, normalize to 0-1
                    if vals.max() > 100:
                        result[f"output_{i}"] = (vals - 1000.0) / 1000.0
                    else:
                        result[f"output_{i}"] = vals
        else:
            return pd.DataFrame()

        return result

    def _extract_vibration(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract vibration (accelerometer) data from sensor_combined."""
        df = _topic_to_df(ulog, "sensor_combined")
        if df is None:
            df = _topic_to_df(ulog, "sensor_accel")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6

        if "accelerometer_m_s2[0]" in df.columns:
            result["accel_x"] = df["accelerometer_m_s2[0]"]
            result["accel_y"] = df["accelerometer_m_s2[1]"]
            result["accel_z"] = df["accelerometer_m_s2[2]"]
        elif "x" in df.columns:
            result["accel_x"] = df["x"]
            result["accel_y"] = df["y"]
            result["accel_z"] = df["z"]
        else:
            return pd.DataFrame()

        return result

    def _extract_rc_input(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract RC input data."""
        df = _topic_to_df(ulog, "input_rc")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6
        result["rssi"] = df.get("rssi", pd.Series(dtype=float))

        # Collect channel columns
        ch_cols = [c for c in df.columns if c.startswith("values[")]
        for col in sorted(ch_cols):
            result[col] = df[col]

        return result

    def _extract_ekf(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract EKF estimator data."""
        df = _topic_to_df(ulog, "estimator_status")
        if df is None:
            df = _topic_to_df(ulog, "estimator_sensor_bias")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6

        # Collect innovation and flag columns
        for col in df.columns:
            if col.startswith("vel_") or col.startswith("pos_") or col == "flags" or "innov" in col:
                result[col] = df[col]

        return result

    def _extract_cpu(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract CPU load data."""
        df = _topic_to_df(ulog, "cpuload")
        if df is None:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["timestamp"] = (df["timestamp"] - start_us) / 1e6
        result["load_pct"] = df["load"] * 100.0 if "load" in df.columns else np.nan
        return result

    def _extract_mode_changes(self, ulog: ULog, start_us: int) -> list[ModeChange]:
        """Extract flight mode changes from vehicle_status."""
        df = _topic_to_df(ulog, "vehicle_status")
        if df is None:
            return []

        mode_col = None
        for candidate in ["nav_state", "main_state"]:
            if candidate in df.columns:
                mode_col = candidate
                break
        if mode_col is None:
            return []

        changes: list[ModeChange] = []
        prev_mode = ""
        for _, row in df.iterrows():
            mode_val = int(row[mode_col])
            mode_name = PX4_MODES.get(mode_val, f"unknown_{mode_val}")
            if mode_name != prev_mode:
                timestamp = (row["timestamp"] - start_us) / 1e6
                changes.append(ModeChange(
                    timestamp=timestamp,
                    from_mode=prev_mode if prev_mode else "none",
                    to_mode=mode_name,
                ))
                prev_mode = mode_name

        return changes

    def _extract_events(self, ulog: ULog, start_us: int) -> list[FlightEvent]:
        """Extract events from logged messages and vehicle_command."""
        events: list[FlightEvent] = []

        # Extract from ULog logged messages
        for msg in ulog.logged_messages:
            timestamp = (msg.timestamp - start_us) / 1e6
            severity = "info"
            event_type = "info"
            log_level = msg.log_level if hasattr(msg, "log_level") else 6
            if isinstance(log_level, str):
                log_level_str = log_level.lower()
                if log_level_str in ("emergency", "alert", "critical", "error"):
                    severity = "critical"
                    event_type = "error"
                elif log_level_str in ("warning",):
                    severity = "warning"
                    event_type = "warning"
            elif isinstance(log_level, int):
                if log_level <= 3:
                    severity = "critical"
                    event_type = "error"
                elif log_level <= 4:
                    severity = "warning"
                    event_type = "warning"

            events.append(FlightEvent(
                timestamp=timestamp,
                event_type=event_type,
                severity=severity,
                message=msg.message,
            ))

        return events

    def _extract_parameters(self, ulog: ULog) -> dict[str, float]:
        """Extract all parameters from ULog header."""
        return {k: float(v) for k, v in ulog.initial_parameters.items()}

    def _compute_primary_mode(self, mode_changes: list[ModeChange], duration_sec: float) -> str:
        """Compute the most-used flight mode based on time spent in each mode."""
        if not mode_changes:
            return "manual"

        # Calculate time spent in each mode
        mode_times: Counter[str] = Counter()
        for i, mc in enumerate(mode_changes):
            end_time = mode_changes[i + 1].timestamp if i + 1 < len(mode_changes) else duration_sec
            time_in_mode = end_time - mc.timestamp
            # Map to hierarchy level
            hierarchy_mode = MODE_TO_HIERARCHY.get(mc.to_mode, "manual")
            mode_times[hierarchy_mode] += time_in_mode

        if not mode_times:
            return "manual"

        return mode_times.most_common(1)[0][0]
