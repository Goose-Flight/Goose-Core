"""Shared timeseries extraction utilities for the Goose web layer.

Used by both the case analysis routes and the Quick Analysis cockpit to
extract downsampled chart-ready data from a parsed Flight object.
"""

from __future__ import annotations

import math
from typing import Any


def downsample(arr: list, max_points: int = 2000) -> list:
    """Downsample a list to max_points using stride-based selection."""
    if len(arr) <= max_points:
        return arr
    stride = len(arr) / max_points
    return [arr[int(i * stride)] for i in range(max_points)]


def safe_val(v: Any) -> Any:
    """Convert numpy/pandas values to JSON-safe Python types."""
    if v is None:
        return None
    try:
        import numpy as np

        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            if np.isnan(v) or np.isinf(v):
                return None
            return float(v)
        if isinstance(v, np.bool_):
            return bool(v)
    except (ImportError, TypeError, ValueError):
        pass
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
    return v


def df_to_series(
    df: Any,
    columns: list[str] | None = None,
    max_points: int = 2000,
) -> dict[str, list] | None:
    """Convert a pandas DataFrame to JSON-ready dict of downsampled arrays.

    Returns {"timestamps": [...], "col1": [...], "col2": [...]} or None if
    the dataframe is empty or lacks a timestamp column.
    """
    if df is None or df.empty:
        return None

    if columns is None:
        columns = [c for c in df.columns if c != "timestamp"]

    if "timestamp" not in df.columns or not columns:
        return None

    result: dict[str, list] = {}
    ts = df["timestamp"].tolist()
    ts_ds = downsample(ts, max_points)
    result["timestamps"] = [safe_val(t) for t in ts_ds]

    stride = len(ts) / len(ts_ds) if len(ts) > max_points else 1
    indices = [int(i * stride) for i in range(len(ts_ds))] if stride > 1 else list(range(len(ts)))

    for col in columns:
        if col in df.columns:
            vals = df[col].tolist()
            result[col] = [safe_val(vals[i]) for i in indices]

    return result


