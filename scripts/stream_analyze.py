#!/usr/bin/env python3
"""Stream-analyze public PX4 logs from logs.px4.io.

Downloads one log at a time, runs full Goose analysis, stores results in
SQLite, then deletes the file.  Fully resumable — already-analyzed log_ids
are skipped on every run.  Designed to scale to all 371k+ public logs.

Usage:
    python scripts/stream_analyze.py --limit 100          # first run / test
    python scripts/stream_analyze.py --limit 1000         # larger batch
    python scripts/stream_analyze.py --resume             # skip already done
    python scripts/stream_analyze.py --stats              # show DB stats only
    python scripts/stream_analyze.py --export results.csv # export DB to CSV
    python scripts/stream_analyze.py --rated-crashes-only # only logs rated as crash/not ok
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sqlite3
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGS_BASE = "https://logs.px4.io"
BROWSE_URL = f"{LOGS_BASE}/browse_data_retrieval"
DOWNLOAD_URL = f"{LOGS_BASE}/download"
USER_AGENT = "goose-flight/1.0 (research; stream-analyze)"
RATE_LIMIT_SEC = 1.2   # seconds between downloads — be polite
PAGE_SIZE = 100        # entries per listing request

DB_PATH = ROOT / "data" / "stream_results.db"

# ---------------------------------------------------------------------------
# DB schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyzed_logs (
    log_id              TEXT PRIMARY KEY,
    analyzed_at         TEXT NOT NULL,
    -- Listing metadata (from logs.px4.io API — stored for reference only, never used to classify)
    date                TEXT,
    vehicle_type_api    TEXT,
    airframe            TEXT,
    hardware_api        TEXT,
    firmware_api        TEXT,
    duration_api        TEXT,
    rating              TEXT,
    mode_api            TEXT,
    -- Parse / analysis outcome
    ok                  INTEGER NOT NULL DEFAULT 0,
    error               TEXT,
    -- Flight metadata (from parsed log)
    duration_sec        REAL,
    vehicle_type        TEXT,
    hardware            TEXT,
    firmware            TEXT,
    primary_mode        TEXT,
    motor_count         INTEGER,
    log_format          TEXT,
    -- Crash assessment (evidence-based, from telemetry only)
    crashed             INTEGER,
    crash_confidence    REAL,
    crash_signals       TEXT,
    -- Plugin results
    score               INTEGER,
    critical_count      INTEGER,
    warning_count       INTEGER,
    info_count          INTEGER,
    -- Signal availability
    has_gps             INTEGER,
    has_attitude        INTEGER,
    has_battery         INTEGER,
    has_motors          INTEGER,
    has_vibration       INTEGER,
    has_rc              INTEGER,
    has_ekf             INTEGER,
    has_cpu             INTEGER,
    has_magnetometer    INTEGER,
    has_barometer       INTEGER,
    has_airspeed        INTEGER,
    signal_streams      INTEGER,
    -- ── Raw telemetry features for re-analysis without re-download ────────────
    -- Attitude
    max_roll_deg        REAL,   -- peak absolute roll (degrees)
    max_pitch_deg       REAL,   -- peak absolute pitch (degrees)
    max_yaw_rate_dps    REAL,   -- peak yaw rate (deg/s)
    -- Attitude tracking error (setpoint vs actual)
    max_roll_err_deg    REAL,
    max_pitch_err_deg   REAL,
    -- Motors
    motor_cutoff_frac   REAL,   -- fraction through log where motors last active (0-1)
    motor_cutoff_tilt   REAL,   -- attitude tilt angle at motor cutoff (degrees)
    motor_min_avg       REAL,   -- average of per-motor minimums across flight
    motor_max_avg       REAL,   -- average of per-motor maximums
    motor_imbalance     REAL,   -- max spread between motors at any point
    -- Altitude / position
    alt_peak_m          REAL,   -- max altitude reached (relative, meters)
    alt_final_m         REAL,   -- altitude at end of log
    alt_drop_rate       REAL,   -- m/s descent in last 30% of flight
    alt_drop_m          REAL,   -- total drop in last 30% of flight
    horiz_dist_m        REAL,   -- total horizontal distance flown (GPS-derived)
    -- GPS quality
    gps_fix_min         INTEGER, -- minimum GPS fix type seen (0=no fix, 3=3D)
    gps_sat_min         INTEGER, -- minimum satellites tracked
    gps_hdop_max        REAL,    -- maximum horizontal dilution of precision
    -- Battery
    batt_v_min          REAL,   -- minimum voltage seen
    batt_v_start        REAL,   -- voltage at start of flight
    batt_v_end          REAL,   -- voltage at end of flight
    batt_drop_v         REAL,   -- total voltage drop
    batt_pct_min        REAL,   -- minimum remaining percentage
    batt_current_max    REAL,   -- peak current draw (A)
    -- Vibration / IMU
    peak_g_last20pct    REAL,   -- max g-force in last 20% of log (crash indicator)
    peak_g_overall      REAL,   -- max g-force across entire flight
    vib_rms_x           REAL,   -- RMS vibration X axis
    vib_rms_y           REAL,   -- RMS vibration Y axis
    vib_rms_z           REAL,   -- RMS vibration Z axis
    -- EKF health
    ekf_vel_innov_max   REAL,   -- max velocity innovation magnitude
    ekf_pos_innov_max   REAL,   -- max position innovation magnitude
    -- RC input
    rc_rssi_min         REAL,   -- minimum RSSI (0-1)
    rc_loss_events      INTEGER, -- number of RC signal loss events
    -- Flight events
    error_count         INTEGER, -- number of error-level events
    warning_count_evt   INTEGER, -- number of warning-level events
    failsafe_count      INTEGER, -- number of failsafe activations
    mode_change_count   INTEGER, -- total mode transitions
    -- Velocity
    vel_horiz_max       REAL,   -- max horizontal speed (m/s)
    vel_vert_max        REAL,   -- max vertical speed magnitude (m/s)
    -- CPU
    cpu_load_max        REAL,   -- peak CPU load (0-1)
    cpu_load_avg        REAL    -- average CPU load
);

CREATE INDEX IF NOT EXISTS idx_analyzed_at     ON analyzed_logs (analyzed_at);
CREATE INDEX IF NOT EXISTS idx_crashed         ON analyzed_logs (crashed);
CREATE INDEX IF NOT EXISTS idx_crash_confidence ON analyzed_logs (crash_confidence);
CREATE INDEX IF NOT EXISTS idx_rating          ON analyzed_logs (rating);
CREATE INDEX IF NOT EXISTS idx_score           ON analyzed_logs (score);
"""

