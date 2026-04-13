"""ArduPilot DataFlash (.bin/.log) parser.

Supports:
- Text-format DataFlash (.log): fully parsed, all key streams extracted.
- Binary-format DataFlash (.bin): format detected, FMT messages read, best-effort
  extraction of key messages; degrades gracefully on unknown message types.

The text format is line-oriented ASCII with FMT definition lines followed by
data lines. The binary format uses 0xA3 0x95 framing per message.
"""

from __future__ import annotations

import logging
import struct
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Binary format constants
# ---------------------------------------------------------------------------
BINARY_HEADER = (0xA3, 0x95)
FMT_TYPE = 128  # 0x80

# DataFlash binary type-format char to struct format mapping
# Based on ArduPilot source: libraries/AP_Logger/LogStructure.h
_FMT_CHAR_MAP: dict[str, str] = {
    "a": "64s",  # int16_t[32]
    "b": "b",  # int8_t
    "B": "B",  # uint8_t
    "h": "h",  # int16_t
    "H": "H",  # uint16_t
    "i": "i",  # int32_t
    "I": "I",  # uint32_t
    "f": "f",  # float
    "d": "d",  # double
    "n": "4s",  # char[4]
    "N": "16s",  # char[16]
    "Z": "64s",  # char[64]
    "c": "h",  # int16_t * 100 (centidegrees)
    "C": "H",  # uint16_t * 100
    "e": "i",  # int32_t * 100
    "E": "I",  # uint32_t * 100
    "L": "i",  # int32_t latitude/longitude (deg * 1e7)
    "M": "B",  # uint8_t flight mode
    "q": "q",  # int64_t
    "Q": "Q",  # uint64_t
}

# Scaling for centidegree types
_SCALE_100 = {"c", "C", "e", "E"}
# Scale 1e-7 for lat/lon
_SCALE_LAT_LON = {"L"}


# ---------------------------------------------------------------------------
# Text-format parser helpers
# ---------------------------------------------------------------------------


def _parse_text_fmt_line(parts: list[str]) -> dict[str, Any] | None:
    """Parse a FMT definition line into a format descriptor dict.

    FMT line: FMT, <type>, <length>, <name>, <format_chars>, <col1>,<col2>,...
    """
    # parts[0] == "FMT"
    if len(parts) < 6:
        return None
    try:
        msg_type = int(parts[1].strip())
        # parts[2] = length, parts[3] = name, parts[4] = format chars
        name = parts[3].strip()
        fmt_chars = parts[4].strip()
        columns = [c.strip() for c in parts[5:]]
    except (ValueError, IndexError):
        return None
    else:
        return {
            "type": msg_type,
            "name": name,
            "fmt_chars": fmt_chars,
            "columns": columns,
        }


def _coerce_value(val_str: str) -> float | str:
    """Convert a string field value to float or leave as string."""
    v = val_str.strip()
    try:
        return float(v)
    except ValueError:
        return v


def _parse_text_dataflash(raw: str) -> dict[str, list[dict[str, Any]]]:
    """Parse a full text DataFlash log.

    Returns a dict: message_name -> list of row dicts {col: value, ...}.
    The first column is always TimeUS (time in microseconds).
    """
    fmt_defs: dict[str, dict[str, Any]] = {}  # name -> fmt descriptor
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(",")
        msg_type_str = parts[0].strip()

        if msg_type_str == "FMT":
            desc = _parse_text_fmt_line(parts)
            if desc:
                fmt_defs[desc["name"]] = desc
            continue

        if msg_type_str not in fmt_defs:
            continue

        desc = fmt_defs[msg_type_str]
        cols = desc["columns"]
        values = parts[1:]  # skip the message type token

        row: dict[str, Any] = {}
        for i, col in enumerate(cols):
            if i < len(values):
                row[col] = _coerce_value(values[i])
            else:
                row[col] = None
        records[msg_type_str].append(row)

    return dict(records)


