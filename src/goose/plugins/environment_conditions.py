"""Environment conditions assessment plugin.

Assesses environmental indicators (GPS multipath, wind loading, vibration
environment, RF interference) that may have contributed to flight anomalies.
This is a correlating analyzer — it does not establish causation.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest

# Configurable thresholds
DEFAULT_HIGH_HDOP_THRESHOLD = 2.0
DEFAULT_MIN_SATELLITES_FOR_MULTIPATH = 8
DEFAULT_VIBRATION_ENV_THRESHOLD = 25.0  # m/s² RMS
DEFAULT_ATTITUDE_BIAS_THRESHOLD = 5.0   # degrees sustained bias
DEFAULT_SAT_DROP_THRESHOLD = 4          # satellites lost in window
DEFAULT_SAT_DROP_WINDOW_SEC = 5.0


class EnvironmentConditionsPlugin(Plugin):
    """Assess environmental factors that may have contributed to flight anomalies."""

    name = "environment_conditions"
    description = (
        "Assesses environmental indicators (GPS multipath, wind, interference) "
        "that may have contributed to flight anomalies"
    )
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="environment_conditions",
        name="Environment Conditions Assessment",
        version="1.0.0",
        author="Goose Flight",
        description=(
            "Assesses environmental indicators (GPS multipath, wind, interference) "
            "that may have contributed to flight anomalies"
        ),
        category=PluginCategory.HEALTH,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["gps"],
        optional_streams=["vibration", "attitude", "ekf"],
        output_finding_types=[
            "gps_multipath_indicator",
            "high_vibration_environment",
            "wind_loading_indicator",
            "interference_indicator",
        ],
        primary_stream="gps",
    )

    # Class-level defaults (for tuning profile parity)
    DEFAULT_HIGH_HDOP_THRESHOLD = DEFAULT_HIGH_HDOP_THRESHOLD
    DEFAULT_MIN_SATELLITES_FOR_MULTIPATH = DEFAULT_MIN_SATELLITES_FOR_MULTIPATH
    DEFAULT_VIBRATION_ENV_THRESHOLD = DEFAULT_VIBRATION_ENV_THRESHOLD
    DEFAULT_ATTITUDE_BIAS_THRESHOLD = DEFAULT_ATTITUDE_BIAS_THRESHOLD
    DEFAULT_SAT_DROP_THRESHOLD = DEFAULT_SAT_DROP_THRESHOLD
    DEFAULT_SAT_DROP_WINDOW_SEC = DEFAULT_SAT_DROP_WINDOW_SEC

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run environmental conditions assessment. Returns findings."""
        findings: list[Finding] = []
        cfg = config or {}

        high_hdop = float(cfg.get("high_hdop_threshold", DEFAULT_HIGH_HDOP_THRESHOLD))
        min_sats_multipath = int(
            cfg.get("min_satellites_for_multipath", DEFAULT_MIN_SATELLITES_FOR_MULTIPATH)
        )
        vib_env_threshold = float(
            cfg.get("vibration_env_threshold", DEFAULT_VIBRATION_ENV_THRESHOLD)
        )
        attitude_bias_threshold = float(
            cfg.get("attitude_bias_threshold", DEFAULT_ATTITUDE_BIAS_THRESHOLD)
        )
        sat_drop_threshold = int(
            cfg.get("sat_drop_threshold", DEFAULT_SAT_DROP_THRESHOLD)
        )
        sat_drop_window_sec = float(
            cfg.get("sat_drop_window_sec", DEFAULT_SAT_DROP_WINDOW_SEC)
        )

        # Check GPS multipath
        multipath = self._check_gps_multipath(
            flight, high_hdop, min_sats_multipath
        )
        if multipath:
            findings.append(multipath)

        # Check GPS interference (satellite count drop)
        interference = self._check_gps_interference(
            flight, sat_drop_threshold, sat_drop_window_sec
        )
        if interference:
            findings.append(interference)

        # Check high vibration environment
        vib_env = self._check_vibration_environment(flight, vib_env_threshold)
        if vib_env:
            findings.append(vib_env)

        # Check wind loading indicator
        wind = self._check_wind_loading(flight, attitude_bias_threshold)
        if wind:
            findings.append(wind)

        return findings

    # ------------------------------------------------------------------
    # GPS multipath indicator
    # ------------------------------------------------------------------

    def _check_gps_multipath(
        self,
        flight: Flight,
        high_hdop: float,
        min_sats: int,
    ) -> Finding | None:
        """High DOP with adequate satellites suggests multipath rather than poor sky view."""
        gps = flight.gps
        if gps.empty:
            return None

        hdop_col = next(
            (c for c in ("hdop", "h_dop", "eph") if c in gps.columns), None
        )
        sat_col = next(
            (c for c in ("satellites_used", "num_sats", "sats") if c in gps.columns), None
        )

        if hdop_col is None or sat_col is None:
            return None

        hdop = gps[hdop_col].dropna()
        sats = gps[sat_col].dropna()

        if hdop.empty or sats.empty:
            return None

        # Rows where HDOP is high AND satellites are adequate
        merged = pd.concat([hdop.rename("hdop"), sats.rename("sats")], axis=1).dropna()
        multipath_mask = (merged["hdop"] > high_hdop) & (merged["sats"] >= min_sats)

        if not multipath_mask.any():
            return None

        pct = round(float(multipath_mask.mean()) * 100, 1)
        mean_hdop = round(float(merged.loc[multipath_mask, "hdop"].mean()), 2)
        mean_sats = round(float(merged.loc[multipath_mask, "sats"].mean()), 1)

        # Only flag if sustained (>5% of flight)
        if pct < 5.0:
            return None

        ts_col = gps["timestamp"] if "timestamp" in gps.columns else None

        return Finding(
            plugin_name=self.name,
            title=f"GPS multipath indicator: HDOP {mean_hdop:.1f} with {mean_sats:.0f} satellites",
            severity="info",
            score=50,
            description=(
                f"High DOP ({mean_hdop:.1f}) observed alongside adequate satellite count "
                f"({mean_sats:.0f} avg) for {pct}% of flight. "
                "This pattern is consistent with GPS multipath (signal reflection). "
                "Direct confirmation requires RF analysis."
            ),
            evidence={
                "mean_hdop_during_event": mean_hdop,
                "mean_satellites_during_event": mean_sats,
                "pct_flight_affected": pct,
                "hdop_threshold": high_hdop,
                "min_satellites_threshold": min_sats,
                "assumptions": [
                    "High DOP with adequate satellites is consistent with multipath "
                    "— direct confirmation requires RF analysis.",
                    "Low satellite count (not multipath) is an alternative explanation "
                    "if satellite visibility was momentarily obstructed.",
                ],
            },
            timestamp_start=float(ts_col.iloc[0]) if ts_col is not None else None,
            timestamp_end=float(ts_col.iloc[-1]) if ts_col is not None else None,
        )

    # ------------------------------------------------------------------
    # GPS interference indicator
    # ------------------------------------------------------------------

    def _check_gps_interference(
        self,
        flight: Flight,
        sat_drop_threshold: int,
        sat_drop_window_sec: float,
    ) -> Finding | None:
        """Sudden satellite count drop without position change suggests interference."""
        gps = flight.gps
        if gps.empty:
            return None

        sat_col = next(
            (c for c in ("satellites_used", "num_sats", "sats") if c in gps.columns), None
        )
        if sat_col is None or "timestamp" not in gps.columns:
            return None

        df = gps[["timestamp", sat_col]].dropna().sort_values("timestamp")
        if len(df) < 10:
            return None

        sats = df[sat_col].values
        ts = df["timestamp"].values

        # Scan for windows where satellite count drops by >= threshold in <= window_sec
        events: list[dict[str, Any]] = []
        for i in range(1, len(ts)):
            window_mask = (ts >= ts[i] - sat_drop_window_sec) & (ts < ts[i])
            if not window_mask.any():
                continue
            window_sats = sats[window_mask]
            if len(window_sats) == 0:
                continue
            sat_drop = float(window_sats.max()) - float(sats[i])
            if sat_drop >= sat_drop_threshold:
                events.append({
                    "timestamp": float(ts[i]),
                    "sats_before": float(window_sats.max()),
                    "sats_after": float(sats[i]),
                    "drop": float(sat_drop),
                })

        if not events:
            return None

        worst = max(events, key=lambda e: e["drop"])

        return Finding(
            plugin_name=self.name,
            title=f"GPS interference indicator: {len(events)} satellite drop event(s)",
            severity="info",
            score=55,
            description=(
                f"Detected {len(events)} event(s) where satellite count dropped by "
                f">= {sat_drop_threshold} in < {sat_drop_window_sec}s. "
                "Sudden satellite drops (without corresponding position change) are "
                "consistent with RF interference rather than sky obstruction."
            ),
            evidence={
                "event_count": len(events),
                "worst_drop": worst["drop"],
                "worst_sats_before": worst["sats_before"],
                "worst_sats_after": worst["sats_after"],
                "worst_timestamp": worst["timestamp"],
                "sat_drop_threshold": sat_drop_threshold,
                "sat_drop_window_sec": sat_drop_window_sec,
                "assumptions": [
                    "Sudden satellite count drop is consistent with RF interference "
                    "— sky obstruction (e.g. obstacle or maneuver) is an alternative explanation.",
                    "Position change at the same time would favor obstruction over interference.",
                ],
            },
            timestamp_start=float(events[0]["timestamp"]),
            timestamp_end=float(events[-1]["timestamp"]),
        )

    # ------------------------------------------------------------------
    # Vibration environment indicator
    # ------------------------------------------------------------------

    def _check_vibration_environment(
        self, flight: Flight, threshold: float
    ) -> Finding | None:
        """Elevated vibration outside takeoff suggests turbulent conditions."""
        if flight.vibration.empty:
            return None

        accel_cols = [c for c in flight.vibration.columns if c.startswith("accel_")]
        if not accel_cols or "timestamp" not in flight.vibration.columns:
            return None

        vib = flight.vibration.copy()

        # Skip the first 5 seconds (takeoff transient)
        if "timestamp" in vib.columns:
            min_ts = float(vib["timestamp"].iloc[0]) + 5.0
            vib = vib[vib["timestamp"] >= min_ts]

        if vib.empty:
            return None

        total_accel = np.sqrt(sum(vib[c] ** 2 for c in accel_cols))
        rms = float(np.sqrt(np.mean(total_accel ** 2)))

        if rms < threshold:
            return None

        # Cross-check: are motor outputs balanced? (mechanical vs environmental)
        note = ""
        if not flight.motors.empty:
            motor_cols = [c for c in flight.motors.columns if c.startswith("output_")]
            if motor_cols:
                tail = flight.motors.tail(20)
                outputs = [float(tail[c].mean()) for c in motor_cols]
                if max(outputs) - min(outputs) < 0.1:
                    note = (
                        " Motor outputs appear balanced, which leans toward "
                        "environmental turbulence rather than mechanical imbalance."
                    )

        return Finding(
            plugin_name=self.name,
            title=f"High vibration environment: {rms:.1f} m/s² RMS (cruise phase)",
            severity="info",
            score=45,
            description=(
                f"Vibration RMS of {rms:.1f} m/s² observed during cruise (excluding takeoff transient), "
                f"exceeding the environmental threshold of {threshold} m/s²."
                f"{note} This may indicate turbulent air conditions."
            ),
            evidence={
                "vibration_rms_ms2": round(rms, 2),
                "threshold_ms2": threshold,
                "assumptions": [
                    "Elevated vibration during cruise is consistent with turbulent conditions "
                    "— propeller imbalance or loose components are alternative explanations.",
                    "Motor output balance check reduces probability of mechanical cause when balanced.",
                ],
            },
        )

    # ------------------------------------------------------------------
    # Wind loading indicator
    # ------------------------------------------------------------------

    def _check_wind_loading(
        self, flight: Flight, bias_threshold_deg: float
    ) -> Finding | None:
        """Sustained directional attitude bias suggests wind load."""
        if flight.attitude.empty or flight.attitude_setpoint.empty:
            return None

        att = flight.attitude
        sp = flight.attitude_setpoint

        if "timestamp" not in att.columns or "timestamp" not in sp.columns:
            return None

        for axis in ("roll", "pitch"):
            if axis not in att.columns:
                continue
            sp_col = axis if axis in sp.columns else None
            if sp_col is None:
                continue

            merged = pd.merge_asof(
                att[["timestamp", axis]].sort_values("timestamp"),
                sp[["timestamp", sp_col]].sort_values("timestamp").rename(
                    columns={sp_col: f"{axis}_sp"}
                ),
                on="timestamp",
                direction="nearest",
                tolerance=0.5,
            )
            if merged.empty:
                continue

            # Compute error in degrees
            error_deg = np.degrees(merged[axis] - merged[f"{axis}_sp"])
            if len(error_deg) < 20:
                continue

            mean_bias = float(error_deg.mean())
            if abs(mean_bias) < bias_threshold_deg:
                continue

            # Check it's not correlated with maneuvers (large setpoint changes)
            sp_std = float(np.degrees(sp[sp_col].std()))
            direction = "positive" if mean_bias > 0 else "negative"

            return Finding(
                plugin_name=self.name,
                title=(
                    f"Wind loading indicator: sustained {axis} bias "
                    f"{mean_bias:+.1f} deg"
                ),
                severity="info",
                score=42,
                description=(
                    f"Attitude controller shows a sustained {axis} bias of "
                    f"{mean_bias:+.1f} deg ({direction}) relative to setpoint. "
                    f"Setpoint standard deviation: {sp_std:.1f} deg. "
                    "Persistent bias not correlated with maneuvers is consistent "
                    "with sustained wind load on the airframe."
                ),
                evidence={
                    "axis": axis,
                    "mean_bias_deg": round(mean_bias, 2),
                    "bias_direction": direction,
                    "setpoint_std_deg": round(sp_std, 2),
                    "bias_threshold_deg": bias_threshold_deg,
                    "assumptions": [
                        "Sustained attitude bias is consistent with wind loading "
                        "— trim offset or CG imbalance are alternative explanations.",
                        "Correlation with maneuvers was not checked exhaustively.",
                    ],
                },
            )

        return None