# Columns added after initial release — applied as migrations to existing DBs
_MIGRATION_COLUMNS = [
    "motor_count INTEGER", "log_format TEXT",
    "has_rc INTEGER", "has_ekf INTEGER", "has_cpu INTEGER",
    "has_magnetometer INTEGER", "has_barometer INTEGER", "has_airspeed INTEGER",
    "max_roll_deg REAL", "max_pitch_deg REAL", "max_yaw_rate_dps REAL",
    "max_roll_err_deg REAL", "max_pitch_err_deg REAL",
    "motor_cutoff_frac REAL", "motor_cutoff_tilt REAL",
    "motor_min_avg REAL", "motor_max_avg REAL", "motor_imbalance REAL",
    "alt_peak_m REAL", "alt_final_m REAL", "alt_drop_rate REAL", "alt_drop_m REAL",
    "horiz_dist_m REAL",
    "gps_fix_min INTEGER", "gps_sat_min INTEGER", "gps_hdop_max REAL",
    "batt_v_min REAL", "batt_v_start REAL", "batt_v_end REAL",
    "batt_drop_v REAL", "batt_pct_min REAL", "batt_current_max REAL",
    "peak_g_last20pct REAL", "peak_g_overall REAL",
    "vib_rms_x REAL", "vib_rms_y REAL", "vib_rms_z REAL",
    "ekf_vel_innov_max REAL", "ekf_pos_innov_max REAL",
    "rc_rssi_min REAL", "rc_loss_events INTEGER",
    "error_count INTEGER", "warning_count_evt INTEGER", "failsafe_count INTEGER",
    "mode_change_count INTEGER",
    "vel_horiz_max REAL", "vel_vert_max REAL",
    "cpu_load_max REAL", "cpu_load_avg REAL",
]

# ---------------------------------------------------------------------------
# Listing helpers (reused from download_public_logs.py)
# ---------------------------------------------------------------------------

