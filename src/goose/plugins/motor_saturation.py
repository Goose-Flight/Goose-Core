"""Motor saturation analysis plugin — detects near-saturation, imbalance, and sustained saturation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# Thresholds
SATURATION_THRESHOLD = 0.95       # 95% output — near saturation
IMBALANCE_THRESHOLD = 0.15        # 15% max spread between motors
SUSTAINED_SATURATION_SEC = 3.0    # seconds of continuous saturation to flag


class MotorSaturationPlugin(Plugin):
    """Analyze motor output levels for saturation, balance, and sustained high-demand events."""

    name = "motor_saturation"
    description = (
        "Checks motor outputs for near-saturation events, cross-motor imbalance, "
        "and sustained saturation periods indicating loss of control authority"
    )
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="motor_saturation",
        name="Motor Saturation",
        version="1.0.0",
        author="Goose Flight",
        description="Checks motor outputs for near-saturation events, cross-motor imbalance, and sustained saturation periods",
        category=PluginCategory.PROPULSION,
        supported_vehicle_types=["multirotor", "all"],
        required_streams=["motors"],
        optional_streams=[],
        output_finding_types=["motor_saturation", "motor_imbalance", "sustained_saturation"],
    )

    DEFAULT_SATURATION_THRESHOLD = SATURATION_THRESHOLD
    DEFAULT_IMBALANCE_THRESHOLD = IMBALANCE_THRESHOLD
    DEFAULT_SUSTAINED_SATURATION_SEC = SUSTAINED_SATURATION_SEC

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run motor saturation checks. Returns findings for each check category."""
        findings: list[Finding] = []
        cfg = config or {}
        sat_thr = float(cfg.get("saturation_threshold", SATURATION_THRESHOLD))
        imb_thr = float(cfg.get("imbalance_threshold", IMBALANCE_THRESHOLD))
        sustained_sec = float(cfg.get("sustained_saturation_sec", SUSTAINED_SATURATION_SEC))

        if flight.motors is None or flight.motors.empty:
            findings.append(Finding(
                plugin_name=self.name,
                title="No motor data available",
                severity="info",
                score=50,
                description="No motor output data found in the flight log. Motor checks skipped.",
            ))
            return findings

        motors = flight.motors.copy()

        if "timestamp" not in motors.columns:
            findings.append(Finding(
                plugin_name=self.name,
                title="Motor data missing timestamp column",
                severity="info",
                score=50,
                description="Motors DataFrame present but has no 'timestamp' column.",
            ))
            return findings

        # Resolve motor output columns
        motor_cols = self._resolve_motor_cols(motors, flight.metadata.motor_count)

        if not motor_cols:
            findings.append(Finding(
                plugin_name=self.name,
                title="No motor output columns found",
                severity="info",
                score=50,
                description=(
                    f"Expected output_0..output_{flight.metadata.motor_count - 1} columns "
                    "but none were found in the motors DataFrame."
                ),
                evidence={"available_columns": list(motors.columns),
                          "motor_count": flight.metadata.motor_count},
            ))
            return findings

        findings.extend(self._check_saturation(motors, motor_cols, sat_thr))
        findings.extend(self._check_imbalance(motors, motor_cols, imb_thr))
        findings.extend(self._check_sustained_saturation(motors, motor_cols, sat_thr, sustained_sec))

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_motor_cols(motors: pd.DataFrame, motor_count: int) -> list[str]:
        """Return the list of output_N columns that exist in the DataFrame."""
        candidates = [f"output_{i}" for i in range(motor_count)]
        return [c for c in candidates if c in motors.columns]

    # ------------------------------------------------------------------
    # Near-saturation check
    # ------------------------------------------------------------------

    def _check_saturation(
        self,
        motors: pd.DataFrame,
        motor_cols: list[str],
        SATURATION_THRESHOLD: float = SATURATION_THRESHOLD,
    ) -> list[Finding]:
        """Check whether any motor output exceeds the saturation threshold."""
        per_motor: dict[str, dict[str, Any]] = {}
        any_saturated = False

        for col in motor_cols:
            series = motors[col].dropna()
            if series.empty:
                continue
            n_sat = int((series > SATURATION_THRESHOLD).sum())
            pct_sat = round(n_sat / len(series) * 100, 2)
            max_output = round(float(series.max()), 4)
            per_motor[col] = {
                "max_output": max_output,
                "samples_above_threshold": n_sat,
                "percent_above": pct_sat,
            }
            if n_sat > 0:
                any_saturated = True

        if not any_saturated:
            overall_max = max((v["max_output"] for v in per_motor.values()), default=0.0)
            return [Finding(
                plugin_name=self.name,
                title="No motor saturation detected",
                severity="pass",
                score=95,
                description=(
                    f"All motor outputs remained below the {SATURATION_THRESHOLD * 100:.0f}% "
                    f"saturation threshold. Highest output observed: {overall_max:.3f}."
                ),
                evidence={
                    "threshold": SATURATION_THRESHOLD,
                    "per_motor": per_motor,
                },
            )]

        # Which motors saturated?
        saturated_motors = [col for col, v in per_motor.items() if v["samples_above_threshold"] > 0]
        max_pct = max(v["percent_above"] for v in per_motor.values())

        severity = "critical" if max_pct > 10.0 or len(saturated_motors) > 1 else "warning"
        score = 20 if severity == "critical" else 50

        # First saturation timestamp
        ts = motors["timestamp"]
        first_sat_ts: float | None = None
        for col in saturated_motors:
            sat_idx = motors.index[motors[col] > SATURATION_THRESHOLD]
            if len(sat_idx):
                t = float(ts.loc[sat_idx[0]])
                if first_sat_ts is None or t < first_sat_ts:
                    first_sat_ts = t

        return [Finding(
            plugin_name=self.name,
            title=(
                f"Motor saturation detected — {len(saturated_motors)} motor(s) "
                f"exceeded {SATURATION_THRESHOLD * 100:.0f}%"
            ),
            severity=severity,
            score=score,
            description=(
                f"{len(saturated_motors)} motor(s) ({', '.join(saturated_motors)}) "
                f"exceeded the {SATURATION_THRESHOLD * 100:.0f}% output threshold. "
                "Saturation means the flight controller has no further authority on that motor, "
                "which reduces attitude control and can cause instability."
            ),
            evidence={
                "threshold": SATURATION_THRESHOLD,
                "saturated_motors": saturated_motors,
                "per_motor": per_motor,
            },
            timestamp_start=first_sat_ts,
        )]

    # ------------------------------------------------------------------
    # Motor imbalance check
    # ------------------------------------------------------------------

    def _check_imbalance(
        self,
        motors: pd.DataFrame,
        motor_cols: list[str],
        IMBALANCE_THRESHOLD: float = IMBALANCE_THRESHOLD,
    ) -> list[Finding]:
        """Check whether the spread between motor outputs exceeds the imbalance threshold."""
        if len(motor_cols) < 2:
            return []  # can't measure imbalance with a single motor

        # Work sample-by-sample: compute per-row max spread
        output_df = motors[motor_cols].dropna()
        if output_df.empty:
            return []

        row_max = output_df.max(axis=1)
        row_min = output_df.min(axis=1)
        spread = row_max - row_min

        max_spread = round(float(spread.max()), 4)
        mean_spread = round(float(spread.mean()), 4)
        n_imbalanced = int((spread > IMBALANCE_THRESHOLD).sum())
        pct_imbalanced = round(n_imbalanced / len(spread) * 100, 2)

        # Per-motor mean output for evidence
        per_motor_mean = {col: round(float(motors[col].mean()), 4) for col in motor_cols}

        if n_imbalanced == 0:
            return [Finding(
                plugin_name=self.name,
                title="Motor balance nominal",
                severity="pass",
                score=90,
                description=(
                    f"Max spread between motors never exceeded the {IMBALANCE_THRESHOLD * 100:.0f}% "
                    f"imbalance threshold. Peak spread: {max_spread:.3f}, mean: {mean_spread:.3f}."
                ),
                evidence={
                    "threshold": IMBALANCE_THRESHOLD,
                    "max_spread": max_spread,
                    "mean_spread": mean_spread,
                    "per_motor_mean": per_motor_mean,
                },
            )]

        ts = motors["timestamp"]
        imbalance_idx = spread[spread > IMBALANCE_THRESHOLD].index
        # Map back to original index before dropna
        orig_idx = output_df.index[imbalance_idx] if hasattr(output_df, "index") else imbalance_idx
        ts_start = float(ts.loc[orig_idx[0]]) if len(orig_idx) and orig_idx[0] in ts.index else None
        ts_end = float(ts.loc[orig_idx[-1]]) if len(orig_idx) and orig_idx[-1] in ts.index else None

        severity = "critical" if pct_imbalanced > 20.0 or max_spread > 0.35 else "warning"
        score = 20 if severity == "critical" else 50

        return [Finding(
            plugin_name=self.name,
            title=(
                f"Motor imbalance detected — spread exceeded {IMBALANCE_THRESHOLD * 100:.0f}% "
                f"for {pct_imbalanced:.1f}% of flight"
            ),
            severity=severity,
            score=score,
            description=(
                f"The spread between the highest and lowest motor output exceeded "
                f"{IMBALANCE_THRESHOLD * 100:.0f}% in {n_imbalanced} samples "
                f"({pct_imbalanced:.1f}% of flight). Peak spread: {max_spread:.3f}. "
                "Persistent imbalance suggests frame twist, prop damage, motor wear, or CG offset."
            ),
            evidence={
                "threshold": IMBALANCE_THRESHOLD,
                "max_spread": max_spread,
                "mean_spread": mean_spread,
                "samples_above_threshold": n_imbalanced,
                "percent_above": pct_imbalanced,
                "per_motor_mean": per_motor_mean,
            },
            timestamp_start=ts_start,
            timestamp_end=ts_end,
        )]

    # ------------------------------------------------------------------
    # Sustained saturation check
    # ------------------------------------------------------------------

    def _check_sustained_saturation(
        self,
        motors: pd.DataFrame,
        motor_cols: list[str],
        SATURATION_THRESHOLD: float = SATURATION_THRESHOLD,
        SUSTAINED_SATURATION_SEC: float = SUSTAINED_SATURATION_SEC,
    ) -> list[Finding]:
        """Detect windows where any motor stays above the saturation threshold for >=SUSTAINED_SATURATION_SEC."""
        sustained_events: list[dict[str, Any]] = []

        for col in motor_cols:
            df = motors[["timestamp", col]].dropna().reset_index(drop=True)
            if df.empty:
                continue

            in_sat = False
            seg_start_ts: float = 0.0
            seg_start_i: int = 0

            for i, row in df.iterrows():
                above = row[col] > SATURATION_THRESHOLD
                if above and not in_sat:
                    in_sat = True
                    seg_start_ts = float(row["timestamp"])
                    seg_start_i = int(i)
                elif not above and in_sat:
                    seg_end_ts = float(df.loc[i - 1, "timestamp"]) if i > 0 else seg_start_ts
                    duration = seg_end_ts - seg_start_ts
                    if duration >= SUSTAINED_SATURATION_SEC:
                        sustained_events.append({
                            "motor": col,
                            "start": round(seg_start_ts, 3),
                            "end": round(seg_end_ts, 3),
                            "duration_sec": round(duration, 3),
                        })
                    in_sat = False

            # Close any open segment at end of data
            if in_sat:
                seg_end_ts = float(df.iloc[-1]["timestamp"])
                duration = seg_end_ts - seg_start_ts
                if duration >= SUSTAINED_SATURATION_SEC:
                    sustained_events.append({
                        "motor": col,
                        "start": round(seg_start_ts, 3),
                        "end": round(seg_end_ts, 3),
                        "duration_sec": round(duration, 3),
                    })

        if not sustained_events:
            return [Finding(
                plugin_name=self.name,
                title="No sustained motor saturation detected",
                severity="pass",
                score=95,
                description=(
                    f"No motor remained above {SATURATION_THRESHOLD * 100:.0f}% output "
                    f"for more than {SUSTAINED_SATURATION_SEC}s continuously."
                ),
                evidence={
                    "saturation_threshold": SATURATION_THRESHOLD,
                    "sustained_duration_threshold_sec": SUSTAINED_SATURATION_SEC,
                },
            )]

        max_duration = round(max(e["duration_sec"] for e in sustained_events), 3)
        affected_motors = list({e["motor"] for e in sustained_events})

        severity = "critical" if max_duration > 10.0 or len(sustained_events) > 3 else "warning"
        score = 10 if severity == "critical" else 40

        return [Finding(
            plugin_name=self.name,
            title=(
                f"Sustained motor saturation — {len(sustained_events)} event(s), "
                f"longest {max_duration}s"
            ),
            severity=severity,
            score=score,
            description=(
                f"Detected {len(sustained_events)} event(s) where a motor stayed above "
                f"{SATURATION_THRESHOLD * 100:.0f}% output for at least {SUSTAINED_SATURATION_SEC}s. "
                f"Longest event: {max_duration}s on {affected_motors}. "
                "Sustained saturation means the flight controller has exhausted upward authority "
                "on that rotor arm — an adverse condition that can lead to loss of control."
            ),
            evidence={
                "saturation_threshold": SATURATION_THRESHOLD,
                "sustained_duration_threshold_sec": SUSTAINED_SATURATION_SEC,
                "event_count": len(sustained_events),
                "max_duration_sec": max_duration,
                "affected_motors": affected_motors,
                "events": sustained_events[:20],  # cap evidence payload
            },
            timestamp_start=sustained_events[0]["start"],
            timestamp_end=sustained_events[-1]["end"],
        )]
