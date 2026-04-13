"""Damage and impact classification plugin.

Classifies damage indicators and attempts to distinguish pre-impact failure
from post-impact artifact. Helps investigators separate cause from consequence.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest

# Configurable thresholds
DEFAULT_IMPACT_VIBRATION_SPIKE_MS2 = 50.0
DEFAULT_IMPACT_ATTITUDE_DIVERGENCE_DEG = 45.0
DEFAULT_PRE_IMPACT_WINDOW_SEC = 10.0
DEFAULT_POST_IMPACT_WINDOW_SEC = 2.0


class DamageImpactClassificationPlugin(Plugin):
    """Classify damage indicators and distinguish pre-impact vs post-impact anomalies."""

    name = "damage_impact_classification"
    description = (
        "Classifies damage indicators and distinguishes pre-impact anomalies "
        "from post-impact artifact"
    )
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="damage_impact_classification",
        name="Damage and Impact Classification",
        version="1.0.0",
        author="Goose Flight",
        description=(
            "Classifies damage indicators and distinguishes pre-impact anomalies "
            "from post-impact artifact"
        ),
        category=PluginCategory.CRASH,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["attitude"],
        optional_streams=["motors", "battery", "vibration", "position"],
        output_finding_types=[
            "pre_impact_anomaly",
            "impact_signature",
            "post_impact_artifact",
            "damage_sequence_indicator",
        ],
        primary_stream="attitude",
    )

    # Class-level defaults
    DEFAULT_IMPACT_VIBRATION_SPIKE_MS2 = DEFAULT_IMPACT_VIBRATION_SPIKE_MS2
    DEFAULT_IMPACT_ATTITUDE_DIVERGENCE_DEG = DEFAULT_IMPACT_ATTITUDE_DIVERGENCE_DEG
    DEFAULT_PRE_IMPACT_WINDOW_SEC = DEFAULT_PRE_IMPACT_WINDOW_SEC
    DEFAULT_POST_IMPACT_WINDOW_SEC = DEFAULT_POST_IMPACT_WINDOW_SEC

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run damage and impact classification analysis. Returns findings."""
        findings: list[Finding] = []
        cfg = config or {}

        vib_spike_threshold = float(
            cfg.get("impact_vibration_spike_ms2", DEFAULT_IMPACT_VIBRATION_SPIKE_MS2)
        )
        att_divergence_deg = float(
            cfg.get("impact_attitude_divergence_deg", DEFAULT_IMPACT_ATTITUDE_DIVERGENCE_DEG)
        )
        pre_window_sec = float(
            cfg.get("pre_impact_window_sec", DEFAULT_PRE_IMPACT_WINDOW_SEC)
        )
        post_window_sec = float(
            cfg.get("post_impact_window_sec", DEFAULT_POST_IMPACT_WINDOW_SEC)
        )

        # Step 1: detect impact timestamp
        impact_ts = self._detect_impact(
            flight, vib_spike_threshold, att_divergence_deg
        )

        # Step 2: impact signature finding
        if impact_ts is not None:
            sig_finding = self._make_impact_signature_finding(
                flight, impact_ts, vib_spike_threshold, att_divergence_deg
            )
            if sig_finding:
                findings.append(sig_finding)

        # Step 3: scan pre-impact window for anomalies
        pre_anomalies: list[Finding] = []
        if impact_ts is not None:
            pre_anomalies = self._check_pre_impact_window(
                flight, impact_ts, pre_window_sec
            )
            findings.extend(pre_anomalies)

        # Step 4: flag post-impact artifact
        if impact_ts is not None:
            post_finding = self._make_post_impact_artifact(
                flight, impact_ts, post_window_sec
            )
            if post_finding:
                findings.append(post_finding)

        # Step 5: damage sequence indicator
        if impact_ts is not None:
            seq_finding = self._make_sequence_indicator(
                pre_anomalies, impact_ts
            )
            if seq_finding:
                findings.append(seq_finding)

        return findings

    # ------------------------------------------------------------------
    # Impact detection
    # ------------------------------------------------------------------

    def _detect_impact(
        self,
        flight: Flight,
        vib_spike_ms2: float,
        att_divergence_deg: float,
    ) -> float | None:
        """Return the estimated impact timestamp, or None if not found."""
        impact_ts_candidates: list[float] = []

        # Signal 1: vibration spike
        if not flight.vibration.empty and "timestamp" in flight.vibration.columns:
            accel_cols = [
                c for c in flight.vibration.columns if c.startswith("accel_")
            ]
            if accel_cols:
                total_accel = np.sqrt(
                    sum(flight.vibration[c] ** 2 for c in accel_cols)
                )
                spike_mask = total_accel > vib_spike_ms2
                if spike_mask.any():
                    # Use the last spike (impact is typically near end of log)
                    spike_ts = flight.vibration["timestamp"][spike_mask]
                    impact_ts_candidates.append(float(spike_ts.iloc[-1]))

        # Signal 2: attitude divergence (large rapid deviation)
        if not flight.attitude.empty and "timestamp" in flight.attitude.columns:
            att = flight.attitude
            for axis in ("roll", "pitch", "yaw"):
                if axis not in att.columns:
                    continue
                vals = np.degrees(att[axis].values)
                diffs = np.abs(np.diff(vals))
                big_jump = diffs > att_divergence_deg
                if big_jump.any():
                    idx = np.where(big_jump)[0][-1]
                    impact_ts_candidates.append(float(att["timestamp"].iloc[idx]))

        if not impact_ts_candidates:
            return None

        # Use median of candidates as best estimate
        return float(np.median(impact_ts_candidates))

    # ------------------------------------------------------------------
    # Impact signature finding
    # ------------------------------------------------------------------

    def _make_impact_signature_finding(
        self,
        flight: Flight,
        impact_ts: float,
        vib_spike_ms2: float,
        att_divergence_deg: float,
    ) -> Finding | None:
        """Emit an impact_signature finding based on how many signals are present."""
        signals_present: list[str] = []
        metrics: dict[str, Any] = {"estimated_impact_timestamp": impact_ts}

        # Check vibration spike
        if not flight.vibration.empty:
            accel_cols = [
                c for c in flight.vibration.columns if c.startswith("accel_")
            ]
            if accel_cols:
                near_impact = flight.vibration[
                    abs(flight.vibration["timestamp"] - impact_ts) <= 2.0
                ] if "timestamp" in flight.vibration.columns else flight.vibration
                if not near_impact.empty:
                    total = np.sqrt(
                        sum(near_impact[c] ** 2 for c in accel_cols)
                    )
                    if float(total.max()) > vib_spike_ms2:
                        signals_present.append("vibration_spike")
                        metrics["peak_vibration_ms2"] = round(float(total.max()), 1)

        # Check attitude divergence
        if not flight.attitude.empty and "timestamp" in flight.attitude.columns:
            for axis in ("roll", "pitch"):
                if axis not in flight.attitude.columns:
                    continue
                near = flight.attitude[
                    abs(flight.attitude["timestamp"] - impact_ts) <= 2.0
                ]
                if not near.empty:
                    diffs = np.abs(np.degrees(near[axis].diff().dropna()))
                    if float(diffs.max()) > att_divergence_deg:
                        signals_present.append("attitude_divergence")
                        metrics[f"max_{axis}_jump_deg"] = round(float(diffs.max()), 1)
                        break

        # Check velocity stop (position proxy)
        if not flight.position.empty and "timestamp" in flight.position.columns:
            vel_cols = [
                c for c in flight.position.columns if "vel" in c.lower()
            ]
            if vel_cols:
                near = flight.position[
                    flight.position["timestamp"] >= impact_ts
                ].head(5)
                if not near.empty:
                    signals_present.append("velocity_stop")

        n_signals = len(signals_present)
        if n_signals == 0:
            return None

        score = 70 if n_signals >= 3 else (50 if n_signals == 2 else 40)
        severity = "warning" if score >= 60 else "info"

        metrics["signals_present"] = signals_present
        metrics["signal_count"] = n_signals

        return Finding(
            plugin_name=self.name,
            title=f"Impact signature detected ({n_signals} signal(s))",
            severity=severity,
            score=score,
            description=(
                f"Impact signature identified at t={impact_ts:.1f}s with "
                f"{n_signals} corroborating signal(s): {', '.join(signals_present)}. "
                "This pattern is characteristic of a ground impact event."
            ),
            evidence={
                **metrics,
                "assumptions": [
                    "Impact signature inferred from correlated sensor spikes "
                    "— individual signals may have alternative explanations.",
                    "Velocity stop proxy uses position data; direct velocity sensor preferred.",
                ],
            },
            timestamp_start=impact_ts,
            timestamp_end=impact_ts + 1.0,
        )

    # ------------------------------------------------------------------
    # Pre-impact window scan
    # ------------------------------------------------------------------

    def _check_pre_impact_window(
        self,
        flight: Flight,
        impact_ts: float,
        pre_window_sec: float,
    ) -> list[Finding]:
        """Scan the pre-impact window for anomalies (motor saturation, battery sag, EKF)."""
        findings: list[Finding] = []
        window_start = impact_ts - pre_window_sec
        window_end = impact_ts

        # Motor saturation in pre-impact window
        if not flight.motors.empty and "timestamp" in flight.motors.columns:
            motor_cols = [
                c for c in flight.motors.columns if c.startswith("output_")
            ]
            if motor_cols:
                pre = flight.motors[
                    (flight.motors["timestamp"] >= window_start)
                    & (flight.motors["timestamp"] < window_end)
                ]
                if not pre.empty:
                    for col in motor_cols:
                        if float(pre[col].max()) > 0.95:
                            findings.append(Finding(
                                plugin_name=self.name,
                                title=(
                                    f"Pre-impact motor saturation: {col} "
                                    f"reached {float(pre[col].max()):.2f}"
                                ),
                                severity="warning",
                                score=35,
                                description=(
                                    f"Motor {col} output reached saturation (>0.95) "
                                    f"within {pre_window_sec}s before the detected impact at "
                                    f"t={impact_ts:.1f}s. This is a candidate pre-impact cause."
                                ),
                                evidence={
                                    "motor": col,
                                    "max_output": round(float(pre[col].max()), 3),
                                    "window_start": window_start,
                                    "impact_ts": impact_ts,
                                    "finding_type": "pre_impact_anomaly",
                                },
                                timestamp_start=window_start,
                                timestamp_end=impact_ts,
                            ))

        # Battery sag in pre-impact window
        if not flight.battery.empty and "timestamp" in flight.battery.columns:
            volt_col = next(
                (c for c in ("voltage", "voltage_v", "pack_voltage") if c in flight.battery.columns),
                None,
            )
            if volt_col:
                pre = flight.battery[
                    (flight.battery["timestamp"] >= window_start)
                    & (flight.battery["timestamp"] < window_end)
                ]
                if not pre.empty and len(pre) > 1:
                    volt_drop = float(pre[volt_col].iloc[0]) - float(pre[volt_col].iloc[-1])
                    if volt_drop > 0.5:
                        findings.append(Finding(
                            plugin_name=self.name,
                            title=f"Pre-impact battery voltage sag: {volt_drop:.2f}V drop",
                            severity="warning",
                            score=40,
                            description=(
                                f"Battery voltage dropped {volt_drop:.2f}V within "
                                f"{pre_window_sec}s before the detected impact at "
                                f"t={impact_ts:.1f}s. This may be a pre-impact cause."
                            ),
                            evidence={
                                "volt_drop_v": round(volt_drop, 3),
                                "volt_at_window_start": round(float(pre[volt_col].iloc[0]), 3),
                                "volt_at_impact": round(float(pre[volt_col].iloc[-1]), 3),
                                "window_start": window_start,
                                "impact_ts": impact_ts,
                                "finding_type": "pre_impact_anomaly",
                            },
                            timestamp_start=window_start,
                            timestamp_end=impact_ts,
                        ))

        # EKF divergence in pre-impact window
        if not flight.ekf.empty and "timestamp" in flight.ekf.columns:
            innov_cols = [
                c for c in flight.ekf.columns if "innov" in c.lower()
            ]
            if innov_cols:
                pre = flight.ekf[
                    (flight.ekf["timestamp"] >= window_start)
                    & (flight.ekf["timestamp"] < window_end)
                ]
                if not pre.empty:
                    for col in innov_cols:
                        if float(pre[col].abs().max()) > 1.0:
                            findings.append(Finding(
                                plugin_name=self.name,
                                title=(
                                    f"Pre-impact EKF divergence: {col} "
                                    f"reached {float(pre[col].abs().max()):.2f}"
                                ),
                                severity="warning",
                                score=40,
                                description=(
                                    f"EKF innovation ratio {col} exceeded 1.0 "
                                    f"within {pre_window_sec}s before detected impact. "
                                    "EKF divergence before impact may indicate estimation failure."
                                ),
                                evidence={
                                    "ekf_field": col,
                                    "max_abs_value": round(
                                        float(pre[col].abs().max()), 3
                                    ),
                                    "finding_type": "pre_impact_anomaly",
                                },
                                timestamp_start=window_start,
                                timestamp_end=impact_ts,
                            ))
                            break  # one EKF finding is enough

        return findings

    # ------------------------------------------------------------------
    # Post-impact artifact finding
    # ------------------------------------------------------------------

    def _make_post_impact_artifact(
        self,
        flight: Flight,
        impact_ts: float,
        post_window_sec: float,
    ) -> Finding | None:
        """Flag sensor readings after impact as potential post-impact artifact."""
        # Check if there is any data after impact_ts
        has_post_data = False
        if not flight.attitude.empty and "timestamp" in flight.attitude.columns:
            if float(flight.attitude["timestamp"].max()) > impact_ts + 0.1:
                has_post_data = True

        if not has_post_data:
            return None

        post_end = impact_ts + post_window_sec

        return Finding(
            plugin_name=self.name,
            title=f"Post-impact artifact window: data after t={impact_ts:.1f}s",
            severity="info",
            score=60,
            description=(
                f"Sensor readings after t={impact_ts:.1f}s (the estimated impact timestamp) "
                "may reflect vehicle damage state rather than in-flight conditions. "
                "These readings should be interpreted as post-impact artifact in forensic analysis."
            ),
            evidence={
                "impact_timestamp": impact_ts,
                "post_impact_window_end": post_end,
                "finding_type": "post_impact_artifact",
                "assumptions": [
                    "Impact timestamp is an estimate; actual impact may differ by ±1–2s.",
                    "Sensor readings after impact may be valid if vehicle remained powered.",
                ],
            },
            timestamp_start=impact_ts,
            timestamp_end=post_end,
        )

    # ------------------------------------------------------------------
    # Damage sequence indicator
    # ------------------------------------------------------------------

    def _make_sequence_indicator(
        self,
        pre_anomalies: list[Finding],
        impact_ts: float,
    ) -> Finding | None:
        """Emit a sequence indicator: failure-then-crash vs crash-then-failure."""
        if pre_anomalies:
            sequence = "failure-then-crash"
            score = 60
            description = (
                f"Pre-impact anomalies were detected before the estimated impact at "
                f"t={impact_ts:.1f}s ({len(pre_anomalies)} anomaly finding(s)). "
                "This sequence is consistent with 'failure-then-crash' — a system failure "
                "may have caused or contributed to the crash."
            )
        else:
            sequence = "crash-then-failure"
            score = 50
            description = (
                f"No pre-impact anomalies were detected before the estimated impact at "
                f"t={impact_ts:.1f}s. This sequence is more consistent with "
                "'impact-then-failure' — the crash may have been the primary event "
                "with subsequent failures resulting from impact damage."
            )

        return Finding(
            plugin_name=self.name,
            title=f"Damage sequence indicator: {sequence}",
            severity="info",
            score=score,
            description=description,
            evidence={
                "sequence_type": sequence,
                "pre_impact_anomaly_count": len(pre_anomalies),
                "impact_ts": impact_ts,
                "finding_type": "damage_sequence_indicator",
                "assumptions": [
                    "Sequence classification depends on accuracy of impact timestamp estimate.",
                    "Absence of pre-impact anomalies does not rule out a pre-impact cause "
                    "if relevant data streams are missing.",
                ],
            },
            timestamp_start=impact_ts,
        )