def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _build_browse_url(start: int, length: int, rated_crashes_only: bool = False) -> str:
    params = {
        "draw": "1",
        "start": str(start),
        "length": str(length),
        "columns[0][data]": "0",
        "columns[1][data]": "1",
        "columns[2][data]": "2",
        "columns[3][data]": "3",
        "columns[4][data]": "4",
        "columns[5][data]": "5",
        "columns[6][data]": "6",
        "columns[7][data]": "7",
        "columns[8][data]": "8",
        "columns[9][data]": "9",
        "order[0][column]": "1",
        "order[0][dir]": "desc",
    }
    if rated_crashes_only:
        # Filter by rating column (col 8) — value "crash" or "not ok"
        params["columns[8][search][value]"] = "crash"
    return BROWSE_URL + "?" + urllib.parse.urlencode(params)


def _extract_log_id(html_cell: str) -> str | None:
    m = re.search(r'log=([0-9a-f-]{36})', html_cell)
    return m.group(1) if m else None


def _extract_text(html_cell: str) -> str:
    m = re.search(r'>([^<]+)<', html_cell)
    return m.group(1).strip() if m else str(html_cell).strip()


def _parse_row(row: list) -> dict:
    return {
        "log_id":       _extract_log_id(str(row[1])) if len(row) > 1 else None,
        "date":         _extract_text(str(row[1])) if len(row) > 1 else None,
        "vehicle_type": str(row[3]) if len(row) > 3 else None,
        "airframe":     str(row[4]) if len(row) > 4 else None,
        "hardware":     str(row[5]) if len(row) > 5 else None,
        "firmware":     str(row[6]) if len(row) > 6 else None,
        "duration":     str(row[7]) if len(row) > 7 else None,
        "rating":       str(row[8]).lower().strip() if len(row) > 8 else None,
        "mode":         str(row[9]) if len(row) > 9 else None,
    }

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_to_temp(log_id: str) -> str | None:
    """Download log to a temp file. Returns path on success, None on failure."""
    url = f"{DOWNLOAD_URL}?log={urllib.parse.quote(log_id)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        if len(data) < 64:
            return None
        fd, path = tempfile.mkstemp(suffix=".ulg", prefix="goose_stream_")
        os.write(fd, data)
        os.close(fd)
        return path
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _safe_float(val) -> float | None:
    try:
        v = float(val)
        return None if (v != v) else round(v, 4)  # NaN check
    except Exception:
        return None


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except Exception:
        return None


