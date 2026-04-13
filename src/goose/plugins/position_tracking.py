"""Position tracking analysis plugin — compares actual vs commanded position."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest

# Thresholds
WARN_MEAN_ERROR_M = 3.0  # warn if mean horizontal error > 3m
CRITICAL_MEAN_ERROR_M = 10.0  # critical if mean horizontal error > 10m
WARN_VERT_ERROR_M = 2.0  # warn if mean vertical error > 2m
CRITICAL_VERT_ERROR_M = 5.0  # critical if mean vertical error > 5m
HOVER_DRIFT_M = 1.0  # drift during hover > 1m flagged
LOW_VELOCITY_THRESHOLD = 0.5  # m/s — below this = hovering


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return float(2 * R * np.arcsin(np.sqrt(a)))


class PositionTrackingPlugin(Plugin):
    """Analyse position tracking error vs commanded setpoints."""

    name = "position_tracking"
    description = "Position tracking error vs commanded position"
    version = "1.0.0"
    min_mode = "position"

    manifest = PluginManifest(
        plugin_id="position_tracking",
        name="Position Tracking",
        version="1.0.0",
        author="Goose Flight",
        description="Compares actual vs commanded position to quantify tracking error and hover drift",
        category=PluginCategory.NAVIGATION,
        supported_vehicle_types=["multirotor", "all"],
        required_streams=["position", "position_setpoint"],
        optional_streams=["velocity"],
        output_finding_types=["horizontal_error", "vertical_error", "hover_drift"],
        primary_stream="position",
    )

    DEFAULT_WARN_MEAN_ERROR_M = WARN_MEAN_ERROR_M
    DEFAULT_CRITICAL_MEAN_ERROR_M = CRITICAL_MEAN_ERROR_M
    DEFAULT_WARN_VERT_ERROR_M = WARN_VERT_ERROR_M
    DEFAULT_CRITICAL_VERT_ERROR_M = CRITICAL_VERT_ERROR_M
    DEFAULT_HOVER_DRIFT_M = HOVER_DRIFT_M
    DEFAULT_LOW_VELOCITY_THRESHOLD_MS = LOW_VELOCITY_THRESHOLD

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []
        cfg = config or {}
        warn_err = float(cfg.get("warn_mean_error_m", WARN_MEAN_ERROR_M))
        crit_err = float(cfg.get("critical_mean_error_m", CRITICAL_MEAN_ERROR_M))
        warn_vert = float(cfg.get("warn_vert_error_m", WARN_VERT_ERROR_M))
        crit_vert = float(cfg.get("critical_vert_error_m", CRITICAL_VERT_ERROR_M))
        hover_drift = float(cfg.get("hover_drift_m", HOVER_DRIFT_M))
        low_vel = float(cfg.get("low_velocity_threshold_ms", LOW_VELOCITY_THRESHOLD))

        if not flight.has_position_setpoints:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="No position setpoint data available",
                    severity="info",
                    score=50,
                    description=(
                        "Position setpoint data is not present in this flight log. "
                        "Position tracking analysis requires a flight mode that commands "
                        "position setpoints (e.g. Position, Mission)."
                    ),
                )
            )
            return findings

        if flight.position is None or flight.position.empty:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="No position data available",
                    severity="info",
                    score=50,
                    description="Position data is missing from the flight log.",
                )
            )
            return findings

        pos = flight.position.copy()
        sp = flight.position_setpoint.copy()

        # Require timestamp in both DataFrames
        if "timestamp" not in pos.columns or "timestamp" not in sp.columns:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="Position data missing timestamp column",
                    severity="info",
                    score=50,
                    description="Cannot merge position and setpoint data without timestamps.",
                )
            )
            return findings

        # Merge on nearest timestamp
        merged = pd.merge_asof(
            pos.sort_values("timestamp"),
            sp.sort_values("timestamp").add_suffix("_sp"),
            left_on="timestamp",
            right_on="timestamp_sp",
            direction="nearest",
            tolerance=1.0,
        )

        if merged.empty:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="Could not merge position and setpoint data",
                    severity="info",
                    score=50,
                    description="Position and setpoint DataFrames could not be aligned by timestamp.",
                )
            )
            return findings

        findings.extend(self._check_horizontal_error(merged, warn_err, crit_err))
        findings.extend(self._check_vertical_error(merged, warn_vert, crit_vert))
        findings.extend(self._check_hover_drift(merged, flight, hover_drift, low_vel, crit_err))

        return findings

    # ------------------------------------------------------------------
    # Horizontal position error
    # ------------------------------------------------------------------

    def _check_horizontal_error(
        self,
        merged: pd.DataFrame,
        WARN_MEAN_ERROR_M: float = WARN_MEAN_ERROR_M,
        CRITICAL_MEAN_ERROR_M: float = CRITICAL_MEAN_ERROR_M,
    ) -> list[Finding]:
        """Compute horizontal distance between actual and setpoint position."""
        # Need lat/lon in both actual and setpoint
        has_actual = "lat" in merged.columns and "lon" in merged.columns
        has_sp_latlon = "lat_sp" in merged.columns and "lon_sp" in merged.columns

        if not has_actual or not has_sp_latlon:
            # Fall back to x/y if available
            has_xy = "x" in merged.columns and "y" in merged.columns
            has_xy_sp = "x_sp" in merged.columns and "y_sp" in merged.columns
            if not has_xy or not has_xy_sp:
                return []
            df = merged[["timestamp", "x", "y", "x_sp", "y_sp"]].dropna()
            if df.empty:
                return []
            horiz_errors = np.sqrt((df["x"] - df["x_sp"]) ** 2 + (df["y"] - df["y_sp"]) ** 2)
        else:
            df = merged[["timestamp", "lat", "lon", "lat_sp", "lon_sp"]].dropna()
            if df.empty:
                return []
            horiz_errors = pd.Series([_haversine_m(row["lat"], row["lon"], row["lat_sp"], row["lon_sp"]) for _, row in df.iterrows()], index=df.index)

        mean_err = float(horiz_errors.mean())
        max_err = float(horiz_errors.max())
        ts = df["timestamp"]

        if mean_err > CRITICAL_MEAN_ERROR_M:
            severity = "critical"
            score = 15
        elif mean_err > WARN_MEAN_ERROR_M:
            severity = "warning"
            score = 55
        else:
            severity = "pass"
            score = 95

        return [
            Finding(
                plugin_name=self.name,
                title=(f"Horizontal position error — mean {mean_err:.1f}m" if severity != "pass" else "Horizontal position tracking nominal"),
                severity=severity,
                score=score,
                description=(
                    f"Mean horizontal position error: {mean_err:.2f}m, "
                    f"maximum: {max_err:.2f}m. "
                    f"Thresholds — warning: {WARN_MEAN_ERROR_M}m, critical: {CRITICAL_MEAN_ERROR_M}m."
                ),
                evidence={
                    "mean_error_m": round(mean_err, 3),
                    "max_error_m": round(max_err, 3),
                    "warn_threshold_m": WARN_MEAN_ERROR_M,
                    "critical_threshold_m": CRITICAL_MEAN_ERROR_M,
                    "sample_count": len(horiz_errors),
                },
                timestamp_start=float(ts.iloc[0]) if not ts.empty else None,
                timestamp_end=float(ts.iloc[-1]) if not ts.empty else None,
            )
        ]

    # ------------------------------------------------------------------
    # Vertical position error
    # ------------------------------------------------------------------

    def _check_vertical_error(
        self,
        merged: pd.DataFrame,
        WARN_VERT_ERROR_M: float = WARN_VERT_ERROR_M,
        CRITICAL_VERT_ERROR_M: float = CRITICAL_VERT_ERROR_M,
    ) -> list[Finding]:
        """Check altitude error vs commanded altitude."""
        alt_col = None
        alt_sp_col = None

        for candidate in ("alt_rel", "alt_msl", "z"):
            if candidate in merged.columns:
                alt_col = candidate
                break
        for candidate in ("alt_rel_sp", "alt_msl_sp", "z_sp"):
            if candidate in merged.columns:
                alt_sp_col = candidate
                break

        if alt_col is None or alt_sp_col is None:
            return []

        df = merged[["timestamp", alt_col, alt_sp_col]].dropna()
        if df.empty:
            return []

        vert_errors = (df[alt_col] - df[alt_sp_col]).abs()
        mean_err = float(vert_errors.mean())
        max_err = float(vert_errors.max())
        ts = df["timestamp"]

        if mean_err > CRITICAL_VERT_ERROR_M:
            severity = "critical"
            score = 15
        elif mean_err > WARN_VERT_ERROR_M:
            severity = "warning"
            score = 55
        else:
            severity = "pass"
            score = 95

        return [
            Finding(
                plugin_name=self.name,
                title=(f"Vertical position error — mean {mean_err:.1f}m" if severity != "pass" else "Vertical position tracking nominal"),
                severity=severity,
                score=score,
                description=(
                    f"Mean vertical (altitude) error: {mean_err:.2f}m, "
                    f"maximum: {max_err:.2f}m. "
                    f"Thresholds — warning: {WARN_VERT_ERROR_M}m, critical: {CRITICAL_VERT_ERROR_M}m."
                ),
                evidence={
                    "mean_error_m": round(mean_err, 3),
                    "max_error_m": round(max_err, 3),
                    "warn_threshold_m": WARN_VERT_ERROR_M,
                    "critical_threshold_m": CRITICAL_VERT_ERROR_M,
                    "sample_count": len(vert_errors),
                },
                timestamp_start=float(ts.iloc[0]) if not ts.empty else None,
                timestamp_end=float(ts.iloc[-1]) if not ts.empty else None,
            )
        ]

    # ------------------------------------------------------------------
    # Hover drift
    # ------------------------------------------------------------------

    def _check_hover_drift(
        self,
        merged: pd.DataFrame,
        flight: Flight,
        HOVER_DRIFT_M: float = HOVER_DRIFT_M,
        LOW_VELOCITY_THRESHOLD: float = LOW_VELOCITY_THRESHOLD,
        CRITICAL_MEAN_ERROR_M: float = CRITICAL_MEAN_ERROR_M,
    ) -> list[Finding]:
        """Detect position drift while vehicle is hovering (low velocity)."""
        # Need velocity data to detect hover
        if flight.velocity is None or flight.velocity.empty:
            return []
        vel = flight.velocity.copy()
        if "timestamp" not in vel.columns:
            return []

        # Determine which velocity columns are available
        vx_col = vy_col = None
        if "vx" in vel.columns and "vy" in vel.columns:
            vx_col, vy_col = "vx", "vy"
        elif "vn" in vel.columns and "ve" in vel.columns:
            vx_col, vy_col = "vn", "ve"

        if vx_col is None:
            # Try ground speed
            if "speed" not in vel.columns:
                return []
            speed_df = vel[["timestamp", "speed"]].dropna()
            hover_mask = speed_df["speed"] < LOW_VELOCITY_THRESHOLD
        else:
            vel_df = vel[["timestamp", vx_col, vy_col]].dropna()
            speed = np.sqrt(vel_df[vx_col] ** 2 + vel_df[vy_col] ** 2)
            vel_df = vel_df.copy()
            vel_df["speed"] = speed
            speed_df = vel_df[["timestamp", "speed"]]
            hover_mask = speed_df["speed"] < LOW_VELOCITY_THRESHOLD

        hover_timestamps = speed_df.loc[hover_mask, "timestamp"]
        if hover_timestamps.empty:
            return []

        # Find horizontal errors during hover
        has_actual = "lat" in merged.columns and "lon" in merged.columns
        has_sp_latlon = "lat_sp" in merged.columns and "lon_sp" in merged.columns
        has_xy = "x" in merged.columns and "y" in merged.columns
        has_xy_sp = "x_sp" in merged.columns and "y_sp" in merged.columns

        if not (has_actual and has_sp_latlon) and not (has_xy and has_xy_sp):
            return []

        # Merge position errors with hover timestamps
        if has_actual and has_sp_latlon:
            pos_df = merged[["timestamp", "lat", "lon", "lat_sp", "lon_sp"]].dropna()
            if pos_df.empty:
                return []
            pos_df = pos_df.copy()
            pos_df["horiz_err"] = [_haversine_m(r["lat"], r["lon"], r["lat_sp"], r["lon_sp"]) for _, r in pos_df.iterrows()]
        else:
            pos_df = merged[["timestamp", "x", "y", "x_sp", "y_sp"]].dropna()
            if pos_df.empty:
                return []
            pos_df = pos_df.copy()
            pos_df["horiz_err"] = np.sqrt((pos_df["x"] - pos_df["x_sp"]) ** 2 + (pos_df["y"] - pos_df["y_sp"]) ** 2)

        # Filter position errors to hover windows
        hover_pos = pos_df[pos_df["timestamp"].isin(hover_timestamps)]
        if hover_pos.empty:
            # Use nearest-match via merge_asof
            hover_df = pd.DataFrame({"timestamp": hover_timestamps})
            hover_pos = pd.merge_asof(
                hover_df.sort_values("timestamp"),
                pos_df.sort_values("timestamp"),
                on="timestamp",
                direction="nearest",
                tolerance=1.0,
            ).dropna(subset=["horiz_err"])

        if hover_pos.empty:
            return []

        max_drift = float(hover_pos["horiz_err"].max())
        mean_drift = float(hover_pos["horiz_err"].mean())

        if max_drift <= HOVER_DRIFT_M:
            return [
                Finding(
                    plugin_name=self.name,
                    title="No excessive hover drift detected",
                    severity="pass",
                    score=95,
                    description=(f"Maximum horizontal drift during hover: {max_drift:.2f}m (threshold: {HOVER_DRIFT_M}m)."),
                    evidence={
                        "max_drift_m": round(max_drift, 3),
                        "mean_drift_m": round(mean_drift, 3),
                        "threshold_m": HOVER_DRIFT_M,
                    },
                )
            ]

        severity = "critical" if max_drift > CRITICAL_MEAN_ERROR_M else "warning"
        score = 20 if severity == "critical" else 55

        ts = hover_pos["timestamp"]
        return [
            Finding(
                plugin_name=self.name,
                title=f"Hover drift detected — max {max_drift:.1f}m during low-velocity hover",
                severity=severity,
                score=score,
                description=(
                    f"Position drifted up to {max_drift:.2f}m from setpoint while hovering "
                    f"(ground speed < {LOW_VELOCITY_THRESHOLD}m/s). "
                    f"Mean drift during hover: {mean_drift:.2f}m. "
                    "Hover drift may indicate GPS/EKF issues or windy conditions."
                ),
                evidence={
                    "max_drift_m": round(max_drift, 3),
                    "mean_drift_m": round(mean_drift, 3),
                    "threshold_m": HOVER_DRIFT_M,
                    "hover_samples": len(hover_pos),
                },
                timestamp_start=float(ts.iloc[0]) if not ts.empty else None,
                timestamp_end=float(ts.iloc[-1]) if not ts.empty else None,
            )
        ]
