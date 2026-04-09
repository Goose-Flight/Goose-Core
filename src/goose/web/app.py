"""Goose embedded web UI — FastAPI application factory."""

import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


def _downsample(arr: list, max_points: int = 2000) -> list:
    """Downsample a list to max_points using stride-based selection."""
    if len(arr) <= max_points:
        return arr
    stride = len(arr) / max_points
    return [arr[int(i * stride)] for i in range(max_points)]


def _safe_val(v: Any) -> Any:
    """Convert numpy/pandas values to JSON-safe Python types."""
    if v is None:
        return None
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            if np.isnan(v) or np.isinf(v):
                return None
            return float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
    except (ImportError, TypeError, ValueError):
        pass
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
    return v


def _df_to_series(df: Any, columns: list[str] | None = None, max_points: int = 2000) -> dict[str, list] | None:
    """Convert a pandas DataFrame to JSON-ready dict of downsampled arrays.

    Returns {"timestamps": [...], "col1": [...], "col2": [...]} or None if empty.
    """
    if df is None or df.empty:
        return None

    if columns is None:
        columns = [c for c in df.columns if c != "timestamp"]

    if "timestamp" not in df.columns or not columns:
        return None

    result: dict[str, list] = {}
    ts = df["timestamp"].tolist()
    ts_ds = _downsample(ts, max_points)
    result["timestamps"] = [_safe_val(t) for t in ts_ds]

    stride = len(ts) / len(ts_ds) if len(ts) > max_points else 1
    indices = [int(i * stride) for i in range(len(ts_ds))] if stride > 1 else list(range(len(ts)))

    for col in columns:
        if col in df.columns:
            vals = df[col].tolist()
            result[col] = [_safe_val(vals[i]) for i in indices]

    return result


def _extract_timeseries(flight: Any) -> dict[str, Any]:
    """Extract downsampled time-series data from a Flight for frontend charting."""
    ts: dict[str, Any] = {}

    # Altitude
    pos = _df_to_series(flight.position, ["alt_rel", "alt_msl", "lat", "lon"])
    if pos:
        ts["altitude"] = pos

    # Battery
    bat = _df_to_series(flight.battery, ["voltage", "current", "remaining_pct"])
    if bat:
        ts["battery"] = bat

    # Motors
    if not flight.motors.empty:
        motor_cols = [c for c in flight.motors.columns if c.startswith("output_")]
        mot = _df_to_series(flight.motors, motor_cols)
        if mot:
            ts["motors"] = mot

    # Attitude (convert radians to degrees for display)
    if not flight.attitude.empty:
        import numpy as np
        att_df = flight.attitude.copy()
        for col in ["roll", "pitch", "yaw"]:
            if col in att_df.columns:
                att_df[col] = np.degrees(att_df[col])
        att = _df_to_series(att_df, ["roll", "pitch", "yaw"])
        if att:
            ts["attitude"] = att

    # Attitude setpoint
    if not flight.attitude_setpoint.empty:
        import numpy as np
        sp_df = flight.attitude_setpoint.copy()
        for col in ["roll", "pitch", "yaw"]:
            if col in sp_df.columns:
                sp_df[col] = np.degrees(sp_df[col])
        sp = _df_to_series(sp_df, ["roll", "pitch", "yaw"])
        if sp:
            ts["attitude_setpoint"] = sp

    # Vibration
    vib = _df_to_series(flight.vibration, ["accel_x", "accel_y", "accel_z"])
    if vib:
        ts["vibration"] = vib

    # GPS
    gps = _df_to_series(flight.gps, ["satellites", "hdop", "fix_type"])
    if gps:
        ts["gps"] = gps

    # EKF
    if not flight.ekf.empty:
        ekf_cols = [c for c in flight.ekf.columns if c != "timestamp"][:8]  # limit columns
        ekf = _df_to_series(flight.ekf, ekf_cols)
        if ekf:
            ts["ekf"] = ekf

    # RC signal
    if not flight.rc_input.empty:
        rc = _df_to_series(flight.rc_input, ["rssi"])
        if rc:
            ts["rc"] = rc

    # Velocity
    vel = _df_to_series(flight.velocity, ["vx", "vy", "vz"])
    if vel:
        ts["velocity"] = vel

    # Mode changes
    ts["mode_changes"] = [
        {"timestamp": mc.timestamp, "from_mode": mc.from_mode, "to_mode": mc.to_mode}
        for mc in flight.mode_changes
    ]

    # Events
    ts["events"] = [
        {"timestamp": ev.timestamp, "type": ev.event_type, "severity": ev.severity, "message": ev.message}
        for ev in flight.events
    ]

    return ts