def _extract_features(flight) -> dict:
    """Extract all raw telemetry features from a Flight object.

    These are stored in the DB so we can re-run scoring / crash detection
    logic without re-downloading or re-parsing the original log file.
    """
    import numpy as np
    f: dict = {}

    # ── Attitude ──────────────────────────────────────────────────────────────
    if not flight.attitude.empty and "roll" in flight.attitude.columns:
        att = flight.attitude
        f["max_roll_deg"]  = _safe_float(np.degrees(att["roll"].abs().max()))
        f["max_pitch_deg"] = _safe_float(np.degrees(att["pitch"].abs().max())) if "pitch" in att.columns else None
        if "yawspeed" in att.columns:
            f["max_yaw_rate_dps"] = _safe_float(np.degrees(att["yawspeed"].abs().max()))

    # ── Attitude tracking error ───────────────────────────────────────────────
    if not flight.attitude.empty and not flight.attitude_setpoint.empty:
        try:
            att = flight.attitude[["timestamp", "roll", "pitch"]].dropna()
            sp  = flight.attitude_setpoint[["timestamp", "roll_body", "pitch_body"]].dropna()
            merged = att.merge(sp, on="timestamp", how="inner")
            if not merged.empty:
                f["max_roll_err_deg"]  = _safe_float(np.degrees((merged["roll"]  - merged["roll_body"]).abs().max()))
                f["max_pitch_err_deg"] = _safe_float(np.degrees((merged["pitch"] - merged["pitch_body"]).abs().max()))
        except Exception:
            pass

    # ── Motors ────────────────────────────────────────────────────────────────
    if not flight.motors.empty:
        mcols = [c for c in flight.motors.columns if c.startswith("output_")]
        if mcols:
            motor_df = flight.motors[mcols]
            # cutoff position
            active_mask = (motor_df > 0.05).any(axis=1)
            active_idx  = active_mask[active_mask].index
            if len(active_idx) > 0 and len(flight.motors) > 5:
                last_pos = flight.motors.index.get_loc(active_idx[-1])
                f["motor_cutoff_frac"] = _safe_float(last_pos / len(flight.motors))
                # tilt at cutoff
                if not flight.attitude.empty and "roll" in flight.attitude.columns:
                    cutoff_ts = float(flight.motors["timestamp"].iloc[last_pos])
                    att_near = flight.attitude[flight.attitude["timestamp"] <= cutoff_ts].tail(5)
                    if not att_near.empty:
                        roll_c  = float(np.degrees(att_near["roll"].abs().mean()))
                        pitch_c = float(np.degrees(att_near["pitch"].abs().mean())) if "pitch" in att_near.columns else 0.0
                        f["motor_cutoff_tilt"] = _safe_float(max(roll_c, pitch_c))
            # per-motor stats
            per_min = motor_df.min(axis=0)
            per_max = motor_df.max(axis=0)
            f["motor_min_avg"]   = _safe_float(per_min.mean())
            f["motor_max_avg"]   = _safe_float(per_max.mean())
            # imbalance: max spread between motors at each timestep
            f["motor_imbalance"] = _safe_float((motor_df.max(axis=1) - motor_df.min(axis=1)).max())

    # ── Altitude / position ───────────────────────────────────────────────────
    if not flight.position.empty:
        pos = flight.position
        alt_col = "alt_rel" if "alt_rel" in pos.columns else ("alt_msl" if "alt_msl" in pos.columns else None)
        if alt_col and len(pos) >= 5:
            alt = pos[alt_col].dropna()
            ts  = pos["timestamp"]
            f["alt_peak_m"]  = _safe_float(alt.max())
            f["alt_final_m"] = _safe_float(alt.iloc[-1])
            if len(alt) >= 20:
                tail_start = int(len(alt) * 0.7)
                tail_alt   = alt.iloc[tail_start:]
                tail_ts    = ts.iloc[tail_start:]
                dt = float(tail_ts.iloc[-1] - tail_ts.iloc[0])
                if dt > 0:
                    drop = float(tail_alt.iloc[0] - tail_alt.iloc[-1])
                    f["alt_drop_rate"] = _safe_float(drop / dt)
                    f["alt_drop_m"]    = _safe_float(drop)
        # horizontal distance
        if "lat" in pos.columns and "lon" in pos.columns and len(pos) >= 2:
            try:
                lat = pos["lat"].dropna().values
                lon = pos["lon"].dropna().values
                n = min(len(lat), len(lon))
                if n >= 2:
                    dlat = np.diff(lat[:n]) * 111320.0
                    dlon = np.diff(lon[:n]) * 111320.0 * np.cos(np.radians(lat[:n-1]))
                    f["horiz_dist_m"] = _safe_float(np.sqrt(dlat**2 + dlon**2).sum())
            except Exception:
                pass

    # ── GPS quality ───────────────────────────────────────────────────────────
    if not flight.gps.empty:
        gps = flight.gps
        if "fix_type" in gps.columns:
            f["gps_fix_min"] = _safe_int(gps["fix_type"].min())
        if "satellites_used" in gps.columns:
            f["gps_sat_min"] = _safe_int(gps["satellites_used"].min())
        if "hdop" in gps.columns:
            f["gps_hdop_max"] = _safe_float(gps["hdop"].max())

    # ── Battery ───────────────────────────────────────────────────────────────
    if not flight.battery.empty:
        bat = flight.battery
        if "voltage" in bat.columns:
            v = bat["voltage"].dropna()
            if len(v) >= 2:
                f["batt_v_min"]   = _safe_float(v.min())
                f["batt_v_start"] = _safe_float(v.iloc[0])
                f["batt_v_end"]   = _safe_float(v.iloc[-1])
                f["batt_drop_v"]  = _safe_float(float(v.iloc[0]) - float(v.min()))
        if "remaining_pct" in bat.columns:
            f["batt_pct_min"] = _safe_float(bat["remaining_pct"].min())
        if "current" in bat.columns:
            f["batt_current_max"] = _safe_float(bat["current"].max())

    # ── Vibration / IMU ───────────────────────────────────────────────────────
    if not flight.vibration.empty:
        vib = flight.vibration
        accel_cols = [c for c in vib.columns if c.startswith("accel_")]
        if accel_cols:
            total_g = np.sqrt(sum(vib[c]**2 for c in accel_cols)) / 9.81
            f["peak_g_overall"] = _safe_float(total_g.max())
            last_20 = int(len(total_g) * 0.8)
            f["peak_g_last20pct"] = _safe_float(total_g.iloc[last_20:].max())
        if "vibration_x" in vib.columns:
            f["vib_rms_x"] = _safe_float(np.sqrt((vib["vibration_x"]**2).mean()))
        if "vibration_y" in vib.columns:
            f["vib_rms_y"] = _safe_float(np.sqrt((vib["vibration_y"]**2).mean()))
        if "vibration_z" in vib.columns:
            f["vib_rms_z"] = _safe_float(np.sqrt((vib["vibration_z"]**2).mean()))

    # ── EKF ───────────────────────────────────────────────────────────────────
    if not flight.ekf.empty:
        ekf = flight.ekf
        vel_cols = [c for c in ekf.columns if "vel_innov" in c or "velocity_innov" in c]
        pos_cols = [c for c in ekf.columns if "pos_innov" in c or "position_innov" in c]
        if vel_cols:
            f["ekf_vel_innov_max"] = _safe_float(ekf[vel_cols].abs().max().max())
        if pos_cols:
            f["ekf_pos_innov_max"] = _safe_float(ekf[pos_cols].abs().max().max())

    # ── RC ────────────────────────────────────────────────────────────────────
    if not flight.rc_input.empty:
        rc = flight.rc_input
        if "rssi" in rc.columns:
            f["rc_rssi_min"] = _safe_float(rc["rssi"].min())
        # RC loss = transitions to rssi < 0.1
        if "rssi" in rc.columns:
            rssi = rc["rssi"].fillna(1.0)
            loss_events = int(((rssi < 0.1) & (rssi.shift(1) >= 0.1)).sum())
            f["rc_loss_events"] = loss_events

    # ── Flight events ─────────────────────────────────────────────────────────
    if flight.events:
        f["error_count"]       = sum(1 for e in flight.events if e.severity == "critical")
        f["warning_count_evt"] = sum(1 for e in flight.events if e.severity == "warning")
        f["failsafe_count"]    = sum(1 for e in flight.events if e.event_type == "failsafe")
    if flight.mode_changes:
        f["mode_change_count"] = len(flight.mode_changes)

    # ── Velocity ──────────────────────────────────────────────────────────────
    if not flight.velocity.empty:
        vel = flight.velocity
        if "vx" in vel.columns and "vy" in vel.columns:
            horiz = np.sqrt(vel["vx"]**2 + vel["vy"]**2)
            f["vel_horiz_max"] = _safe_float(horiz.max())
        if "vz" in vel.columns:
            f["vel_vert_max"] = _safe_float(vel["vz"].abs().max())

    # ── CPU ───────────────────────────────────────────────────────────────────
    if not flight.cpu.empty:
        cpu = flight.cpu
        load_col = next((c for c in ["load", "cpu_load", "ram_usage"] if c in cpu.columns), None)
        if load_col:
            f["cpu_load_max"] = _safe_float(cpu[load_col].max())
            f["cpu_load_avg"] = _safe_float(cpu[load_col].mean())

    return f


