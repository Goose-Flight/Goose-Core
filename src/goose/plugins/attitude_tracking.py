"""Attitude tracking plugin — compares attitude vs setpoint to quantify tracking error."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest

# Tracking error thresholds in degrees
TRACKING_ERROR_WARNING_DEG = 5.0
TRACKING_ERROR_CRITICAL_DEG = 15.0

# Oscillation detection: minimum number of sign changes per second to flag
OSCILLATION_SIGN_CHANGES_PER_SEC = 2.0

# Merge tolerance for timestamp alignment (seconds)
MERGE_TOLERANCE_SEC = 0.05


def _rms_deg(series: pd.Series) -> float:
    """Compute RMS of a series (already in degrees)."""
    return float(np.sqrt((series**2).mean()))


def _count_sign_changes(series: pd.Series) -> int:
    """Count the number of sign changes in a series."""
    if len(series) < 2:
        return 0
    signs = np.sign(series.values)
    # Ignore zeros
    nonzero = signs[signs != 0]
    if len(nonzero) < 2:
        return 0
    return int(np.sum(np.diff(nonzero) != 0))


class AttitudeTrackingPlugin(Plugin):
    """Analyze attitude tracking error by comparing attitude vs attitude setpoint."""

    name = "attitude_tracking"
    description = "Attitude tracking error vs setpoint analysis"
    version = "1.0.0"
    min_mode = "stabilized"

    manifest = PluginManifest(
        plugin_id="attitude_tracking",
        name="Attitude Tracking",
        version="1.0.0",
        author="Goose Flight",
        description="Compares attitude vs setpoint to quantify tracking error and detect oscillations",
        category=PluginCategory.FLIGHT_DYNAMICS,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["attitude", "attitude_setpoint"],
        optional_streams=[],
        output_finding_types=["tracking_error", "attitude_oscillation"],
        primary_stream="attitude",
    )

    DEFAULT_TRACKING_ERROR_WARNING_DEG = TRACKING_ERROR_WARNING_DEG
    DEFAULT_TRACKING_ERROR_CRITICAL_DEG = TRACKING_ERROR_CRITICAL_DEG
    DEFAULT_OSCILLATION_SIGN_CHANGES_PER_SEC = OSCILLATION_SIGN_CHANGES_PER_SEC
    DEFAULT_MERGE_TOLERANCE_SEC = MERGE_TOLERANCE_SEC

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run attitude tracking analysis. Returns findings per axis and for oscillation."""
        findings: list[Finding] = []
        cfg = config or {}
        warn_deg = float(cfg.get("tracking_error_warning_deg", TRACKING_ERROR_WARNING_DEG))
        crit_deg = float(cfg.get("tracking_error_critical_deg", TRACKING_ERROR_CRITICAL_DEG))
        osc_per_sec = float(cfg.get("oscillation_sign_changes_per_sec", OSCILLATION_SIGN_CHANGES_PER_SEC))
        merge_tol = float(cfg.get("merge_tolerance_sec", MERGE_TOLERANCE_SEC))

        # Need both attitude and setpoint data
        if flight.attitude is None or flight.attitude.empty:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="No attitude data available",
                    severity="info",
                    score=50,
                    description="No attitude data found in the flight log. Tracking error analysis skipped.",
                )
            )
            return findings

        if not flight.has_attitude_setpoints or flight.attitude_setpoint.empty:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="No attitude setpoint data available",
                    severity="info",
                    score=50,
                    description=("Attitude setpoint data is not available. Tracking error analysis requires both attitude and attitude_setpoint streams."),
                )
            )
            return findings

        att = flight.attitude.copy()
        sp = flight.attitude_setpoint.copy()

        if "timestamp" not in att.columns or "timestamp" not in sp.columns:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="Attitude data missing timestamp column",
                    severity="info",
                    score=50,
                    description="Cannot merge attitude and setpoint data without 'timestamp' column.",
                )
            )
            return findings

        merged = self._merge_on_timestamp(att, sp, merge_tol)
        if merged.empty:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="Could not merge attitude and setpoint data",
                    severity="info",
                    score=50,
                    description="No overlapping timestamps found between attitude and attitude_setpoint streams.",
                )
            )
            return findings

        findings.extend(self._check_tracking_error(merged, flight, warn_deg, crit_deg))
        findings.extend(self._check_oscillation(merged, flight, osc_per_sec))

        return findings

    # ------------------------------------------------------------------
    # Timestamp merge
    # ------------------------------------------------------------------

    def _merge_on_timestamp(
        self,
        att: pd.DataFrame,
        sp: pd.DataFrame,
        merge_tolerance_sec: float = MERGE_TOLERANCE_SEC,
    ) -> pd.DataFrame:
        """Merge attitude and setpoint DataFrames by nearest timestamp."""
        att_sorted = att.sort_values("timestamp").reset_index(drop=True)
        sp_sorted = sp.sort_values("timestamp").reset_index(drop=True)

        # Rename setpoint columns to avoid collisions (suffix _sp)
        sp_renamed = sp_sorted.rename(columns={c: f"{c}_sp" for c in sp_sorted.columns if c != "timestamp"})

        # Use merge_asof for nearest-timestamp join
        merged = pd.merge_asof(
            att_sorted,
            sp_renamed,
            on="timestamp",
            tolerance=merge_tolerance_sec,
            direction="nearest",
        )
        return merged.dropna(subset=["timestamp"])

    # ------------------------------------------------------------------
    # RMS tracking error per axis
    # ------------------------------------------------------------------

    def _check_tracking_error(
        self,
        merged: pd.DataFrame,
        flight: Flight,
        TRACKING_ERROR_WARNING_DEG: float = TRACKING_ERROR_WARNING_DEG,
        TRACKING_ERROR_CRITICAL_DEG: float = TRACKING_ERROR_CRITICAL_DEG,
    ) -> list[Finding]:
        """Compute RMS tracking error for roll/pitch/yaw in degrees."""
        axis_map = {
            "roll": ("roll", "roll_sp"),
            "pitch": ("pitch", "pitch_sp"),
            "yaw": ("yaw", "yaw_sp"),
        }

        axis_results: dict[str, dict[str, Any]] = {}
        worst = "pass"
        worst_axis = ""
        worst_rms = 0.0

        for axis, (att_col, sp_col) in axis_map.items():
            if att_col not in merged.columns or sp_col not in merged.columns:
                continue

            # Convert radians to degrees
            att_deg = np.degrees(merged[att_col].dropna())
            sp_deg = np.degrees(merged[sp_col].dropna())

            # Align indices
            common_idx = att_deg.index.intersection(sp_deg.index)
            if len(common_idx) < 2:
                continue

            error_deg = att_deg.loc[common_idx] - sp_deg.loc[common_idx]

            rms = round(_rms_deg(error_deg), 3)
            max_err = round(float(error_deg.abs().max()), 3)
            mean_err = round(float(error_deg.abs().mean()), 3)

            if rms >= TRACKING_ERROR_CRITICAL_DEG:
                level = "critical"
                worst = "critical"
                if rms > worst_rms:
                    worst_rms = rms
                    worst_axis = axis
            elif rms >= TRACKING_ERROR_WARNING_DEG:
                level = "warning"
                if worst != "critical":
                    worst = "warning"
                    if rms > worst_rms:
                        worst_rms = rms
                        worst_axis = axis
            else:
                level = "pass"

            axis_results[axis] = {
                "rms_error_deg": rms,
                "max_error_deg": max_err,
                "mean_abs_error_deg": mean_err,
                "level": level,
                "samples": int(len(common_idx)),
            }

        if not axis_results:
            return [
                Finding(
                    plugin_name=self.name,
                    title="No matching attitude axes found for tracking analysis",
                    severity="info",
                    score=50,
                    description=("Could not find matching roll/pitch/yaw columns in both attitude and setpoint data."),
                )
            ]

        if worst == "pass":
            return [
                Finding(
                    plugin_name=self.name,
                    title="Attitude tracking error within limits",
                    severity="pass",
                    score=95,
                    description=(f"All axes showed RMS tracking error below the warning threshold of {TRACKING_ERROR_WARNING_DEG} degrees."),
                    evidence={
                        "axes": axis_results,
                        "warning_threshold_deg": TRACKING_ERROR_WARNING_DEG,
                        "critical_threshold_deg": TRACKING_ERROR_CRITICAL_DEG,
                    },
                )
            ]

        if worst == "critical":
            severity = "critical"
            score = 15
            title = f"Critical attitude tracking error — {worst_axis} RMS {worst_rms:.1f}° (threshold {TRACKING_ERROR_CRITICAL_DEG}°)"
            desc = (
                f"Attitude tracking error is critically high on the {worst_axis} axis "
                f"(RMS {worst_rms:.1f}°). "
                "This may indicate a control loop tuning problem, actuator failure, or structural issue."
            )
        else:
            severity = "warning"
            score = 50
            title = f"Elevated attitude tracking error — {worst_axis} RMS {worst_rms:.1f}° (threshold {TRACKING_ERROR_WARNING_DEG}°)"
            desc = (
                f"Attitude tracking error exceeds the warning threshold on the {worst_axis} axis "
                f"(RMS {worst_rms:.1f}°). "
                "Check PID tuning and mechanical balance."
            )

        return [
            Finding(
                plugin_name=self.name,
                title=title,
                severity=severity,
                score=score,
                description=desc,
                evidence={
                    "axes": axis_results,
                    "warning_threshold_deg": TRACKING_ERROR_WARNING_DEG,
                    "critical_threshold_deg": TRACKING_ERROR_CRITICAL_DEG,
                },
            )
        ]

    # ------------------------------------------------------------------
    # Oscillation detection
    # ------------------------------------------------------------------

    def _check_oscillation(
        self,
        merged: pd.DataFrame,
        flight: Flight,
        OSCILLATION_SIGN_CHANGES_PER_SEC: float = OSCILLATION_SIGN_CHANGES_PER_SEC,
    ) -> list[Finding]:
        """Detect rapid oscillation in attitude tracking error."""
        axis_map = {
            "roll": ("roll", "roll_sp"),
            "pitch": ("pitch", "pitch_sp"),
            "yaw": ("yaw", "yaw_sp"),
        }

        oscillating: list[str] = []
        osc_evidence: dict[str, dict[str, Any]] = {}

        ts = merged["timestamp"]
        if len(ts) < 4:
            return []

        duration = float(ts.iloc[-1] - ts.iloc[0])
        if duration < 1.0:
            return []

        for axis, (att_col, sp_col) in axis_map.items():
            if att_col not in merged.columns or sp_col not in merged.columns:
                continue

            att_deg = np.degrees(merged[att_col].dropna())
            sp_deg = np.degrees(merged[sp_col].dropna())
            common_idx = att_deg.index.intersection(sp_deg.index)
            if len(common_idx) < 4:
                continue

            error = att_deg.loc[common_idx] - sp_deg.loc[common_idx]
            sign_changes = _count_sign_changes(error)
            changes_per_sec = sign_changes / duration

            if changes_per_sec >= OSCILLATION_SIGN_CHANGES_PER_SEC:
                oscillating.append(axis)
                osc_evidence[axis] = {
                    "sign_changes": sign_changes,
                    "changes_per_sec": round(changes_per_sec, 2),
                }

        if not oscillating:
            return []

        return [
            Finding(
                plugin_name=self.name,
                title=f"Attitude oscillation detected on {', '.join(oscillating)} axis/axes",
                severity="warning",
                score=40,
                description=(
                    f"Rapid sign changes in tracking error detected on {oscillating} axes, "
                    f"suggesting oscillatory behavior. "
                    "This typically indicates PID gains are too aggressive. "
                    "Reduce P/D gains on the affected axes."
                ),
                evidence={
                    "oscillating_axes": oscillating,
                    "oscillation_threshold_per_sec": OSCILLATION_SIGN_CHANGES_PER_SEC,
                    "flight_duration_sec": round(duration, 1),
                    "axes": osc_evidence,
                },
            )
        ]