def _finding_to_dict(finding: Any) -> dict[str, Any]:
    """Serialize a Finding dataclass to a JSON-safe dict."""
    evidence = finding.evidence or {}
    # Walk evidence values and sanitize non-serializable types (numpy scalars, etc.)
    safe_evidence: dict[str, Any] = {}
    for k, v in evidence.items():
        try:
            import json
            json.dumps(v)
            safe_evidence[k] = v
        except (TypeError, ValueError):
            safe_evidence[k] = str(v)

    return {
        "plugin_name": finding.plugin_name,
        "title": finding.title,
        "severity": finding.severity,
        "score": int(finding.score),
        "description": finding.description,
        "evidence": safe_evidence,
        "phase": finding.phase,
        "timestamp_start": finding.timestamp_start,
        "timestamp_end": finding.timestamp_end,
    }


def _compute_overall_score(findings: list[Any]) -> int:
    """Compute a weighted overall score (0-100) from all findings."""
    from goose.core.scoring import compute_overall_score
    return compute_overall_score(findings)


def create_app():
    """Create and return the FastAPI application."""
    app = FastAPI(
        title="Goose Flight Analyzer",
        description="Drone flight log validation and crash analysis",
        version="1.0.0",
    )

    # ------------------------------------------------------------------
    # Static files
    # ------------------------------------------------------------------
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # ------------------------------------------------------------------
    # Case-oriented routes (Sprint 2+)
    # ------------------------------------------------------------------
    from goose.web.cases_api import router as cases_router
    app.include_router(cases_router)

    # Validation harness routes (Advanced Forensic Validation Sprint)
    from goose.web.routes.validation import router as validation_router
    app.include_router(validation_router)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        """Serve the single-page HTML application."""
        html_path = _STATIC_DIR / "index.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(
            str(html_path),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/api/plugins")
    async def list_plugins() -> JSONResponse:
        """Return metadata for all discovered plugins."""
        try:
            from goose.plugins.registry import load_plugins
            plugins = load_plugins()
            return JSONResponse({
                "plugins": [
                    {
                        "name": p.name,
                        "description": p.description,
                        "version": p.version,
                        "min_mode": p.min_mode,
                    }
                    for p in plugins
                ],
                "count": len(plugins),
            })
        except Exception as exc:
            logger.exception("Failed to list plugins")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/analyze")
    async def analyze(file: UploadFile = File(...)) -> JSONResponse:
        """
        Accept a flight log upload, run all plugins, and return analysis results.

        Supported formats: .ulg (ULog/PX4), .bin/.log (DataFlash/ArduPilot),
        .tlog (MAVLink telemetry), .csv (generic CSV).
        """
        if file.filename is None or file.filename == "":
            raise HTTPException(status_code=400, detail="No filename provided")

        original_name = Path(file.filename)
        suffix = original_name.suffix.lower()

        # Write upload to a named temp file (suffix matters for parsers)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=suffix, delete=False, prefix="goose_upload_"
            ) as tmp:
                tmp_path = tmp.name
                content = await file.read()
                if not content:
                    raise HTTPException(status_code=400, detail="Uploaded file is empty")
                tmp.write(content)

            # ----------------------------------------------------------
            # Parser selection via formal ParseResult contract
            # ----------------------------------------------------------
            from goose.parsers.detect import parse_file as _parse_file
            _parse_result = _parse_file(tmp_path)
            if not _parse_result.success:
                errors = "; ".join(_parse_result.diagnostics.errors)
                detail = (
                    f"Could not parse '{original_name.name}'. "
                    f"Supported format: .ulg. Error: {errors}"
                )
                raise HTTPException(status_code=422, detail=detail)
            flight = _parse_result.flight

            # ----------------------------------------------------------
            # Run plugins
            # ----------------------------------------------------------
            try:
                from goose.plugins.registry import load_plugins
                plugins = load_plugins()
            except Exception as exc:
                logger.warning("Plugin loading failed: %s", exc)
                plugins = []

            all_findings: list[Any] = []
            plugin_errors: list[dict[str, str]] = []

            for plugin in plugins:
                try:
                    findings = plugin.analyze(flight, {})
                    all_findings.extend(findings)
                except Exception as exc:
                    logger.warning("Plugin %s failed: %s", plugin.name, exc)
                    plugin_errors.append({"plugin": plugin.name, "error": str(exc)})

            # ----------------------------------------------------------
            # Build response
            # ----------------------------------------------------------
            overall_score = _compute_overall_score(all_findings)

            meta = flight.metadata
            start_time_str: str | None = None
            if meta.start_time_utc is not None:
                start_time_str = meta.start_time_utc.isoformat()

            duration_sec = meta.duration_sec
            duration_str = _format_duration(duration_sec)

            findings_by_severity: dict[str, int] = {
                "critical": 0,
                "warning": 0,
                "info": 0,
                "pass": 0,
            }
            for f in all_findings:
                sev = f.severity if f.severity in findings_by_severity else "info"
                findings_by_severity[sev] += 1

            # Extract time-series for cockpit charts
            try:
                timeseries = _extract_timeseries(flight)
            except Exception as ts_exc:
                logger.warning("Time-series extraction failed: %s", ts_exc)
                timeseries = {}

            # Generate flight narrative
            try:
                from goose.core.narrative import generate_narrative, generate_human_narrative
                narr_meta = {
                    "duration_str": duration_str,
                    "vehicle_type": meta.vehicle_type,
                    "primary_mode": flight.primary_mode,
                    "firmware_version": meta.firmware_version,
                    "hardware": meta.hardware,
                    "crashed": flight.crashed,
                }
                narrative = generate_narrative(
                    all_findings, metadata=narr_meta, overall_score=overall_score,
                )
                narrative_human = generate_human_narrative(
                    all_findings, metadata=narr_meta, overall_score=overall_score,
                )
            except Exception as narr_exc:
                logger.warning("Narrative generation failed: %s", narr_exc)
                narrative = None
                narrative_human = None

            return JSONResponse({
                "ok": True,
                "overall_score": overall_score,
                "narrative": narrative,
                "narrative_human": narrative_human,
                "timeseries": timeseries,
                "metadata": {
                    "filename": original_name.name,
                    "autopilot": meta.autopilot,
                    "vehicle_type": meta.vehicle_type,
                    "firmware_version": meta.firmware_version,
                    "hardware": meta.hardware,
                    "duration_sec": round(duration_sec, 1),
                    "duration_str": duration_str,
                    "start_time_utc": start_time_str,
                    "log_format": meta.log_format,
                    "motor_count": meta.motor_count,
                    "primary_mode": flight.primary_mode,
                    "crashed": flight.crashed,
                },
                "summary": {
                    "total_findings": len(all_findings),
                    "by_severity": findings_by_severity,
                    "plugins_run": len(plugins),
                    "plugin_errors": plugin_errors,
                },
                "findings": [_finding_to_dict(f) for f in all_findings],
            })

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unexpected error during analysis")
            raise HTTPException(
                status_code=500,
                detail=f"Internal analysis error: {exc}",
            ) from exc
        finally:
            # Always clean up the temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_all_parsers(filepath: str, prior_error: str | None) -> tuple[Any, str | None]:
    """Attempt to parse a file with all available parsers in priority order."""
    parsers_to_try: list[tuple[str, str]] = [
        ("goose.parsers.dataflash", "DataFlashParser"),
        ("goose.parsers.tlog", "TlogParser"),
        ("goose.parsers.csv_parser", "CsvParser"),
    ]

    last_error = prior_error
    for module_path, class_name in parsers_to_try:
        try:
            import importlib
            module = importlib.import_module(module_path)
            parser_cls = getattr(module, class_name)
            parser = parser_cls()
            if parser.can_parse(filepath):
                flight = parser.parse(filepath)
                return flight, None
        except Exception as exc:
            last_error = str(exc)
            logger.debug("Parser %s.%s failed: %s", module_path, class_name, exc)

    return None, last_error


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if not math.isfinite(seconds) or seconds < 0:
        return "unknown"
    total_sec = int(round(seconds))
    hours, remainder = divmod(total_sec, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


# Module-level app instance for uvicorn ("goose.web.app:app")
app = create_app()