def extract_timeseries(flight: Any) -> dict[str, Any]:
    """Extract downsampled time-series data from a Flight for frontend charting.

    Returns a dict with keys: altitude, battery, motors, attitude,
    attitude_setpoint, vibration, gps, ekf, rc, velocity, mode_changes, events.
    Only keys with available data are included (except mode_changes and events
    which are always present as empty lists if unavailable).
    """
    ts: dict[str, Any] = {}

    # Altitude
    pos = df_to_series(flight.position, ["alt_rel", "alt_msl", "lat", "lon"])
    if pos:
        ts["altitude"] = pos

    # Battery
    bat = df_to_series(flight.battery, ["voltage", "current", "remaining_pct"])
    if bat:
        ts["battery"] = bat

    # Motors
    if not flight.motors.empty:
        motor_cols = [c for c in flight.motors.columns if c.startswith("output_")]
        mot = df_to_series(flight.motors, motor_cols)
        if mot:
            ts["motors"] = mot

    # Attitude (convert radians → degrees for display)
    if not flight.attitude.empty:
        import numpy as np

        att_df = flight.attitude.copy()
        for col in ["roll", "pitch", "yaw"]:
            if col in att_df.columns:
                att_df[col] = np.degrees(att_df[col])
        att = df_to_series(att_df, ["roll", "pitch", "yaw"])
        if att:
            ts["attitude"] = att

    # Attitude setpoint (convert radians → degrees)
    if not flight.attitude_setpoint.empty:
        import numpy as np

        sp_df = flight.attitude_setpoint.copy()
        for col in ["roll", "pitch", "yaw"]:
            if col in sp_df.columns:
                sp_df[col] = np.degrees(sp_df[col])
        sp = df_to_series(sp_df, ["roll", "pitch", "yaw"])
        if sp:
            ts["attitude_setpoint"] = sp

    # Vibration
    vib = df_to_series(flight.vibration, ["accel_x", "accel_y", "accel_z"])
    if vib:
        ts["vibration"] = vib

    # GPS
    gps = df_to_series(flight.gps, ["satellites", "hdop", "fix_type"])
    if gps:
        ts["gps"] = gps

    # EKF (cap columns to avoid payload bloat)
    if not flight.ekf.empty:
        ekf_cols = [c for c in flight.ekf.columns if c != "timestamp"][:8]
        ekf = df_to_series(flight.ekf, ekf_cols)
        if ekf:
            ts["ekf"] = ekf

    # RC signal
    if not flight.rc_input.empty:
        rc = df_to_series(flight.rc_input, ["rssi"])
        if rc:
            ts["rc"] = rc

    # Velocity
    vel = df_to_series(flight.velocity, ["vx", "vy", "vz"])
    if vel:
        ts["velocity"] = vel

    # Velocity setpoint
    vel_sp = df_to_series(flight.velocity_setpoint, ["vx", "vy", "vz"])
    if vel_sp:
        ts["velocity_setpoint"] = vel_sp

    # Attitude rate (deg/s)
    if not flight.attitude_rate.empty:
        import numpy as np

        ar_df = flight.attitude_rate.copy()
        for col in ["roll", "pitch", "yaw"]:
            if col in ar_df.columns:
                ar_df[col] = np.degrees(ar_df[col])
        ar = df_to_series(ar_df, ["roll", "pitch", "yaw"])
        if ar:
            ts["attitude_rate"] = ar

    # Attitude rate setpoint (deg/s)
    if not flight.attitude_rate_setpoint.empty:
        import numpy as np

        arsp_df = flight.attitude_rate_setpoint.copy()
        for col in ["roll", "pitch", "yaw"]:
            if col in arsp_df.columns:
                arsp_df[col] = np.degrees(arsp_df[col])
        arsp = df_to_series(arsp_df, ["roll", "pitch", "yaw"])
        if arsp:
            ts["attitude_rate_setpoint"] = arsp

    # CPU load
    if not flight.cpu.empty:
        cpu_cols = [c for c in flight.cpu.columns if c != "timestamp"][:4]
        cpu = df_to_series(flight.cpu, cpu_cols)
        if cpu:
            ts["cpu"] = cpu

    # Manual control (stick inputs)
    if not flight.manual_control.empty:
        mc = df_to_series(flight.manual_control, ["x", "y", "r", "z"])
        if mc:
            ts["manual_control"] = mc

    # Actuator controls (demand before mixing)
    if not flight.actuator_controls.empty:
        ac = df_to_series(flight.actuator_controls, ["roll", "pitch", "yaw", "thrust"])
        if ac:
            ts["actuator_controls"] = ac

    # Magnetometer
    if not flight.magnetometer.empty:
        mag_cols = [c for c in flight.magnetometer.columns if c != "timestamp"]
        mag = df_to_series(flight.magnetometer, mag_cols)
        if mag:
            ts["magnetometer"] = mag

    # Airspeed (fixed wing)
    if not flight.airspeed.empty:
        asp = df_to_series(
            flight.airspeed,
            [c for c in flight.airspeed.columns if c != "timestamp"],
        )
        if asp:
            ts["airspeed"] = asp

    # Wind estimate
    if not flight.wind.empty:
        wnd = df_to_series(
            flight.wind,
            [c for c in flight.wind.columns if c != "timestamp"],
        )
        if wnd:
            ts["wind"] = wnd

    # RC channels
    if not flight.rc_channels.empty:
        rc_cols = [c for c in flight.rc_channels.columns if c != "timestamp"]
        rcc = df_to_series(flight.rc_channels, rc_cols)
        if rcc:
            ts["rc_channels"] = rcc

    # Barometer
    if not flight.barometer.empty:
        baro = df_to_series(
            flight.barometer,
            [c for c in flight.barometer.columns if c != "timestamp"],
        )
        if baro:
            ts["barometer"] = baro

    # Raw gyro
    if not flight.raw_gyro.empty:
        gyro = df_to_series(flight.raw_gyro, ["gyro_x", "gyro_y", "gyro_z"])
        if gyro:
            ts["raw_gyro"] = gyro

    # Raw accel
    if not flight.raw_accel.empty:
        racc = df_to_series(flight.raw_accel, ["accel_x", "accel_y", "accel_z"])
        if racc:
            ts["raw_accel"] = racc

    # Rate controller integrators (PID wind-up detection)
    if not flight.rate_ctrl_status.empty:
        rcs = df_to_series(
            flight.rate_ctrl_status,
            ["rollspeed_integ", "pitchspeed_integ", "yawspeed_integ"],
        )
        if rcs:
            ts["rate_ctrl_status"] = rcs

    # Failure detector timeline
    if not flight.failure_detector.empty:
        fd_cols = [c for c in flight.failure_detector.columns if c != "timestamp"]
        fd = df_to_series(flight.failure_detector, fd_cols)
        if fd:
            ts["failure_detector"] = fd

    # Hover thrust trend (motor degradation indicator)
    if not flight.hover_thrust.empty:
        ht = df_to_series(
            flight.hover_thrust,
            ["hover_thrust", "hover_thrust_var", "valid"],
        )
        if ht:
            ts["hover_thrust"] = ht

    # IMU health timeline
    if not flight.imu_status.empty:
        imu_cols = [c for c in flight.imu_status.columns if c != "timestamp"]
        imu = df_to_series(flight.imu_status, imu_cols)
        if imu:
            ts["imu_status"] = imu

    # EKF sensor bias estimates
    if not flight.estimator_bias.empty:
        eb_cols = [c for c in flight.estimator_bias.columns if c != "timestamp"]
        eb = df_to_series(flight.estimator_bias, eb_cols)
        if eb:
            ts["estimator_bias"] = eb

    # Mixer saturation / control allocator
    if not flight.control_allocator.empty:
        ca_cols = [c for c in flight.control_allocator.columns if c != "timestamp"]
        ca = df_to_series(flight.control_allocator, ca_cols)
        if ca:
            ts["control_allocator"] = ca

    # ESC telemetry (RPM, voltage, current per ESC)
    if not flight.esc_status.empty:
        esc_cols = [c for c in flight.esc_status.columns if c != "timestamp"]
        esc = df_to_series(flight.esc_status, esc_cols)
        if esc:
            ts["esc_status"] = esc

    # EKF innovation test ratios
    if not flight.ekf_innovations.empty:
        innov_cols = [c for c in flight.ekf_innovations.columns if c != "timestamp"]
        innov = df_to_series(flight.ekf_innovations, innov_cols)
        if innov:
            ts["ekf_innovations"] = innov

    # Distance sensor
    if not flight.distance_sensor.empty:
        dist = df_to_series(
            flight.distance_sensor,
            ["current_distance", "min_distance", "max_distance", "signal_quality"],
        )
        if dist:
            ts["distance_sensor"] = dist

    # Mode changes
    ts["mode_changes"] = [
        {
            "timestamp": mc.timestamp,
            "from_mode": mc.from_mode,
            "to_mode": mc.to_mode,
        }
        for mc in flight.mode_changes
    ]

    # Events
    ts["events"] = [
        {
            "timestamp": ev.timestamp,
            "type": ev.event_type,
            "severity": ev.severity,
            "message": ev.message,
        }
        for ev in flight.events
    ]

    return ts


