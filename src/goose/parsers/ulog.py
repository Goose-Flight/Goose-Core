"""PX4 ULog parser — converts .ulg files into the normalized Flight dataclass.

Sprint 3: parse() now returns ParseResult with full ParseDiagnostics and Provenance.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyulog import ULog

from goose import __version__ as _engine_version
from goose.core.flight import (
    Flight,
    FlightEvent,
    FlightMetadata,
    ModeChange,
)
from goose.forensics.models import Provenance
from goose.parsers.base import BaseParser
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult, StreamCoverage

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

    def parse(self, filepath: str | Path) -> ParseResult:
        """Parse a .ulg file and return a ParseResult with diagnostics and provenance.

        Never raises — all errors are captured in ParseResult.diagnostics.errors.
        """
        filepath = Path(filepath)
        diag = ParseDiagnostics(
            parser_selected="ULogParser",
            parser_version=_engine_version,
            detected_format="ulog",
            format_confidence=1.0,
            supported=True,
            parse_started_at=datetime.now().replace(microsecond=0),
        )
        t0 = time.monotonic()

        if not filepath.exists():
            diag.errors.append(f"File not found: {filepath}")
            diag.parser_confidence = 0.0
            return ParseResult.failure(diag)

        try:
            ulog = ULog(str(filepath))
        except (OSError, ValueError, RuntimeError) as exc:
            diag.errors.append(f"ULog open failed: {exc}")
            diag.parser_confidence = 0.0
            diag.parse_completed_at = datetime.now().replace(microsecond=0)
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        start_us = ulog.start_timestamp

        # --- Stream coverage audit -----------------------------------------
        present_topics = {ds.name for ds in ulog.data_list}
        diag.parse_artifacts = {"topics_present": sorted(present_topics)}

        STREAM_MAP = {
            "vehicle_local_position": "position",
            "vehicle_local_position_setpoint": "position_setpoint",
            "vehicle_global_position": "global_position",
            "vehicle_velocity_setpoint": "velocity_setpoint",
            "vehicle_attitude": "attitude",
            "vehicle_attitude_setpoint": "attitude_setpoint",
            "vehicle_rates_setpoint": "attitude_rate_setpoint",
            "vehicle_angular_velocity": "attitude_rate",
            "battery_status": "battery",
            "vehicle_gps_position": "gps",
            "sensor_gps": "gps (alt)",
            "actuator_outputs": "motors",
            "actuator_motors": "motors (alt)",
            "sensor_combined": "vibration",
            "sensor_accel": "vibration (alt)",
            "input_rc": "rc_input",
            "estimator_status": "ekf",
            "estimator_sensor_bias": "ekf (alt)",
            "vehicle_status": "mode_changes",
            "cpuload": "cpu",
        }
        coverage: list[StreamCoverage] = []
        missing: list[str] = []
        for topic, label in STREAM_MAP.items():
            df = _topic_to_df(ulog, topic)
            if df is not None:
                coverage.append(StreamCoverage(
                    stream_name=label,
                    present=True,
                    row_count=len(df),
                ))
            else:
                coverage.append(StreamCoverage(stream_name=label, present=False))
                missing.append(label)

        diag.stream_coverage = coverage
        diag.missing_streams = missing

        # Warn for important missing streams
        if "battery" in missing:
            diag.warnings.append("Battery stream missing — battery analysis will be skipped.")
        if "gps" in missing and "gps (alt)" in missing:
            diag.warnings.append("GPS stream missing — position analysis will be incomplete.")
        if "mode_changes" in missing:
            diag.warnings.append("vehicle_status missing — mode change extraction unavailable.")
        if "ekf" in missing and "ekf (alt)" in missing:
            diag.warnings.append("EKF stream missing — estimator analysis unavailable.")

        # --- Timebase check ------------------------------------------------
        duration_us = ulog.last_timestamp - ulog.start_timestamp
        duration_sec = duration_us / 1e6
        if duration_sec < 1.0:
            diag.timebase_anomalies.append(
                f"Log duration is very short ({duration_sec:.2f}s). "
                "Timestamps may be unreliable."
            )
        if ulog.start_timestamp == 0:
            diag.timebase_anomalies.append(
                "Log start timestamp is 0 — absolute time reference unavailable."
            )

        # --- Corruption / logged errors ------------------------------------
        for msg in ulog.logged_messages:
            log_level = msg.log_level if hasattr(msg, "log_level") else 6
            if isinstance(log_level, int) and log_level <= 3:
                diag.corruption_indicators.append(
                    f"Critical log message at {(msg.timestamp - start_us)/1e6:.1f}s: {msg.message}"
                )
            elif isinstance(log_level, str) and log_level.lower() in ("emergency", "alert", "critical"):
                diag.corruption_indicators.append(
                    f"Critical log message: {msg.message}"
                )

        # --- Assumptions ---------------------------------------------------
        diag.assumptions.append(
            "Timestamps are assumed monotonically increasing from log start."
        )
        if "gps" in missing and "gps (alt)" not in missing:
            diag.assumptions.append(
                "Using sensor_gps as GPS source (vehicle_gps_position not present)."
            )

        # --- Extract all streams -------------------------------------------
        try:
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
            manual_control = self._extract_manual_control(ulog, start_us)
            actuator_controls = self._extract_actuator_controls(ulog, start_us)
            magnetometer = self._extract_magnetometer(ulog, start_us)
            airspeed = self._extract_airspeed(ulog, start_us)
            wind = self._extract_wind(ulog, start_us)
            rc_channels = self._extract_rc_channels(ulog, start_us)
            barometer = self._extract_barometer(ulog, start_us)
            raw_gyro = self._extract_raw_gyro(ulog, start_us)
            raw_accel = self._extract_raw_accel(ulog, start_us)
            mode_changes = self._extract_mode_changes(ulog, start_us)
            events = self._extract_events(ulog, start_us)
            parameters = self._extract_parameters(ulog)
            primary_mode = self._compute_primary_mode(mode_changes, metadata.duration_sec)
            rate_ctrl_status = self._extract_rate_ctrl_status(ulog, start_us)
            failure_detector = self._extract_failure_detector(ulog, start_us)
            hover_thrust = self._extract_hover_thrust(ulog, start_us)
            imu_status = self._extract_imu_status(ulog, start_us)
            estimator_bias = self._extract_estimator_bias(ulog, start_us)
            control_allocator = self._extract_control_allocator(ulog, start_us)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            diag.errors.append(f"Extraction failed mid-parse: {exc}")
            diag.parser_confidence = 0.0
            diag.parse_completed_at = datetime.now().replace(microsecond=0)
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        flight = Flight(
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
            manual_control=manual_control,
            actuator_controls=actuator_controls,
            magnetometer=magnetometer,
            airspeed=airspeed,
            wind=wind,
            rc_channels=rc_channels,
            barometer=barometer,
            raw_gyro=raw_gyro,
            raw_accel=raw_accel,
            mode_changes=mode_changes,
            events=events,
            parameters=parameters,
            primary_mode=primary_mode,
            rate_ctrl_status=rate_ctrl_status,
            failure_detector=failure_detector,
            hover_thrust=hover_thrust,
            imu_status=imu_status,
            estimator_bias=estimator_bias,
            control_allocator=control_allocator,
        )

        # --- Finalize diagnostics ------------------------------------------
        # Parser confidence scoring — see ParseDiagnostics class docstring for
        # the full semantics.  This is parse/data-quality confidence ONLY, not
        # root-cause confidence.  Do not use this value to score hypotheses.
        #
        # Scoring table (v1, matches contract_version "1.0"):
        #   Base:                                     1.0
        #   Each critical stream absent
        #     (position, attitude, battery, gps):    −0.15 each
        #   Each corruption indicator (max 3):       −0.10 each
        #   Any timebase anomaly:                    −0.05 (flat)
        #   Floor:                                    0.0
        #
        # Critical streams are those whose absence makes core analysis
        # impossible or unreliable for crash/anomaly investigation.
        # Adding a stream to this set is a contract_version-breaking change.
        confidence = 1.0
        critical_missing = {"position", "attitude", "battery", "gps"}
        for stream in missing:
            if stream in critical_missing:
                confidence -= 0.15
        if diag.corruption_indicators:
            confidence -= 0.10 * min(len(diag.corruption_indicators), 3)
        if diag.timebase_anomalies:
            confidence -= 0.05
        diag.parser_confidence = max(0.0, round(confidence, 2))
        diag.parse_completed_at = datetime.now().replace(microsecond=0)
        diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)

        # --- Provenance ---------------------------------------------------
        provenance = Provenance(
            source_evidence_id="",  # caller fills this in when evidence_id is known
            parser_name="ULogParser",
            parser_version=_engine_version,
            detected_format="ulog",
            parsed_at=diag.parse_started_at,
            transformation_chain=["raw_ulg -> canonical_flight"],
            engine_version=_engine_version,
            assumptions=list(diag.assumptions),
        )

        return ParseResult(
            flight=flight,
            diagnostics=diag,
            provenance=provenance,
            parse_artifacts={"topics_present": sorted(present_topics)},
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

    def _extract_manual_control(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract manual control setpoint (stick inputs)."""
        df = _topic_to_df(ulog, "manual_control_setpoint")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("x", "x"), ("y", "y"), ("r", "r"), ("z", "z"), ("throttle", "z")
        ]:
            if raw in df.columns and name not in cols:
                cols[name] = df[raw]
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_actuator_controls(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract actuator control demands before mixing."""
        df = _topic_to_df(ulog, "actuator_controls_0")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for i, name in enumerate(["roll", "pitch", "yaw", "thrust"]):
            col = f"control[{i}]"
            if col in df.columns:
                cols[name] = df[col]
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_magnetometer(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract magnetometer (compass) data."""
        df = _topic_to_df(ulog, "vehicle_magnetometer")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("magnetometer_ga[0]", "mag_x"),
            ("magnetometer_ga[1]", "mag_y"),
            ("magnetometer_ga[2]", "mag_z"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw]
        if not cols:
            return pd.DataFrame()
        if "mag_x" in cols and "mag_y" in cols:
            cols["heading_deg"] = np.degrees(np.arctan2(cols["mag_y"], cols["mag_x"]))
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_airspeed(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract airspeed (fixed-wing)."""
        df = _topic_to_df(ulog, "airspeed")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("indicated_airspeed_m_s", "indicated"),
            ("true_airspeed_m_s", "true_airspeed"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw]
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_wind(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract wind estimate."""
        df = None
        for topic in ["wind_estimate", "wind"]:
            df = _topic_to_df(ulog, topic)
            if df is not None and not df.empty:
                break
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("windspeed_east", "wind_x"),
            ("windspeed_north", "wind_y"),
            ("var_vert", "wind_z"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw]
        if not cols:
            return pd.DataFrame()
        if "wind_x" in cols and "wind_y" in cols:
            cols["wind_speed"] = np.sqrt(cols["wind_x"] ** 2 + cols["wind_y"] ** 2)
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_rc_channels(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract individual RC channel values."""
        df = _topic_to_df(ulog, "rc_channels")
        if df is None or df.empty:
            df = _topic_to_df(ulog, "input_rc")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for i in range(8):
            col = f"channels[{i}]"
            if col in df.columns:
                cols[f"chan{i + 1}"] = df[col]
        if "rssi" in df.columns:
            cols["rssi"] = df["rssi"]
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_barometer(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract raw barometer data."""
        df = _topic_to_df(ulog, "sensor_baro")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("pressure", "pressure_pa"),
            ("temperature", "temperature_c"),
            ("altitude", "baro_alt_meter"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw]
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_raw_gyro(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract high-rate gyroscope data (rad/s → deg/s)."""
        df = _topic_to_df(ulog, "sensor_combined")
        if df is None or df.empty:
            df = _topic_to_df(ulog, "vehicle_imu")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("gyro_rad[0]", "gyro_x"),
            ("gyro_rad[1]", "gyro_y"),
            ("gyro_rad[2]", "gyro_z"),
        ]:
            if raw in df.columns:
                cols[name] = np.degrees(df[raw])
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_raw_accel(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract high-rate accelerometer data (m/s²)."""
        df = _topic_to_df(ulog, "sensor_combined")
        if df is None or df.empty:
            df = _topic_to_df(ulog, "vehicle_imu")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("accelerometer_m_s2[0]", "accel_x"),
            ("accelerometer_m_s2[1]", "accel_y"),
            ("accelerometer_m_s2[2]", "accel_z"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw]
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
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

    def _extract_rate_ctrl_status(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract PID integrator values from rate_ctrl_status."""
        df = _topic_to_df(ulog, "rate_ctrl_status")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("rollspeed_integ", "rollspeed_integ"),
            ("pitchspeed_integ", "pitchspeed_integ"),
            ("yawspeed_integ", "yawspeed_integ"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw].astype(float)
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_failure_detector(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract failure detector boolean flags from failure_detector_status."""
        df = _topic_to_df(ulog, "failure_detector_status")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        # PX4 field name for motor failure varies: fd_motor or fd_motor_failure
        fd_motor_col = next(
            (c for c in ["fd_motor_failure", "fd_motor"] if c in df.columns), None
        )
        for raw, name in [
            ("fd_roll", "fd_roll"),
            ("fd_pitch", "fd_pitch"),
            ("fd_battery", "fd_battery"),
            ("fd_imbalanced_prop", "fd_imbalanced_prop"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw].astype(int)
        if fd_motor_col is not None:
            cols["fd_motor_failure"] = df[fd_motor_col].astype(int)
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_hover_thrust(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract hover thrust trend from hover_thrust_estimate."""
        df = _topic_to_df(ulog, "hover_thrust_estimate")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("hover_thrust", "hover_thrust"),
            ("hover_thrust_var", "hover_thrust_var"),
            ("valid", "valid"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw].astype(float)
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_imu_status(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract IMU health metrics from vehicle_imu_status."""
        df = _topic_to_df(ulog, "vehicle_imu_status")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}

        # Accel clipping: may be scalar or array fields (accel_clipping[0..N])
        clip_cols = [c for c in df.columns if c.startswith("accel_clipping")]
        if clip_cols:
            cols["accel_clipping_total"] = sum(df[c] for c in clip_cols).astype(float)
        elif "accel_clipping" in df.columns:
            cols["accel_clipping_total"] = df["accel_clipping"].astype(float)

        # Gyro clipping: same pattern
        gyro_clip_cols = [c for c in df.columns if c.startswith("gyro_clipping")]
        if gyro_clip_cols:
            cols["gyro_clipping_total"] = sum(df[c] for c in gyro_clip_cols).astype(float)
        elif "gyro_clipping" in df.columns:
            cols["gyro_clipping_total"] = df["gyro_clipping"].astype(float)

        for raw, name in [
            ("accel_vibration_metric", "accel_vib_metric"),
            ("gyro_vibration_metric", "gyro_vib_metric"),
            ("accel_error_count", "accel_error_count"),
            ("gyro_error_count", "gyro_error_count"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw].astype(float)

        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_estimator_bias(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract EKF sensor bias estimates from estimator_sensor_bias."""
        df = _topic_to_df(ulog, "estimator_sensor_bias")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        # PX4 ULog names these accel_bias[0], gyro_bias[0], mag_bias[0]
        for axis in range(3):
            for prefix, out_prefix in [
                ("accel_bias", "accel_bias"),
                ("gyro_bias", "gyro_bias"),
                ("mag_bias", "mag_bias"),
            ]:
                raw = f"{prefix}[{axis}]"
                name = f"{out_prefix}_{axis}"
                if raw in df.columns:
                    cols[name] = df[raw].astype(float)
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

    def _extract_control_allocator(self, ulog: ULog, start_us: int) -> pd.DataFrame:
        """Extract mixer saturation data from control_allocator_status."""
        df = _topic_to_df(ulog, "control_allocator_status")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _us_to_sec(df, start_us)
        cols: dict[str, Any] = {}
        for raw, name in [
            ("unallocated_thrust", "unallocated_thrust"),
            ("unallocated_torque[0]", "unallocated_torque_x"),
            ("unallocated_torque[1]", "unallocated_torque_y"),
            ("unallocated_torque[2]", "unallocated_torque_z"),
            ("handled_motor_failure_mask", "handled_motor_failure_mask"),
        ]:
            if raw in df.columns:
                cols[name] = df[raw].astype(float)
        if not cols:
            return pd.DataFrame()
        result = pd.DataFrame(cols)
        result.insert(0, "timestamp", df["timestamp"])
        return result

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
