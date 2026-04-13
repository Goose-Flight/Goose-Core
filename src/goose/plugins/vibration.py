"""Vibration analysis plugin — classifies vibration levels and detects anomalies."""

from __future__ import annotations

import time
import uuid
from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest

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

    def forensic_analyze_native(
        self,
        flight: Flight,
        evidence_id: str,
        run_id: str,
        config: dict[str, Any],
        parse_diagnostics: Any,
        tuning_profile: Any = None,
    ) -> tuple[list[Any], Any]:
        """Emit ForensicFinding directly with vibration window timestamps and RMS values."""
        from goose.forensics.canonical import (
            EvidenceReference,
            FindingSeverity,
            ForensicFinding,
        )
        from goose.plugins.contract import PluginDiagnostics as PDiag

        t0 = time.perf_counter()

        # Merge tuning profile thresholds if supplied
        effective_config: dict[str, Any] = dict(config or {})
        if tuning_profile is not None:
            plugin_cfg = tuning_profile.get_config_for_plugin(self.manifest.plugin_id)
            if plugin_cfg is not None and plugin_cfg.thresholds is not None:
                merged: dict[str, Any] = dict(plugin_cfg.thresholds.values)
                merged.update(effective_config)
                effective_config = merged

        # Check required streams
        missing = []
        for stream_name in self.manifest.required_streams:
            df = getattr(flight, stream_name, None)
            if df is None or (hasattr(df, "empty") and df.empty):
                missing.append(stream_name)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if missing:
            diag = PDiag(
                plugin_id=self.manifest.plugin_id,
                plugin_version=self.manifest.version,
                run_id=run_id,
                executed=False,
                skipped=True,
                skip_reason=f"Missing required streams: {', '.join(missing)}",
                missing_streams=missing,
                findings_emitted=0,
                execution_duration_ms=round(elapsed_ms, 2),
                trust_state=self.manifest.trust_state.value,
            )
            return [], diag

        cfg = effective_config
        good_thr = float(cfg.get("vibration_good_ms2", VIBRATION_GOOD))
        warn_thr = float(cfg.get("vibration_warning_ms2", VIBRATION_WARNING))
        fwd_factor = float(cfg.get("forward_flight_factor", FORWARD_FLIGHT_FACTOR))
        clip_thr = float(cfg.get("clipping_threshold_ms2", CLIPPING_THRESHOLD_MS2))

        forensic_findings: list[ForensicFinding] = []

        # Get vibration window timestamps
        vib_ts_start: float | None = None
        vib_ts_end: float | None = None
        if not flight.vibration.empty and "timestamp" in flight.vibration.columns:
            vib_ts_start = float(flight.vibration["timestamp"].iloc[0])
            vib_ts_end = float(flight.vibration["timestamp"].iloc[-1])

        if flight.vibration.empty:
            ev_ref = EvidenceReference(
                evidence_id=evidence_id,
                stream_name="vibration",
                time_range_start=None,
                time_range_end=None,
                support_summary="No accelerometer data found in flight log.",
            )
            forensic_findings.append(ForensicFinding(
                finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
                plugin_id=self.name,
                plugin_version=self.manifest.version,
                title="No vibration data available",
                description="No accelerometer data found in flight log.",
                severity=FindingSeverity.INFO,
                score=50,
                confidence=0.5,
                confidence_scope="finding_analysis",
                evidence_references=[ev_ref],
                supporting_metrics={},
                contradicting_metrics={},
                assumptions=["Vibration data absence may indicate a parser limitation or hardware mismatch"],
                run_id=run_id,
            ))
            elapsed_ms = (time.perf_counter() - t0) * 1000
            diag = PDiag(
                plugin_id=self.manifest.plugin_id,
                plugin_version=self.manifest.version,
                run_id=run_id,
                executed=True,
                skipped=False,
                findings_emitted=len(forensic_findings),
                execution_duration_ms=round(elapsed_ms, 2),
                trust_state=self.manifest.trust_state.value,
            )
            return forensic_findings, diag

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
            ev_ref = EvidenceReference(
                evidence_id=evidence_id,
                stream_name="vibration",
                time_range_start=vib_ts_start,
                time_range_end=vib_ts_end,
                support_summary="Vibration data present but no accel_x/y/z columns found.",
            )
            forensic_findings.append(ForensicFinding(
                finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
                plugin_id=self.name,
                plugin_version=self.manifest.version,
                title="No accelerometer axes found",
                description="Vibration data present but no accel_x/y/z columns found.",
                severity=FindingSeverity.INFO,
                score=50,
                confidence=0.5,
                confidence_scope="finding_analysis",
                evidence_references=[ev_ref],
                supporting_metrics={},
                contradicting_metrics={},
                assumptions=["Sensor column naming may differ from PX4 standard (accel_x/y/z)"],
                run_id=run_id,
            ))
            elapsed_ms = (time.perf_counter() - t0) * 1000
            diag = PDiag(
                plugin_id=self.manifest.plugin_id,
                plugin_version=self.manifest.version,
                run_id=run_id,
                executed=True,
                skipped=False,
                findings_emitted=len(forensic_findings),
                execution_duration_ms=round(elapsed_ms, 2),
                trust_state=self.manifest.trust_state.value,
            )
            return forensic_findings, diag

        # Remove gravity from Z axis for vibration analysis
        vib_data = flight.vibration.copy()
        if "accel_z" in vib_data.columns:
            vib_data["accel_z"] = vib_data["accel_z"] - vib_data["accel_z"].mean()

        is_forward = flight.primary_mode in ("mission", "position")

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

        if worst_classification == "good":
            severity = FindingSeverity.PASS
            score = 95
            title = "Vibration levels normal"
            desc = "All axes within PX4 recommended thresholds."
            confidence = 0.95
        elif worst_classification == "warning":
            severity = FindingSeverity.WARNING
            score = 60
            title = "Elevated vibration detected"
            desc = "One or more axes exceed the 'good' threshold. Check prop balance and mount isolation."
            confidence = 0.6
        else:
            severity = FindingSeverity.CRITICAL
            score = 20
            title = "Excessive vibration detected"
            desc = (
                "One or more axes exceed PX4 safety thresholds. "
                "Flight controller performance may be degraded. "
                "Inspect props, motors, frame, and vibration damping."
            )
            confidence = 0.8

        assumptions: list[str] = [
            "Vibration thresholds are based on PX4 default IMU recommendations; "
            "custom-mounted or non-standard flight controllers may have different baselines",
        ]
        if is_forward:
            assumptions.append(
                f"Forward-flight scaling factor {fwd_factor:.1f}x applied to thresholds "
                "— vehicle was in mission/position mode"
            )

        supporting_metrics: dict[str, Any] = {
            "axes": axis_results,
            "flight_mode": flight.primary_mode,
            "forward_flight_scaling": is_forward,
            "good_threshold_ms2": good_thr,
            "warning_threshold_ms2": warn_thr,
        }

        ev_ref = EvidenceReference(
            evidence_id=evidence_id,
            stream_name="vibration",
            time_range_start=vib_ts_start,
            time_range_end=vib_ts_end,
            support_summary=f"Vibration analysis over full flight window ({vib_ts_start:.1f}s–{vib_ts_end:.1f}s)."
            if vib_ts_start is not None and vib_ts_end is not None else desc[:200],
        )

        forensic_findings.append(ForensicFinding(
            finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
            plugin_id=self.name,
            plugin_version=self.manifest.version,
            title=title,
            description=desc,
            severity=severity,
            score=score,
            confidence=confidence,
            confidence_scope="finding_analysis",
            start_time=vib_ts_start,
            end_time=vib_ts_end,
            evidence_references=[ev_ref],
            supporting_metrics=supporting_metrics,
            contradicting_metrics={},
            assumptions=assumptions,
            run_id=run_id,
        ))

        # Clipping detection
        clipping_finding = self._check_clipping(flight, available, clip_thr)
        if clipping_finding:
            clip_ev_ref = EvidenceReference(
                evidence_id=evidence_id,
                stream_name="vibration",
                time_range_start=vib_ts_start,
                time_range_end=vib_ts_end,
                support_summary=clipping_finding.description[:200] if clipping_finding.description else "",
            )
            clip_supporting: dict[str, Any] = {}
            for k, v in (clipping_finding.evidence or {}).items():
                try:
                    import json as _json
                    _json.dumps(v)
                    clip_supporting[k] = v
                except (TypeError, ValueError):
                    clip_supporting[k] = str(v)
            forensic_findings.append(ForensicFinding(
                finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
                plugin_id=self.name,
                plugin_version=self.manifest.version,
                title=clipping_finding.title,
                description=clipping_finding.description,
                severity=FindingSeverity(clipping_finding.severity)
                if clipping_finding.severity in FindingSeverity._value2member_map_
                else FindingSeverity.WARNING,
                score=int(clipping_finding.score),
                confidence=round(int(clipping_finding.score) / 100.0, 2),
                confidence_scope="finding_analysis",
                start_time=vib_ts_start,
                end_time=vib_ts_end,
                evidence_references=[clip_ev_ref],
                supporting_metrics=clip_supporting,
                contradicting_metrics={},
                assumptions=["Clipping threshold set at ~15.9g (156 m/s²) — standard PX4 IMU saturation point"],
                run_id=run_id,
            ))

        # Degradation detection
        degradation_finding = self._check_degradation(flight, vib_data, available)
        if degradation_finding:
            deg_ev_ref = EvidenceReference(
                evidence_id=evidence_id,
                stream_name="vibration",
                time_range_start=vib_ts_start,
                time_range_end=vib_ts_end,
                support_summary=degradation_finding.description[:200] if degradation_finding.description else "",
            )
            deg_supporting: dict[str, Any] = {}
            for k, v in (degradation_finding.evidence or {}).items():
                try:
                    import json as _json
                    _json.dumps(v)
                    deg_supporting[k] = v
                except (TypeError, ValueError):
                    deg_supporting[k] = str(v)
            forensic_findings.append(ForensicFinding(
                finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
                plugin_id=self.name,
                plugin_version=self.manifest.version,
                title=degradation_finding.title,
                description=degradation_finding.description,
                severity=FindingSeverity(degradation_finding.severity)
                if degradation_finding.severity in FindingSeverity._value2member_map_
                else FindingSeverity.WARNING,
                score=int(degradation_finding.score),
                confidence=round(int(degradation_finding.score) / 100.0, 2),
                confidence_scope="finding_analysis",
                start_time=vib_ts_start,
                end_time=vib_ts_end,
                evidence_references=[deg_ev_ref],
                supporting_metrics=deg_supporting,
                contradicting_metrics={},
                assumptions=[
                    "Vibration increase is measured across first vs last flight quarter; "
                    "short flights (<100 samples) are excluded from this check"
                ],
                run_id=run_id,
            ))

        elapsed_ms = (time.perf_counter() - t0) * 1000
        diag = PDiag(
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.version,
            run_id=run_id,
            executed=True,
            skipped=False,
            findings_emitted=len(forensic_findings),
            execution_duration_ms=round(elapsed_ms, 2),
            trust_state=self.manifest.trust_state.value,
        )
        return forensic_findings, diag

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