def _analyze(log_path: str, entry: dict) -> dict:
    """Parse + analyze one log. Returns result dict for DB insertion."""
    null_features = {
        "max_roll_deg": None, "max_pitch_deg": None, "max_yaw_rate_dps": None,
        "max_roll_err_deg": None, "max_pitch_err_deg": None,
        "motor_cutoff_frac": None, "motor_cutoff_tilt": None,
        "motor_min_avg": None, "motor_max_avg": None, "motor_imbalance": None,
        "alt_peak_m": None, "alt_final_m": None, "alt_drop_rate": None, "alt_drop_m": None,
        "horiz_dist_m": None,
        "gps_fix_min": None, "gps_sat_min": None, "gps_hdop_max": None,
        "batt_v_min": None, "batt_v_start": None, "batt_v_end": None,
        "batt_drop_v": None, "batt_pct_min": None, "batt_current_max": None,
        "peak_g_last20pct": None, "peak_g_overall": None,
        "vib_rms_x": None, "vib_rms_y": None, "vib_rms_z": None,
        "ekf_vel_innov_max": None, "ekf_pos_innov_max": None,
        "rc_rssi_min": None, "rc_loss_events": None,
        "error_count": None, "warning_count_evt": None,
        "failsafe_count": None, "mode_change_count": None,
        "vel_horiz_max": None, "vel_vert_max": None,
        "cpu_load_max": None, "cpu_load_avg": None,
    }
    result: dict = {
        "log_id":           entry["log_id"],
        "analyzed_at":      datetime.now(timezone.utc).isoformat(),
        "date":             entry.get("date"),
        "vehicle_type_api": entry.get("vehicle_type"),
        "airframe":         entry.get("airframe"),
        "hardware_api":     entry.get("hardware"),
        "firmware_api":     entry.get("firmware"),
        "duration_api":     entry.get("duration"),
        "rating":           entry.get("rating"),
        "mode_api":         entry.get("mode"),
        "ok":               0,
        "error":            None,
        "duration_sec":     None,
        "vehicle_type":     None,
        "hardware":         None,
        "firmware":         None,
        "primary_mode":     None,
        "motor_count":      None,
        "log_format":       None,
        "crashed":          None,
        "crash_confidence": None,
        "crash_signals":    None,
        "score":            None,
        "critical_count":   0,
        "warning_count":    0,
        "info_count":       0,
        "has_gps":          0,
        "has_attitude":     0,
        "has_battery":      0,
        "has_motors":       0,
        "has_vibration":    0,
        "has_rc":           0,
        "has_ekf":          0,
        "has_cpu":          0,
        "has_magnetometer": 0,
        "has_barometer":    0,
        "has_airspeed":     0,
        "signal_streams":   0,
        **null_features,
    }
    try:
        from goose.parsers.ulog import ULogParser
        from goose.plugins.registry import load_plugins
        from goose.core.scoring import compute_overall_score

        pr = ULogParser().parse(log_path)
        if pr is None or pr.flight is None:
            result["error"] = "parse returned None"
            return result

        flight = pr.flight
        meta = flight.metadata

        result["duration_sec"]  = round(meta.duration_sec, 1)
        result["vehicle_type"]  = meta.vehicle_type
        result["hardware"]      = meta.hardware or meta.autopilot
        result["firmware"]      = meta.firmware_version
        result["primary_mode"]  = flight.primary_mode
        result["motor_count"]   = meta.motor_count
        result["log_format"]    = meta.log_format
        result["has_gps"]       = int(not flight.gps.empty)
        result["has_attitude"]  = int(not flight.attitude.empty)
        result["has_battery"]   = int(not flight.battery.empty)
        result["has_motors"]    = int(not flight.motors.empty)
        result["has_vibration"] = int(not flight.vibration.empty)
        result["has_rc"]        = int(not flight.rc_input.empty)
        result["has_ekf"]       = int(not flight.ekf.empty)
        result["has_cpu"]       = int(not flight.cpu.empty)
        result["has_magnetometer"] = int(not flight.magnetometer.empty)
        result["has_barometer"] = int(not flight.barometer.empty)
        result["has_airspeed"]  = int(not flight.airspeed.empty)

        ca = flight.crash_assessment()
        result["crashed"]          = int(ca["crashed"])
        result["crash_confidence"] = ca["confidence"]
        result["crash_signals"]    = "; ".join(ca["signals"]) if ca["signals"] else ""

        if pr.diagnostics:
            result["signal_streams"] = len(pr.diagnostics.stream_coverage)

        # Extract raw telemetry features
        try:
            result.update(_extract_features(flight))
        except Exception as feat_exc:
            pass  # features are best-effort; don't fail the whole record

        # Run plugins
        plugins = load_plugins()
        findings = []
        for p in plugins:
            try:
                findings.extend(p.analyze(flight, {}))
            except Exception:
                pass

        result["score"]          = compute_overall_score(findings)
        result["critical_count"] = sum(1 for f in findings if f.severity == "critical")
        result["warning_count"]  = sum(1 for f in findings if f.severity == "warning")
        result["info_count"]     = sum(1 for f in findings if f.severity == "info")
        result["ok"] = 1

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    return result

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    # Migrate existing DBs — add new columns if absent (safe to re-run)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(analyzed_logs)")}
    for col_def in _MIGRATION_COLUMNS:
        col_name = col_def.split()[0]
        if col_name not in existing:
            conn.execute(f"ALTER TABLE analyzed_logs ADD COLUMN {col_def}")
    # Feature column indexes — only after columns exist
    for col, idx in [("max_roll_deg", "idx_max_roll"), ("batt_v_min", "idx_batt_v_min"),
                     ("peak_g_last20pct", "idx_peak_g")]:
        if col in {row[1] for row in conn.execute("PRAGMA table_info(analyzed_logs)")}:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON analyzed_logs ({col})")
    conn.commit()
    return conn