def extract_setpoint_path(flight: Any, max_points: int = 1000) -> dict[str, Any] | None:
    """Extract position setpoint path (what the autopilot commanded) for comparison.

    Returns same structure as extract_flight_path but from position_setpoint df.
    Only returned if the setpoint df contains lat/lon columns.
    """
    pos_sp = flight.position_setpoint
    if pos_sp is None or pos_sp.empty:
        return None
    if "lat" not in pos_sp.columns or "lon" not in pos_sp.columns:
        return None

    df = pos_sp[(pos_sp["lat"] != 0) & (pos_sp["lon"] != 0)].dropna(subset=["lat", "lon"])
    if df.empty:
        return None

    lat_list = df["lat"].tolist()
    lon_list = df["lon"].tolist()
    alt_list = df["alt_rel"].tolist() if "alt_rel" in df.columns else (df["alt_msl"].tolist() if "alt_msl" in df.columns else [0.0] * len(lat_list))
    ts_list = df["timestamp"].tolist() if "timestamp" in df.columns else []

    total = len(lat_list)
    if total > max_points:
        stride = total / max_points
        indices = [int(i * stride) for i in range(max_points)]
        lat_list = [lat_list[i] for i in indices]
        lon_list = [lon_list[i] for i in indices]
        alt_list = [alt_list[i] for i in indices]
        ts_list = [ts_list[i] for i in indices] if ts_list else []

    return {
        "lat": [safe_val(v) for v in lat_list],
        "lon": [safe_val(v) for v in lon_list],
        "alt": [safe_val(v) for v in alt_list],
        "timestamps": [safe_val(v) for v in ts_list],
        "point_count": len(lat_list),
    }


def extract_flight_path(flight: Any, max_points: int = 1000) -> dict[str, Any] | None:
    """Extract a 2D flight path (lat/lon + alt) for map/path display.

    Returns None if position data is unavailable or lacks lat/lon columns.
    Returns {"lat": [...], "lon": [...], "alt": [...], "timestamps": [...]}
    downsampled to max_points.
    """
    pos = flight.position
    if pos is None or pos.empty:
        return None
    if "lat" not in pos.columns or "lon" not in pos.columns:
        return None

    # Drop rows where lat/lon are zero or NaN (typical for pre-GPS-fix rows)
    df = pos[(pos["lat"] != 0) & (pos["lon"] != 0)].dropna(subset=["lat", "lon"])
    if df.empty:
        return None

    ts_list = df["timestamp"].tolist() if "timestamp" in df.columns else []
    lat_list = df["lat"].tolist()
    lon_list = df["lon"].tolist()
    alt_list = df["alt_rel"].tolist() if "alt_rel" in df.columns else (df["alt_msl"].tolist() if "alt_msl" in df.columns else [0.0] * len(lat_list))

    # Downsample all in lockstep
    total = len(lat_list)
    if total > max_points:
        stride = total / max_points
        indices = [int(i * stride) for i in range(max_points)]
        lat_list = [lat_list[i] for i in indices]
        lon_list = [lon_list[i] for i in indices]
        alt_list = [alt_list[i] for i in indices]
        ts_list = [ts_list[i] for i in indices] if ts_list else []

    return {
        "lat": [safe_val(v) for v in lat_list],
        "lon": [safe_val(v) for v in lon_list],
        "alt": [safe_val(v) for v in alt_list],
        "timestamps": [safe_val(v) for v in ts_list],
        "point_count": len(lat_list),
    }
