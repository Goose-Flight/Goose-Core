"""Generic CSV flight log parser.

Handles CSV exports from common GCS / flight log tools. Supports:
  - QGroundControl CSV exports (PX4 logs exported via QGC)
  - Mission Planner CSV exports (ArduPilot)
  - Generic timestamped CSV with recognizable column names

The parser uses heuristic column name matching to identify streams.
It does NOT attempt to reconstruct complex PX4/APM messages from CSV —
those require format-specific parsers (.ulg, .bin). This parser fills
the gap for users who only have a CSV export from their GCS.

Design rules:
- Never raise. All errors go into ParseDiagnostics.errors.
- Degrade gracefully: parse what's there, skip what's not.
- Record stream coverage for every expected stream (present or absent).
- ParseDiagnostics.confidence reflects how many standard streams were found.

Implementation status: IMPLEMENTED (basic stream heuristics, Sprint 6)
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from goose import __version__ as _engine_version
from goose.core.flight import (
    Flight,
    FlightMetadata,
)
from goose.forensics.models import Provenance
from goose.parsers.base import BaseParser
from goose.parsers.diagnostics import ParseDiagnostics, ParseResult, StreamCoverage

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Column name heuristics
# Column groups: list of candidate column name substrings (case-insensitive).
# The parser tries each candidate in order and uses the first match.
# ---------------------------------------------------------------------------

_COL_TIMESTAMP = ["timestamp", "time_us", "time_s", "time", "t", "elapsed"]
_COL_LAT = ["lat", "latitude", "gps_lat"]
_COL_LON = ["lon", "lng", "longitude", "gps_lon"]
_COL_ALT_REL = ["alt_rel", "relative_alt", "altitude_rel", "height", "alt_relative"]
_COL_ALT_MSL = ["alt", "altitude", "alt_msl", "altitude_msl", "gps_alt"]
_COL_VOLTAGE = ["voltage", "batt_volt", "battery_voltage", "volt", "v_batt"]
_COL_CURRENT = ["current", "batt_curr", "battery_current", "curr"]
_COL_REMAINING = ["remaining", "capacity_pct", "battery_pct", "batt_pct", "charge_state"]
_COL_SATS = ["satellites", "gps_satellites", "num_sats", "numsat", "sat_count"]
_COL_HDOP = ["hdop", "gps_hdop", "horizontal_dilution"]
_COL_FIX = ["fix_type", "gps_fix", "fix", "gps_type"]
_COL_ROLL = ["roll", "roll_deg", "roll_rad", "euler_roll"]
_COL_PITCH = ["pitch", "pitch_deg", "pitch_rad", "euler_pitch"]
_COL_YAW = ["yaw", "heading", "yaw_deg", "yaw_rad", "euler_yaw"]
_COL_VX = ["vx", "vel_x", "velocity_x", "speed_x"]
_COL_VY = ["vy", "vel_y", "velocity_y", "speed_y"]
_COL_VZ = ["vz", "vel_z", "velocity_z", "speed_z"]
_COL_RSSI = ["rssi", "signal", "rx_rssi", "radio_rssi"]


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the first column in df whose name matches any candidate substring."""
    lower_cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        cand_l = cand.lower()
        # Exact match first
        if cand_l in lower_cols:
            return lower_cols[cand_l]
        # Substring match
        for col_l, col in lower_cols.items():
            if cand_l in col_l:
                return col
    return None


def _safe_float_col(df: pd.DataFrame, col: str) -> pd.Series:
    """Return a float column, coercing non-numeric to NaN."""
    return pd.to_numeric(df[col], errors="coerce")


