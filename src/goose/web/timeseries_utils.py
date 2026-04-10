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
    indices = (
        [int(i * stride) for i in range(len(ts_ds))]
        if stride > 1
        else list(range(len(ts)))
    )

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
    alt_list = df["alt_rel"].tolist() if "alt_rel" in df.columns else (
        df["alt_msl"].tolist() if "alt_msl" in df.columns else [0.0] * len(lat_list)
    )
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
    alt_list = df["alt_rel"].tolist() if "alt_rel" in df.columns else (
        df["alt_msl"].tolist() if "alt_msl" in df.columns else [0.0] * len(lat_list)
    )

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