def _records_to_df(records: list[dict[str, Any]], time_col: str = "TimeUS") -> pd.DataFrame:
    """Convert a list of record dicts to a DataFrame with normalised timestamp (seconds)."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if time_col in df.columns:
        # Convert microseconds to seconds, relative to first timestamp
        first_ts = float(df[time_col].iloc[0])
        df["timestamp"] = (df[time_col].astype(float) - first_ts) / 1e6
    return df


# ---------------------------------------------------------------------------
# Stream extractors (text format)
# ---------------------------------------------------------------------------


def _extract_attitude_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """ATT -> attitude DataFrame (roll/pitch/yaw in degrees)."""
    rows = records.get("ATT", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]

    # ATT columns (text format): TimeUS, DesRoll, Roll, DesPitch, Pitch, DesYaw, Yaw
    col_map = {
        "Roll": "roll",
        "Pitch": "pitch",
        "Yaw": "yaw",
        "DesRoll": "roll_setpoint",
        "DesPitch": "pitch_setpoint",
        "DesYaw": "yaw_setpoint",
    }
    for src, dst in col_map.items():
        if src in df.columns:
            result[dst] = pd.to_numeric(df[src], errors="coerce")

    return result


def _extract_baro_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """BARO -> altitude DataFrame."""
    rows = records.get("BARO", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    # BARO columns: TimeUS, Alt, Press, Temp
    if "Alt" in df.columns:
        result["alt_rel"] = pd.to_numeric(df["Alt"], errors="coerce")
        result["alt_msl"] = result["alt_rel"]  # best effort; BARO gives AGL approx
    if "Press" in df.columns:
        result["pressure"] = pd.to_numeric(df["Press"], errors="coerce")

    return result


def _extract_battery_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """BAT -> battery DataFrame."""
    rows = records.get("BAT", [])
    if not rows:
        rows = records.get("POWR", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    # BAT columns: TimeUS, Instance, Volt, VoltR, Curr, EnrgTot
    if "Volt" in df.columns:
        result["voltage"] = pd.to_numeric(df["Volt"], errors="coerce")
    if "Curr" in df.columns:
        result["current"] = pd.to_numeric(df["Curr"], errors="coerce")
    if "RemPct" in df.columns:
        result["remaining_pct"] = pd.to_numeric(df["RemPct"], errors="coerce")

    return result


def _extract_gps_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """GPS -> gps DataFrame."""
    rows = records.get("GPS", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    # GPS columns: TimeUS, Status, GMS, GWk, NSats, HDop, Lat, Lng, Alt, Spd, GCrs
    if "Lat" in df.columns:
        lat_vals = pd.to_numeric(df["Lat"], errors="coerce")
        # Lat/Lng stored as degrees * 1e7 integers in the fixture
        if lat_vals.abs().max() > 360:
            result["lat"] = lat_vals / 1e7
        else:
            result["lat"] = lat_vals
    if "Lng" in df.columns:
        lon_vals = pd.to_numeric(df["Lng"], errors="coerce")
        if lon_vals.abs().max() > 360:
            result["lon"] = lon_vals / 1e7
        else:
            result["lon"] = lon_vals
    if "Alt" in df.columns:
        result["alt"] = pd.to_numeric(df["Alt"], errors="coerce")
    if "Status" in df.columns:
        result["fix_type"] = pd.to_numeric(df["Status"], errors="coerce")
    if "NSats" in df.columns:
        result["satellites"] = pd.to_numeric(df["NSats"], errors="coerce")
    if "HDop" in df.columns:
        result["hdop"] = pd.to_numeric(df["HDop"], errors="coerce")

    return result


def _extract_imu_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """IMU -> vibration/accelerometer DataFrame."""
    rows = records.get("IMU", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    for src, dst in [("AccX", "accel_x"), ("AccY", "accel_y"), ("AccZ", "accel_z"), ("GyrX", "gyro_x"), ("GyrY", "gyro_y"), ("GyrZ", "gyro_z")]:
        if src in df.columns:
            result[dst] = pd.to_numeric(df[src], errors="coerce")
    return result


def _extract_vibe_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """VIBE -> vibration DataFrame."""
    rows = records.get("VIBE", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    for src, dst in [("VibeX", "vibration_x"), ("VibeY", "vibration_y"), ("VibeZ", "vibration_z")]:
        if src in df.columns:
            result[dst] = pd.to_numeric(df[src], errors="coerce")
    return result


def _extract_rcin_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """RCIN -> RC input DataFrame."""
    rows = records.get("RCIN", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    for col in df.columns:
        if col.startswith("C") and col[1:].isdigit():
            result[f"ch{col[1:]}"] = pd.to_numeric(df[col], errors="coerce")
    return result


def _extract_rcou_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """RCOU -> motor output DataFrame."""
    rows = records.get("RCOU", [])
    df = _records_to_df(rows)
    if df.empty:
        return df

    result = pd.DataFrame()
    result["timestamp"] = df["timestamp"]
    for i, col in enumerate([c for c in df.columns if c.startswith("C") and c[1:].isdigit()]):
        vals = pd.to_numeric(df[col], errors="coerce")
        # PWM range 1000-2000 → normalize to 0-1
        if vals.max() > 100:
            result[f"output_{i}"] = (vals - 1000.0) / 1000.0
        else:
            result[f"output_{i}"] = vals
    return result


def _extract_ekf_text(records: dict[str, list[dict]]) -> pd.DataFrame:
    """NKF4/XKF4 -> EKF DataFrame."""
    for key in ("NKF4", "XKF4", "NKF5", "XKF5"):
        rows = records.get(key, [])
        if rows:
            df = _records_to_df(rows)
            result = pd.DataFrame()
            result["timestamp"] = df["timestamp"]
            for col in df.columns:
                if col != "timestamp" and col != "TimeUS":
                    result[col] = pd.to_numeric(df[col], errors="coerce")
            return result
    return pd.DataFrame()


def _extract_mode_changes_text(records: dict[str, list[dict]]) -> list[ModeChange]:
    """MODE -> list of ModeChange."""
    rows = records.get("MODE", [])
    if not rows:
        return []

    changes: list[ModeChange] = []
    df = _records_to_df(rows)
    prev_mode = "none"

    for _, row in df.iterrows():
        ts = float(row["timestamp"])
        # MODE columns: TimeUS, Mode, ModeNum  (text format has mode name directly)
        if "Mode" in df.columns:
            mode_val = row.get("Mode", "")
            mode_name = str(mode_val).strip() if mode_val is not None else "unknown"
        elif "ModeNum" in df.columns:
            mode_name = f"mode_{int(row['ModeNum'])}"
        else:
            mode_name = "unknown"

        if mode_name != prev_mode:
            changes.append(
                ModeChange(
                    timestamp=ts,
                    from_mode=prev_mode,
                    to_mode=mode_name,
                )
            )
            prev_mode = mode_name

    return changes


def _extract_events_text(records: dict[str, list[dict]]) -> list[FlightEvent]:
    """ERR and EV messages -> list of FlightEvent."""
    events: list[FlightEvent] = []

    # ERR messages
    for row in records.get("ERR", []):
        ts = float(row.get("TimeUS", 0)) / 1e6
        subsys = row.get("Subsys", "")
        ecode = row.get("ECode", "")
        events.append(
            FlightEvent(
                timestamp=ts,
                event_type="error",
                severity="warning",
                message=f"Error: Subsys={subsys} ECode={ecode}",
            )
        )

    # EV events (arming/disarming/etc.)
    EV_NAMES = {
        10: "Armed",
        11: "Disarmed",
        15: "Arming Failed",
        16: "Emergency Stop Motors",
        25: "Takeoff",
        26: "Land",
    }
    for row in records.get("EV", []):
        ts = float(row.get("TimeUS", 0)) / 1e6
        ev_id = int(row.get("Id", 0)) if row.get("Id") is not None else 0
        msg = EV_NAMES.get(ev_id, f"Event {ev_id}")
        events.append(
            FlightEvent(
                timestamp=ts,
                event_type="info",
                severity="info",
                message=msg,
            )
        )

    # MSG messages
    for row in records.get("MSG", []):
        ts = float(row.get("TimeUS", 0)) / 1e6
        msg_text = str(row.get("Message", "")).strip()
        events.append(
            FlightEvent(
                timestamp=ts,
                event_type="info",
                severity="info",
                message=msg_text,
            )
        )

    events.sort(key=lambda e: e.timestamp)
    return events


def _extract_firmware_from_msg(records: dict[str, list[dict]]) -> str:
    """Try to extract firmware version from MSG messages."""
    for row in records.get("MSG", []):
        msg = str(row.get("Message", "")).strip()
        if "ArduCopter" in msg or "ArduPlane" in msg or "ArduRover" in msg:
            return msg.split()[0] if msg else "unknown"
    return "unknown"


def _infer_vehicle_type_from_mode(mode_changes: list[ModeChange]) -> str:
    """Rough vehicle type inference from mode names."""
    copter_modes = {"stabilize", "alt_hold", "loiter", "auto", "guided", "sport", "drift", "poshold", "brake", "throw"}
    plane_modes = {"manual", "fbwa", "fbwb", "cruise", "autotune", "fly_by_wire_a"}
    rover_modes = {"hold", "steering", "acro", "guided"}

    mode_names = {mc.to_mode.lower().replace(" ", "_") for mc in mode_changes}
    if mode_names & copter_modes:
        return "quadcopter"
    if mode_names & plane_modes:
        return "fixedwing"
    if mode_names & rover_modes:
        return "rover"
    return "quadcopter"  # ArduPilot default assumption


# ---------------------------------------------------------------------------
# Binary format parser helpers
# ---------------------------------------------------------------------------


def _parse_binary_dataflash(data: bytes) -> dict[str, list[dict[str, Any]]]:
    """Best-effort binary DataFlash parser.

    Reads FMT definitions and then attempts to parse known message types.
    Silently skips malformed or unknown messages.
    """
    fmt_defs: dict[int, dict[str, Any]] = {}  # type_byte -> descriptor
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)

    i = 0
    n = len(data)

    while i < n - 2:
        # Scan for header bytes
        if data[i] != 0xA3 or data[i + 1] != 0x95:
            i += 1
            continue

        if i + 3 > n:
            break

        msg_type = data[i + 2]
        i += 3

        if msg_type == FMT_TYPE:
            # FMT message: type(1), length(1), name(4), fmt(16), columns(64)
            if i + 86 > n:
                break
            try:
                sub_type = data[i]
                # length = data[i+1]
                name = data[i + 2 : i + 6].rstrip(b"\x00").decode("ascii", errors="ignore")
                fmt_str = data[i + 6 : i + 22].rstrip(b"\x00").decode("ascii", errors="ignore")
                cols_raw = data[i + 22 : i + 86].rstrip(b"\x00").decode("ascii", errors="ignore")
                columns = [c.strip() for c in cols_raw.split(",") if c.strip()]

                # Build struct format
                struct_chars = "".join(_FMT_CHAR_MAP.get(c, "") for c in fmt_str)
                try:
                    size = struct.calcsize("<" + struct_chars)
                except struct.error:
                    size = 0

                fmt_defs[sub_type] = {
                    "name": name,
                    "fmt_str": fmt_str,
                    "struct_fmt": "<" + struct_chars,
                    "columns": columns,
                    "size": size,
                }
            except (struct.error, ValueError, UnicodeDecodeError) as exc:
                logger.debug("FMT record parse error at offset %d: %s", i, exc)
            i += 86

        elif msg_type in fmt_defs:
            desc = fmt_defs[msg_type]
            size = desc["size"]
            if size == 0 or i + size > n:
                i += 1
                continue
            try:
                values = struct.unpack(desc["struct_fmt"], data[i : i + size])
                # Decode bytes fields
                decoded = []
                fmt_chars = desc["fmt_str"]
                for val, fc in zip(values, fmt_chars, strict=False):
                    if isinstance(val, bytes):
                        decoded.append(val.rstrip(b"\x00").decode("ascii", errors="ignore"))
                    elif fc in _SCALE_100:
                        decoded.append(val / 100.0)
                    elif fc in _SCALE_LAT_LON:
                        decoded.append(val / 1e7)
                    else:
                        decoded.append(val)

                cols = desc["columns"]
                row = {cols[j]: decoded[j] for j in range(min(len(cols), len(decoded)))}
                records[desc["name"]].append(row)
                i += size
            except (struct.error, ValueError, UnicodeDecodeError) as exc:
                logger.debug("Binary record parse error at offset %d (type %d): %s", i, msg_type, exc)
                i += 1
        else:
            i += 1

    return dict(records)


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------


class DataFlashParser(BaseParser):
    """ArduPilot DataFlash (.log text format, .bin binary format) parser."""

    format_name = "dataflash"
    file_extensions = [".bin", ".log"]
    implemented = True

    PARSER_VERSION = "1.0.0"

    def parse(self, filepath: str | Path) -> ParseResult:
        """Parse a DataFlash file and return a ParseResult.

        Never raises — all exceptions are caught and returned as failures.
        """
        filepath = Path(filepath)
        t0 = time.monotonic()

        diag = ParseDiagnostics(
            parser_selected="dataflash",
            parser_version=self.PARSER_VERSION,
            detected_format="dataflash",
            format_confidence=0.9,
            supported=True,
            parse_started_at=datetime.now().replace(microsecond=0),
            confidence_scope="parser_parse_quality",
        )

        # --- File existence check ------------------------------------------
        if not filepath.exists():
            diag.errors.append(f"File not found: {filepath}")
            diag.parser_confidence = 0.0
            return ParseResult.failure(diag)

        # --- Read raw bytes -------------------------------------------------
        try:
            raw_bytes = filepath.read_bytes()
        except OSError as exc:
            diag.errors.append(f"Cannot read file: {exc}")
            diag.parser_confidence = 0.0
            return ParseResult.failure(diag)

        if len(raw_bytes) == 0:
            diag.errors.append("File is empty.")
            diag.parser_confidence = 0.0
            diag.parse_completed_at = datetime.now().replace(microsecond=0)
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        # --- Format detection (binary vs text) -----------------------------
        is_binary = len(raw_bytes) >= 2 and raw_bytes[0] == BINARY_HEADER[0] and raw_bytes[1] == BINARY_HEADER[1]

        if not is_binary:
            # Try decoding as text
            try:
                raw_text = raw_bytes.decode("utf-8", errors="replace")
            except (UnicodeDecodeError, ValueError) as exc:
                logger.debug("Text decode failed for DataFlash log: %s", exc)
                raw_text = ""
            # Confirm it's actually DataFlash text by looking for FMT lines
            if "FMT" not in raw_text[:4096]:
                diag.errors.append("File does not appear to be a DataFlash log (no FMT definitions found and no binary header).")
                diag.parser_confidence = 0.1
                diag.parse_completed_at = datetime.now().replace(microsecond=0)
                diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
                return ParseResult.failure(diag)

        source_format = "ardupilot_dataflash_binary" if is_binary else "ardupilot_dataflash_text"
        diag.detected_format = source_format

        # --- Parse ---------------------------------------------------------
        try:
            if is_binary:
                records = _parse_binary_dataflash(raw_bytes)
            else:
                records = _parse_text_dataflash(raw_text)
        except (struct.error, ValueError, UnicodeDecodeError, OSError) as exc:
            diag.errors.append(f"Parse failed: {exc}")
            diag.parser_confidence = 0.0
            diag.parse_completed_at = datetime.now().replace(microsecond=0)
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        # --- Extract streams -----------------------------------------------
        try:
            attitude = _extract_attitude_text(records)
            position = _extract_baro_text(records)  # BARO gives altitude
            battery = _extract_battery_text(records)
            gps = _extract_gps_text(records)
            imu_vib = _extract_imu_text(records)
            vibe = _extract_vibe_text(records)
            vibration = imu_vib if not imu_vib.empty else vibe
            rc_input = _extract_rcin_text(records)
            motors = _extract_rcou_text(records)
            ekf = _extract_ekf_text(records)
            mode_changes = _extract_mode_changes_text(records)
            events = _extract_events_text(records)
            fw_version = _extract_firmware_from_msg(records)
            vehicle_type = _infer_vehicle_type_from_mode(mode_changes)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            diag.errors.append(f"Stream extraction failed: {exc}")
            diag.parser_confidence = 0.0
            diag.parse_completed_at = datetime.now().replace(microsecond=0)
            diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return ParseResult.failure(diag)

        # --- Compute duration ----------------------------------------------
        duration_sec = 0.0
        all_timestamps: list[float] = []
        for df in [attitude, position, battery, gps, vibration, rc_input, motors, ekf]:
            if not df.empty and "timestamp" in df.columns:
                all_timestamps.extend(df["timestamp"].dropna().tolist())
        if all_timestamps:
            duration_sec = max(all_timestamps)

        # --- Stream coverage audit ----------------------------------------
        STREAM_MAP = {
            "attitude": attitude,
            "altitude": position,
            "battery": battery,
            "gps": gps,
            "vibration": vibration,
            "rc_input": rc_input,
            "motors": motors,
            "ekf": ekf,
        }
        coverage: list[StreamCoverage] = []
        missing: list[str] = []
        for name, df in STREAM_MAP.items():
            if not df.empty:
                coverage.append(
                    StreamCoverage(
                        stream_name=name,
                        present=True,
                        row_count=len(df),
                    )
                )
            else:
                coverage.append(StreamCoverage(stream_name=name, present=False))
                missing.append(name)

        diag.stream_coverage = coverage
        diag.missing_streams = missing

        if "battery" in missing:
            diag.warnings.append("Battery stream (BAT/POWR) not found — battery analysis unavailable.")
        if "gps" in missing:
            diag.warnings.append("GPS stream not found — position analysis unavailable.")
        if "attitude" in missing:
            diag.warnings.append("ATT stream not found — attitude analysis unavailable.")

        # --- Confidence scoring -------------------------------------------
        confidence = 0.8  # DataFlash base (slightly below ULog as format is less standardised)
        critical_missing = {"attitude", "gps", "battery"}
        for stream in missing:
            if stream in critical_missing:
                confidence -= 0.10
        if not mode_changes:
            confidence -= 0.05
        diag.parser_confidence = max(0.0, round(confidence, 2))

        # --- Metadata -------------------------------------------------
        motor_count = 4  # ArduCopter default
        if vehicle_type == "hexcopter":
            motor_count = 6
        elif vehicle_type == "octocopter":
            motor_count = 8
        elif vehicle_type == "fixedwing":
            motor_count = 1

        metadata = FlightMetadata(
            source_file=str(filepath),
            autopilot="ardupilot",
            firmware_version=fw_version,
            vehicle_type=vehicle_type,
            frame_type=None,
            hardware=None,
            duration_sec=duration_sec,
            start_time_utc=None,
            log_format=source_format.replace("ardupilot_dataflash_", "dataflash_"),
            motor_count=motor_count,
        )

        # --- Build Flight -------------------------------------------------
        flight = Flight(
            metadata=metadata,
            attitude=attitude,
            position=position,
            battery=battery,
            gps=gps,
            vibration=vibration,
            rc_input=rc_input,
            motors=motors,
            ekf=ekf,
            mode_changes=mode_changes,
            events=events,
        )

        # --- Finalize diagnostics ----------------------------------------
        diag.parse_completed_at = datetime.now().replace(microsecond=0)
        diag.parse_duration_ms = round((time.monotonic() - t0) * 1000, 1)
        diag.assumptions.append("TimeUS column treated as microseconds since log start (first record = t=0).")
        diag.parse_artifacts = {"message_types_found": sorted(records.keys())}

        # --- Provenance --------------------------------------------------
        provenance = Provenance(
            source_evidence_id="",
            parser_name="dataflash",
            parser_version=self.PARSER_VERSION,
            detected_format=source_format,
            parsed_at=diag.parse_started_at,
            transformation_chain=[f"raw_{source_format} -> canonical_flight"],
            engine_version=_engine_version,
            assumptions=list(diag.assumptions),
        )

        return ParseResult(
            flight=flight,
            diagnostics=diag,
            provenance=provenance,
            parse_artifacts=diag.parse_artifacts,
        )