class CSVParser(BaseParser):
    """Generic CSV flight log parser.

    Recognizes common column names from QGroundControl, Mission Planner,
    and other GCS CSV export formats. Degrades gracefully when columns
    are missing — every absent stream is recorded in ParseDiagnostics.
    """

    format_name = "csv"
    file_extensions = [".csv"]
    implemented = True
    VERSION = VERSION

    def parse(self, filepath: str | Path) -> ParseResult:
        """Parse a CSV flight log. Never raises — returns ParseResult.failure() on error."""
        filepath = Path(filepath)
        t0 = time.monotonic()
        diag = ParseDiagnostics(
            parser_selected="CSVParser",
            parser_version=VERSION,
            detected_format="csv",
            format_confidence=0.7,  # CSV is ambiguous — always lower confidence than native formats
            supported=True,
            parse_started_at=datetime.now().replace(microsecond=0),
        )

        if not filepath.exists():
            diag.errors.append(f"File not found: {filepath}")
            diag.parser_confidence = 0.0
            return ParseResult.failure(diag)

        # --- Load CSV -------------------------------------------------------
        try:
            df = pd.read_csv(str(filepath), low_memory=False)
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            diag.errors.append(f"CSV read failed: {exc}")
            diag.parser_confidence = 0.0
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        if df.empty or len(df.columns) < 2:
            diag.errors.append("CSV is empty or has fewer than 2 columns.")
            diag.parser_confidence = 0.0
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        _parse_artifacts = {
            "row_count": len(df),
            "columns": list(df.columns),
        }

        # --- Timestamp normalization -----------------------------------------
        ts_col = _find_col(df, _COL_TIMESTAMP)
        if ts_col is None:
            diag.errors.append(
                "No timestamp column found. Expected one of: "
                + ", ".join(_COL_TIMESTAMP[:5])
            )
            diag.parser_confidence = 0.0
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        ts_raw = _safe_float_col(df, ts_col)
        if ts_raw.isna().all():
            diag.errors.append(f"Timestamp column '{ts_col}' contains no numeric values.")
            diag.parser_confidence = 0.0
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        # Detect timestamp scale: microseconds, milliseconds, or seconds
        ts_max = float(ts_raw.dropna().max())
        if ts_max > 1e12:
            # Likely microseconds
            ts_sec = (ts_raw - ts_raw.min()) / 1e6
        elif ts_max > 1e9:
            # Likely milliseconds
            ts_sec = (ts_raw - ts_raw.min()) / 1e3
        elif ts_max > 1e6:
            # Ambiguous — treat as milliseconds
            ts_sec = (ts_raw - ts_raw.min()) / 1e3
            diag.warnings.append(
                f"Timestamp scale ambiguous (max={ts_max:.0f}). Treating as milliseconds."
            )
        else:
            # Likely already seconds (possibly fractional)
            ts_sec = ts_raw - ts_raw.min()

        df["_ts"] = ts_sec
        duration_sec = float(ts_sec.dropna().max() - ts_sec.dropna().min())

        if duration_sec < 1.0:
            diag.timebase_anomalies.append(
                f"Log duration is very short ({duration_sec:.2f}s). Timestamps may be unreliable."
            )

        # --- Build sub-DataFrames for each stream ---------------------------
        coverage: list[StreamCoverage] = []

        def _make_df(*col_defs: tuple[str, list[str]]) -> pd.DataFrame | None:
            """Build a sub-DataFrame from (output_name, candidates) pairs."""
            result = pd.DataFrame({"timestamp": ts_sec})
            found_any = False
            for out_name, candidates in col_defs:
                raw_col = _find_col(df, candidates)
                if raw_col is not None:
                    result[out_name] = _safe_float_col(df, raw_col)
                    found_any = True
                else:
                    result[out_name] = np.nan
            if not found_any:
                return None
            return result.dropna(subset=["timestamp"])

        # Position
        pos_df = _make_df(
            ("lat", _COL_LAT),
            ("lon", _COL_LON),
            ("alt_rel", _COL_ALT_REL),
            ("alt_msl", _COL_ALT_MSL),
        )
        if pos_df is not None and not pos_df.isnull().all(axis=None):
            coverage.append(StreamCoverage("position", present=True, row_count=len(pos_df)))
        else:
            pos_df = pd.DataFrame()
            coverage.append(StreamCoverage("position", present=False))

        # Battery
        bat_df = _make_df(
            ("voltage", _COL_VOLTAGE),
            ("current", _COL_CURRENT),
            ("remaining_pct", _COL_REMAINING),
        )
        if bat_df is not None and not bat_df[["voltage", "current", "remaining_pct"]].isnull().all(axis=None):
            coverage.append(StreamCoverage("battery", present=True, row_count=len(bat_df)))
        else:
            bat_df = pd.DataFrame()
            coverage.append(StreamCoverage("battery", present=False))

        # GPS
        gps_df = _make_df(
            ("satellites", _COL_SATS),
            ("hdop", _COL_HDOP),
            ("fix_type", _COL_FIX),
        )
        if gps_df is not None and not gps_df[["satellites", "hdop", "fix_type"]].isnull().all(axis=None):
            coverage.append(StreamCoverage("gps", present=True, row_count=len(gps_df)))
        else:
            gps_df = pd.DataFrame()
            coverage.append(StreamCoverage("gps", present=False))

        # Attitude
        att_df = _make_df(
            ("roll", _COL_ROLL),
            ("pitch", _COL_PITCH),
            ("yaw", _COL_YAW),
        )
        if att_df is not None and not att_df[["roll", "pitch", "yaw"]].isnull().all(axis=None):
            # Convert degrees to radians if likely in degrees (values > 4 suggest degrees)
            for axis in ("roll", "pitch", "yaw"):
                if axis in att_df.columns:
                    col_max = float(att_df[axis].abs().max())
                    if col_max > 4.0:  # pi ~ 3.14
                        att_df[axis] = np.radians(att_df[axis])
            coverage.append(StreamCoverage("attitude", present=True, row_count=len(att_df)))
        else:
            att_df = pd.DataFrame()
            coverage.append(StreamCoverage("attitude", present=False))

        # Velocity
        vel_df = _make_df(
            ("vx", _COL_VX),
            ("vy", _COL_VY),
            ("vz", _COL_VZ),
        )
        if vel_df is not None and not vel_df[["vx", "vy", "vz"]].isnull().all(axis=None):
            coverage.append(StreamCoverage("velocity", present=True, row_count=len(vel_df)))
        else:
            vel_df = pd.DataFrame()
            coverage.append(StreamCoverage("velocity", present=False))

        # RC signal (RSSI only)
        rc_df = _make_df(("rssi", _COL_RSSI))
        if rc_df is not None and not rc_df[["rssi"]].isnull().all(axis=None):
            coverage.append(StreamCoverage("rc_input", present=True, row_count=len(rc_df)))
        else:
            rc_df = pd.DataFrame()
            coverage.append(StreamCoverage("rc_input", present=False))

        # Mark remaining streams as absent (CSV rarely has vibration/EKF/motors)
        for absent_stream in ("vibration", "motors", "ekf", "attitude_setpoint",
                              "position_setpoint", "attitude_rate", "cpu", "flight_mode"):
            coverage.append(StreamCoverage(absent_stream, present=False,
                                           notes="Stream not available in CSV format."))

        diag.stream_coverage = coverage
        diag.missing_streams = [sc.stream_name for sc in coverage if not sc.present]

        # Warn for critically absent streams
        if pos_df.empty is not True or (isinstance(pos_df, pd.DataFrame) and pos_df.empty):
            if not any(sc.present for sc in coverage if sc.stream_name == "position"):
                diag.warnings.append("No position data found — crash detection and position tracking unavailable.")
        if not any(sc.present for sc in coverage if sc.stream_name == "battery"):
            diag.warnings.append("No battery data found — battery analysis unavailable.")

        # --- Confidence scoring ---------------------------------------------
        critical_streams = {"position", "battery", "attitude", "gps"}
        present_critical = {sc.stream_name for sc in coverage if sc.present and sc.stream_name in critical_streams}
        confidence = round(0.4 + 0.15 * len(present_critical), 2)  # max 1.0 at all 4 critical streams
        # CSV is inherently less reliable than native formats — cap at 0.85
        confidence = min(confidence, 0.85)
        if diag.timebase_anomalies:
            confidence = max(0.0, confidence - 0.05)
        diag.parser_confidence = confidence

        # --- Build Flight object -------------------------------------------
        meta = FlightMetadata(
            source_file=str(filepath),
            autopilot="unknown",
            firmware_version="unknown",
            vehicle_type="unknown",
            frame_type=None,
            hardware=None,
            duration_sec=duration_sec,
            start_time_utc=None,
            log_format="csv",
            motor_count=0,
        )

        flight = Flight(
            metadata=meta,
            position=pos_df if not (isinstance(pos_df, pd.DataFrame) and pos_df.empty) else pd.DataFrame(),
            battery=bat_df if not (isinstance(bat_df, pd.DataFrame) and bat_df.empty) else pd.DataFrame(),
            gps=gps_df if not (isinstance(gps_df, pd.DataFrame) and gps_df.empty) else pd.DataFrame(),
            attitude=att_df if not (isinstance(att_df, pd.DataFrame) and att_df.empty) else pd.DataFrame(),
            velocity=vel_df if not (isinstance(vel_df, pd.DataFrame) and vel_df.empty) else pd.DataFrame(),
            rc_input=rc_df if not (isinstance(rc_df, pd.DataFrame) and rc_df.empty) else pd.DataFrame(),
            primary_mode="manual",
        )

        # --- Provenance -----------------------------------------------------
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        diag.parse_duration_ms = elapsed_ms
        diag.parse_completed_at = datetime.now().replace(microsecond=0)

        present_streams = [sc.stream_name for sc in coverage if sc.present]
        prov = Provenance(
            parser_name="CSVParser",
            parser_version=VERSION,
            engine_version=_engine_version,
            detected_format="csv",
            transformation_chain=[f"CSVParser-{VERSION}"],
            assumptions=[
                "Column names matched by heuristic substring search.",
                f"Timestamp treated as {'microseconds' if ts_max > 1e12 else 'milliseconds' if ts_max > 1e9 else 'seconds'}.",
                f"Streams detected: {', '.join(present_streams) or 'none'}.",
            ],
        )

        return ParseResult(
            flight=flight,
            diagnostics=diag,
            provenance=prov,
            parse_artifacts=_parse_artifacts,
        )
