"""Vibration analysis plugin — classifies vibration levels and detects anomalies."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightPhase
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# PX4 vibration thresholds in m/s^2
VIBRATION_GOOD = 15.0
VIBRATION_WARNING = 30.0
# Above VIBRATION_WARNING = bad

# Hover vs forward-flight scaling (forward flight has higher baseline vibration)
FORWARD_FLIGHT_FACTOR = 1.3

# Clipping threshold — sensor saturation near +-16g for typical IMUs
CLIPPING_THRESHOLD_MS2 = 156.0  # ~15.9g


def _rms(series: pd.Series) -> float:
    """Compute root-mean-square of a series."""
    return float(np.sqrt((series**2).mean()))


def _classify_vibration(
    rms_val: float,
    is_forward_flight: bool = False,
    good_threshold: float = VIBRATION_GOOD,
    warning_threshold: float = VIBRATION_WARNING,
    forward_factor: float = FORWARD_FLIGHT_FACTOR,
) -> str:
    """Classify vibration level as good/warning/bad."""
    threshold_good = good_threshold
    threshold_warn = warning_threshold
    if is_forward_flight:
        threshold_good *= forward_factor
        threshold_warn *= forward_factor
    if rms_val < threshold_good:
        return "good"
    elif rms_val < threshold_warn:
        return "warning"
    return "bad"


class VibrationPlugin(Plugin):
    """Analyze vibration levels from accelerometer data."""

    name = "vibration"
    description = "Computes RMS/peak vibration per axis, checks PX4 thresholds, detects clipping and degradation"
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="vibration",
        name="Vibration Analysis",
        version="1.0.0",
        author="Goose Flight",
        description="Computes RMS/peak vibration per axis, checks PX4 thresholds, detects clipping and degradation",
        category=PluginCategory.HEALTH,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["vibration"],
        optional_streams=[],
        output_finding_types=["vibration_level", "sensor_clipping", "vibration_degradation"],
        primary_stream="vibration",
    )

    DEFAULT_VIBRATION_GOOD_MS2 = VIBRATION_GOOD
    DEFAULT_VIBRATION_WARNING_MS2 = VIBRATION_WARNING
    DEFAULT_FORWARD_FLIGHT_FACTOR = FORWARD_FLIGHT_FACTOR
    DEFAULT_CLIPPING_THRESHOLD_MS2 = CLIPPING_THRESHOLD_MS2

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run vibration analysis. Returns findings for each axis and anomalies."""
        findings: list[Finding] = []
        cfg = config or {}
        good_thr = float(cfg.get("vibration_good_ms2", VIBRATION_GOOD))
        warn_thr = float(cfg.get("vibration_warning_ms2", VIBRATION_WARNING))
        fwd_factor = float(cfg.get("forward_flight_factor", FORWARD_FLIGHT_FACTOR))
        clip_thr = float(cfg.get("clipping_threshold_ms2", CLIPPING_THRESHOLD_MS2))

        if flight.vibration.empty:
            findings.append(Finding(
                plugin_name=self.name,
                title="No vibration data available",
                severity="info",
                score=50,
                description="No accelerometer data found in flight log.",
            ))
            return findings

        accel_cols = {
            "x": "accel_x",
            "y": "accel_y",
            "z": "accel_z",
        }
        available = {
            axis: col
            for axis, col in accel_cols.items()
            if col in flight.vibration.columns
        }
        if not available:
            findings.append(Finding(
                plugin_name=self.name,
                title="No accelerometer axes found",
                severity="info",
                score=50,
                description="Vibration data present but no accel_x/y/z columns found.",
            ))
            return findings

        # Remove gravity from Z axis for vibration analysis
        vib_data = flight.vibration.copy()
        if "accel_z" in vib_data.columns:
            vib_data["accel_z"] = vib_data["accel_z"] - vib_data["accel_z"].mean()

        # Detect flight phases for phase-aware analysis
        is_forward = flight.primary_mode in ("mission", "position")

        # Per-axis RMS and peak
        axis_results: dict[str, dict[str, Any]] = {}
        worst_classification = "good"

        for axis, col in available.items():
            if col == "accel_z":
                series = vib_data[col]
            else:
                series = flight.vibration[col]

            rms_val = _rms(series)
            peak_val = float(series.abs().max())
            classification = _classify_vibration(
                rms_val,
                is_forward_flight=is_forward,
                good_threshold=good_thr,
                warning_threshold=warn_thr,
                forward_factor=fwd_factor,
            )

            axis_results[axis] = {
                "rms_ms2": round(rms_val, 2),
                "peak_ms2": round(peak_val, 2),
                "classification": classification,
            }

            if classification == "bad":
                worst_classification = "bad"
            elif classification == "warning" and worst_classification != "bad":
                worst_classification = "warning"

        # Overall vibration finding
        if worst_classification == "good":
            severity = "pass"
            score = 95
            title = "Vibration levels normal"
            desc = "All axes within PX4 recommended thresholds."
        elif worst_classification == "warning":
            severity = "warning"
            score = 60
            title = "Elevated vibration detected"
            desc = "One or more axes exceed the 'good' threshold. Check prop balance and mount isolation."
        else:
            severity = "critical"
            score = 20
            title = "Excessive vibration detected"
            desc = (
                "One or more axes exceed PX4 safety thresholds. "
                "Flight controller performance may be degraded. "
                "Inspect props, motors, frame, and vibration damping."
            )

        findings.append(Finding(
            plugin_name=self.name,
            title=title,
            severity=severity,
            score=score,
            description=desc,
            evidence={
                "axes": axis_results,
                "flight_mode": flight.primary_mode,
                "forward_flight_scaling": is_forward,
            },
        ))

        # Clipping detection
        clipping_finding = self._check_clipping(flight, available, clip_thr)
        if clipping_finding:
            findings.append(clipping_finding)

        # Degradation over flight duration
        degradation_finding = self._check_degradation(flight, vib_data, available)
        if degradation_finding:
            findings.append(degradation_finding)

        return findings

    def _check_clipping(
        self,
        flight: Flight,
        available: dict[str, str],
        clipping_threshold_ms2: float = CLIPPING_THRESHOLD_MS2,
    ) -> Finding | None:
        """Detect sensor saturation (clipping) on any axis."""
        clip_axes: list[str] = []
        clip_counts: dict[str, int] = {}

        for axis, col in available.items():
            series = flight.vibration[col]
            clipped = (series.abs() > clipping_threshold_ms2).sum()
            if clipped > 0:
                clip_axes.append(axis)
                clip_counts[axis] = int(clipped)

        if not clip_axes:
            return None

        total_samples = len(flight.vibration)
        total_clipped = sum(clip_counts.values())
        pct = total_clipped / total_samples * 100

        return Finding(
            plugin_name=self.name,
            title=f"Sensor clipping detected on {', '.join(clip_axes)} axis",
            severity="critical" if pct > 1.0 else "warning",
            score=10 if pct > 1.0 else 40,
            description=(
                f"Accelerometer saturation detected on {clip_axes} axes. "
                f"{total_clipped} samples clipped ({pct:.2f}% of data). "
                "IMU data unreliable during clipping events."
            ),
            evidence={
                "clipped_axes": clip_axes,
                "clip_counts": clip_counts,
                "total_samples": total_samples,
                "clip_percentage": round(pct, 3),
            },
        )

    def _check_degradation(
        self,
        flight: Flight,
        vib_data: pd.DataFrame,
        available: dict[str, str],
    ) -> Finding | None:
        """Check if vibration increased over flight duration (bearing degradation)."""
        if len(vib_data) < 100:
            return None

        timestamps = vib_data["timestamp"]
        duration = timestamps.iloc[-1] - timestamps.iloc[0]
        if duration < 30.0:  # need at least 30s of data
            return None

        # Split into first and last quarter
        quarter = len(vib_data) // 4
        first_q = vib_data.iloc[:quarter]
        last_q = vib_data.iloc[-quarter:]

        degradation_axes: list[str] = []
        ratios: dict[str, float] = {}

        for axis, col in available.items():
            if col == "accel_z":
                rms_first = _rms(first_q[col])
                rms_last = _rms(last_q[col])
            else:
                rms_first = _rms(first_q[col] if col in first_q.columns else pd.Series(dtype=float))
                rms_last = _rms(last_q[col] if col in last_q.columns else pd.Series(dtype=float))

            if rms_first > 0.1:  # avoid division by near-zero
                ratio = rms_last / rms_first
                ratios[axis] = round(ratio, 2)
                if ratio > 1.5:  # 50% increase = concerning
                    degradation_axes.append(axis)

        if not degradation_axes:
            return None

        return Finding(
            plugin_name=self.name,
            title=f"Vibration increase detected on {', '.join(degradation_axes)} axis",
            severity="warning",
            score=45,
            description=(
                f"Vibration RMS increased significantly over the flight on {degradation_axes} axes. "
                f"Ratios (last/first quarter): {ratios}. "
                "This may indicate bearing wear, prop damage, or loosening hardware."
            ),
            evidence={
                "degradation_axes": degradation_axes,
                "rms_ratios": ratios,
                "flight_duration_sec": round(duration, 1),
            },
        )