def _already_done(conn: sqlite3.Connection, log_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM analyzed_logs WHERE log_id = ?", (log_id,)).fetchone()
    return row is not None


def _insert(conn: sqlite3.Connection, r: dict) -> None:
    cols = list(r.keys())
    placeholders = ", ".join("?" * len(cols))
    sql = f"INSERT OR REPLACE INTO analyzed_logs ({', '.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, [r[c] for c in cols])
    conn.commit()


def _print_stats(conn: sqlite3.Connection, db_path: Path = DB_PATH) -> None:
    total = conn.execute("SELECT COUNT(*) FROM analyzed_logs").fetchone()[0]
    ok    = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE ok=1").fetchone()[0]
    crash = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crashed=1").fetchone()[0]
    hi    = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crash_confidence >= 0.80").fetchone()[0]
    med   = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crash_confidence >= 0.60 AND crash_confidence < 0.80").fetchone()[0]
    low   = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE crash_confidence > 0 AND crash_confidence < 0.60").fetchone()[0]
    avg_score = conn.execute("SELECT AVG(score) FROM analyzed_logs WHERE ok=1").fetchone()[0]
    rated_crash = conn.execute("SELECT COUNT(*) FROM analyzed_logs WHERE rating IN ('crash','not ok','fail')").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  Stream analysis DB: {db_path}")
    print(f"{'='*60}")
    print(f"  Total analyzed  : {total:,}")
    print(f"  Parse OK        : {ok:,} ({ok/total*100:.0f}%)" if total else "  Parse OK        : 0")
    print(f"  Human-rated crash: {rated_crash:,}")
    print(f"  Crash detected  : {crash:,}")
    print(f"    high (>=80%)  : {hi:,}")
    print(f"    medium (60-79%): {med:,}")
    print(f"    signal evidence: {low:,}")
    print(f"  Avg score       : {avg_score:.0f}" if avg_score else "  Avg score       : n/a")
    print(f"{'='*60}\n")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _export_csv(conn: sqlite3.Connection, path: str) -> None:
    import csv
    rows = conn.execute("SELECT * FROM analyzed_logs ORDER BY analyzed_at").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM analyzed_logs LIMIT 0").description]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    print(f"Exported {len(rows):,} rows to {path}")

# ---------------------------------------------------------------------------
# Main stream loop
# ---------------------------------------------------------------------------

_shutdown = False

def _handle_signal(sig, frame):
    global _shutdown
    print("\n[interrupt] Finishing current log then stopping...")
    _shutdown = True


def stream_analyze(
    limit: int,
    resume: bool,
    rated_crashes_only: bool,
    offset_start: int = 0,
    db_path: Path = DB_PATH,
) -> None:
    conn = _open_db(db_path)
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    total_done = conn.execute("SELECT COUNT(*) FROM analyzed_logs").fetchone()[0]
    print(f"\nGoose Stream Analyzer")
    print(f"  DB         : {db_path}")
    print(f"  Already done: {total_done:,}")
    print(f"  Target      : {limit} new logs")
    print(f"  Offset start: {offset_start}")
    print(f"  Filter      : {'rated-crashes-only' if rated_crashes_only else 'all public logs'}")
    print()

    processed = 0
    skipped = 0
    offset = offset_start
    t0 = time.time()

    while processed < limit and not _shutdown:
        # Fetch a page of log listings
        fetch = min(PAGE_SIZE, limit - processed + skipped + 20)
        url = _build_browse_url(offset, fetch, rated_crashes_only)
        try:
            data = _fetch_json(url)
        except urllib.error.URLError as exc:
            print(f"  [listing error] {exc} — retrying in 5s")
            time.sleep(5)
            continue

        rows = data.get("data", [])
        if not rows:
            print("  [done] No more logs in listing.")
            break

        total_available = data.get("recordsTotal", "?")

        for row in rows:
            if processed >= limit or _shutdown:
                break

            entry = _parse_row(row)
            log_id = entry.get("log_id")
            if not log_id:
                skipped += 1
                continue

            if _already_done(conn, log_id):
                skipped += 1
                continue

            # Download
            t_dl = time.time()
            tmp = _download_to_temp(log_id)
            dl_sec = time.time() - t_dl

            if tmp is None:
                result = {
                    "log_id": log_id,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "date": entry.get("date"),
                    "vehicle_type_api": entry.get("vehicle_type"),
                    "airframe": entry.get("airframe"),
                    "hardware_api": entry.get("hardware"),
                    "firmware_api": entry.get("firmware"),
                    "duration_api": entry.get("duration"),
                    "rating": entry.get("rating"),
                    "mode_api": entry.get("mode"),
                    "ok": 0,
                    "error": "download failed",
                    "duration_sec": None, "vehicle_type": None, "hardware": None,
                    "firmware": None, "primary_mode": None,
                    "crashed": None, "crash_confidence": None, "crash_signals": None,
                    "score": None, "critical_count": 0, "warning_count": 0, "info_count": 0,
                    "has_gps": 0, "has_attitude": 0, "has_battery": 0, "has_motors": 0,
                    "has_vibration": 0, "signal_streams": 0,
                }
                _insert(conn, result)
                processed += 1
                elapsed = time.time() - t0
                rate = processed / elapsed * 60
                print(f"[{processed:>4}/{limit}] FAIL  {log_id[:8]}  download failed  ({rate:.0f}/min)")
                time.sleep(RATE_LIMIT_SEC)
                continue

            # Analyze
            t_an = time.time()
            try:
                result = _analyze(tmp, entry)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            an_sec = time.time() - t_an

            _insert(conn, result)
            processed += 1

            elapsed = time.time() - t0
            rate = processed / elapsed * 60

            if result["ok"]:
                conf = result.get("crash_confidence") or 0.0
                if conf >= 0.60:
                    crash_tag = f"CRASH({conf:.0%})"
                elif conf > 0.0:
                    crash_tag = f"sig({conf:.0%})"
                else:
                    crash_tag = "ok"
                score = f"s={result['score']}" if result['score'] is not None else "s=?"
                hw = (result.get("hardware") or entry.get("hardware") or "?")[:16]
                print(f"[{processed:>4}/{limit}] {crash_tag:<12} {log_id[:8]}  {hw:<17} {score}  dl={dl_sec:.0f}s an={an_sec:.0f}s  {rate:.0f}/min")
            else:
                err = (result.get("error") or "?")[:50]
                print(f"[{processed:>4}/{limit}] ERR          {log_id[:8]}  {err}  {rate:.0f}/min")

            time.sleep(RATE_LIMIT_SEC)

        offset += len(rows)

    # Summary
    elapsed = time.time() - t0
    print(f"\n{'-'*60}")
    print(f"Done: {processed} analyzed, {skipped} skipped (already done or no id)")
    print(f"Time: {elapsed:.0f}s  Rate: {processed/elapsed*60:.0f}/min avg")
    _print_stats(conn, db_path)
    conn.close()

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Stream-analyze PX4 public logs into SQLite")
    p.add_argument("--limit", type=int, default=100, help="Max new logs to analyze (default: 100)")
    p.add_argument("--resume", action="store_true", help="Skip logs already in DB (default behavior)")
    p.add_argument("--offset", type=int, default=0, help="Start at this offset in the logs.px4.io listing")
    p.add_argument("--rated-crashes-only", action="store_true", help="Only fetch logs with explicit crash rating")
    p.add_argument("--stats", action="store_true", help="Print DB stats and exit")
    p.add_argument("--export", metavar="CSV", help="Export DB to CSV and exit")
    p.add_argument("--db", metavar="PATH", help=f"SQLite DB path (default: {DB_PATH})")
    args = p.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    conn = _open_db(db_path)

    if args.stats:
        _print_stats(conn, db_path)
        conn.close()
        return

    if args.export:
        _export_csv(conn, args.export)
        conn.close()
        return

    conn.close()

    stream_analyze(
        limit=args.limit,
        resume=True,
        rated_crashes_only=args.rated_crashes_only,
        offset_start=args.offset,
        db_path=db_path,
    )


if __name__ == "__main__":
    main()
