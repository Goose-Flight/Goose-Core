"""Charts data route.

Extracted from cases_api.py during API modularization sprint.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["charts"])


@router.get("/{case_id}/charts/data")
async def get_charts_data(case_id: str, streams: str = "", start: float = 0.0, end: float = 0.0) -> JSONResponse:
    """Return time-series data for requested streams from canonical flight data."""
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    case_dir = svc.case_dir(case_id)

    result_streams: dict[str, Any] = {}
    stream_list = [s.strip() for s in streams.split(",") if s.strip()]

    # Try cached canonical flight data
    canonical_path = case_dir / "parsed" / "canonical_flight.json"
    if canonical_path.exists():
        try:
            canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
            for stream_name in stream_list:
                if stream_name in canonical:
                    sd = canonical[stream_name]
                    times = sd.get("times", [])
                    values = sd.get("values", [])
                    units = sd.get("units", "")
                    # Apply time filter
                    if end > start and times:
                        filtered_t = []
                        filtered_v = []
                        for t, v in zip(times, values, strict=False):
                            if start <= t <= end:
                                filtered_t.append(t)
                                filtered_v.append(v)
                        times = filtered_t
                        values = filtered_v
                    result_streams[stream_name] = {
                        "times": times,
                        "values": values,
                        "units": units,
                    }
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass

    # If no canonical file, try re-parsing evidence to extract streams
    if not result_streams and stream_list:
        ev_dir = case_dir / "evidence"
        if ev_dir.exists():
            ev_files = list(ev_dir.iterdir())
            if ev_files:
                try:
                    from goose.parsers.detect import parse_file

                    pr = parse_file(str(ev_files[0]))
                    if pr and pr.success and pr.flight:
                        flight = pr.flight
                        _STREAM_ATTR_MAP = {
                            "battery_voltage": ("battery", "voltage", "V"),
                            "altitude_m": ("position", "alt_rel", "m"),
                            "altitude_msl": ("position", "alt_msl", "m"),
                            "velocity_m_s": ("velocity", "velocity", "m/s"),
                            "roll_deg": ("attitude", "roll", "rad"),
                            "pitch_deg": ("attitude", "pitch", "rad"),
                            "yaw_deg": ("attitude", "yaw", "rad"),
                            "motor_0": ("motors", "output_0", ""),
                            "gps_nsats": ("gps", "satellites_visible", ""),
                            "vibration_x": ("vibration", "accel_x", "m/s2"),
                            "battery_current": ("battery", "current", "A"),
                            "battery_remaining": ("battery", "remaining_pct", "%"),
                        }
                        for stream_name in stream_list:
                            if stream_name in _STREAM_ATTR_MAP:
                                attr, col, units = _STREAM_ATTR_MAP[stream_name]
                                df = getattr(flight, attr, None)
                                if df is not None and not df.empty and "timestamp" in df.columns and col in df.columns:
                                    times = df["timestamp"].tolist()
                                    values = df[col].tolist()
                                    clean_t, clean_v = [], []
                                    for t, v in zip(times, values, strict=False):
                                        if t is not None and v is not None:
                                            try:
                                                tf = float(t)
                                                vf = float(v)
                                                if not (math.isnan(tf) or math.isinf(tf) or math.isnan(vf) or math.isinf(vf)):
                                                    if end > start:
                                                        if start <= tf <= end:
                                                            clean_t.append(tf)
                                                            clean_v.append(vf)
                                                    else:
                                                        clean_t.append(tf)
                                                        clean_v.append(vf)
                                            except (TypeError, ValueError):
                                                pass
                                    result_streams[stream_name] = {
                                        "times": clean_t,
                                        "values": clean_v,
                                        "units": units,
                                    }
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Chart data re-parse failed: %s", exc)

    return JSONResponse(
        {
            "ok": True,
            "streams": result_streams,
            "available_streams": [
                "battery_voltage",
                "altitude_m",
                "altitude_msl",
                "velocity_m_s",
                "roll_deg",
                "pitch_deg",
                "yaw_deg",
                "motor_0",
                "gps_nsats",
                "vibration_x",
                "battery_current",
                "battery_remaining",
            ],
            "message": "" if result_streams else "No chart data available. Run analysis first or request valid stream names.",
        }
    )
