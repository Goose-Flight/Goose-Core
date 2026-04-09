"""Battery sag analysis plugin — detects low voltage, sag under load, and sudden drops."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# 4S LiPo voltage thresholds (per-cell × 4)
CELL_COUNT = 4
WARN_VOLTAGE = 3.5 * CELL_COUNT   # 14.0 V
CRIT_VOLTAGE = 3.3 * CELL_COUNT   # 13.2 V

# Remaining battery percentage floor
MIN_REMAINING_PCT = 20.0  # warn below this

# Sag detection: voltage drop when current spikes
CURRENT_SPIKE_THRESHOLD = 10.0   # amps — defines a "load event"
SAG_DROP_THRESHOLD = 0.5         # volts — minimum sag magnitude to flag

# Sudden drop: >0.5 V in under 2 seconds
SUDDEN_DROP_VOLTS = 0.5
SUDDEN_DROP_WINDOW_SEC = 2.0


def _resolve_battery_cfg(config: dict[str, Any]) -> dict[str, float]:
    """Resolve configured battery thresholds, falling back to module constants."""
    cell_count = int(config.get("cell_count", CELL_COUNT))
    warn_per_cell = float(config.get("warn_voltage_per_cell", 3.5))
    crit_per_cell = float(config.get("crit_voltage_per_cell", 3.3))
    return {
        "cell_count": cell_count,
        "warn_voltage": warn_per_cell * cell_count,
        "crit_voltage": crit_per_cell * cell_count,
        "min_remaining_pct": float(config.get("min_remaining_pct", MIN_REMAINING_PCT)),
        "current_spike_threshold_a": float(
            config.get("current_spike_threshold_a", CURRENT_SPIKE_THRESHOLD)
        ),
        "sag_drop_threshold_v": float(config.get("sag_drop_threshold_v", SAG_DROP_THRESHOLD)),
        "sudden_drop_volts": float(config.get("sudden_drop_volts", SUDDEN_DROP_VOLTS)),
        "sudden_drop_window_sec": float(
            config.get("sudden_drop_window_sec", SUDDEN_DROP_WINDOW_SEC)
        ),
    }


class BatterySagPlugin(Plugin):
    """Analyze battery voltage, sag under load, remaining capacity, and sudden drops."""

    name = "battery_sag"
    description = (
        "Checks minimum voltage thresholds (4S), voltage sag under current load, "
        "remaining-percent floor, and sudden voltage drop events"
    )
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="battery_sag",
        name="Battery Sag Analysis",
        version="1.0.0",
        author="Goose Flight",
        description="Checks minimum voltage thresholds (4S), voltage sag under current load, remaining-percent floor, and sudden voltage drop events",
        category=PluginCategory.HEALTH,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["battery"],
        optional_streams=[],
        output_finding_types=["low_voltage", "voltage_sag", "low_remaining_pct", "sudden_voltage_drop"],
        primary_stream="battery",
    )

    # Default threshold constants — exposed so tuning profile wiring can
    # compare against the values used when no override is supplied.
    DEFAULT_CELL_COUNT = CELL_COUNT
    DEFAULT_WARN_VOLTAGE_PER_CELL = 3.5
    DEFAULT_CRIT_VOLTAGE_PER_CELL = 3.3
    DEFAULT_MIN_REMAINING_PCT = MIN_REMAINING_PCT
    DEFAULT_CURRENT_SPIKE_THRESHOLD_A = CURRENT_SPIKE_THRESHOLD
    DEFAULT_SAG_DROP_THRESHOLD_V = SAG_DROP_THRESHOLD
    DEFAULT_SUDDEN_DROP_VOLTS = SUDDEN_DROP_VOLTS
    DEFAULT_SUDDEN_DROP_WINDOW_SEC = SUDDEN_DROP_WINDOW_SEC

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run battery health checks. Returns findings for each check category."""
        findings: list[Finding] = []
        cfg = _resolve_battery_cfg(config or {})

        if flight.battery is None or flight.battery.empty:
            findings.append(Finding(
                plugin_name=self.name,
                title="No battery data available",
                severity="info",
                score=50,
                description="No battery data found in the flight log. Battery checks skipped.",
            ))
            return findings

        bat = flight.battery.copy()

        if "timestamp" not in bat.columns:
            findings.append(Finding(
                plugin_name=self.name,
                title="Battery data missing timestamp column",
                severity="info",
                score=50,
                description="Battery DataFrame present but has no 'timestamp' column.",
            ))
            return findings

        findings.extend(self._check_min_voltage(bat, cfg))
        findings.extend(self._check_voltage_sag(bat, cfg))
        findings.extend(self._check_remaining_pct(bat, cfg))
        findings.extend(self._check_sudden_drops(bat, cfg))

        return findings

    # ------------------------------------------------------------------
    # Minimum voltage
    # ------------------------------------------------------------------

    def _check_min_voltage(self, bat: pd.DataFrame, cfg: dict[str, float]) -> list[Finding]:
        """Check pack voltage against 4S warning and critical thresholds."""
        if "voltage" not in bat.columns:
            return []

        volts = bat["voltage"].dropna()
        if volts.empty:
            return []

        WARN_VOLTAGE = cfg["warn_voltage"]
        CRIT_VOLTAGE = cfg["crit_voltage"]

        min_v = round(float(volts.min()), 3)
        mean_v = round(float(volts.mean()), 3)

        if min_v >= WARN_VOLTAGE:
            return [Finding(
                plugin_name=self.name,
                title="Battery voltage nominal",
                severity="pass",
                score=95,
                description=(
                    f"Pack voltage stayed above the warning threshold of {WARN_VOLTAGE}V throughout the flight. "
                    f"Minimum observed: {min_v}V, mean: {mean_v}V."
                ),
                evidence={
                    "min_voltage": min_v,
                    "mean_voltage": mean_v,
                    "warn_threshold": WARN_VOLTAGE,
                    "critical_threshold": CRIT_VOLTAGE,
                },
            )]

        # Find when it first crossed each threshold
        ts = bat["timestamp"]
        warn_idx = bat.index[bat["voltage"] < WARN_VOLTAGE]
        crit_idx = bat.index[bat["voltage"] < CRIT_VOLTAGE]

        ts_warn_start = float(ts.loc[warn_idx[0]]) if len(warn_idx) else None
        ts_crit_start = float(ts.loc[crit_idx[0]]) if len(crit_idx) else None

        n_crit = len(crit_idx)
        pct_crit = n_crit / len(volts) * 100

        if min_v < CRIT_VOLTAGE:
            severity = "critical"
            score = 10
            title = f"Critical battery voltage — minimum {min_v}V (threshold {CRIT_VOLTAGE}V)"
            desc = (
                f"Pack voltage dropped below the critical threshold of {CRIT_VOLTAGE}V "
                f"({n_crit} samples, {pct_crit:.1f}% of flight). "
                f"Minimum: {min_v}V. Risk of brownout or permanent cell damage."
            )
        else:
            severity = "warning"
            score = 45
            n_warn = len(warn_idx)
            pct_warn = n_warn / len(volts) * 100
            title = f"Low battery voltage — minimum {min_v}V (warning threshold {WARN_VOLTAGE}V)"
            desc = (
                f"Pack voltage dropped below the warning threshold of {WARN_VOLTAGE}V "
                f"({n_warn} samples, {pct_warn:.1f}% of flight). "
                f"Minimum: {min_v}V. Consider landing earlier to protect cell health."
            )

        return [Finding(
            plugin_name=self.name,
            title=title,
            severity=severity,
            score=score,
            description=desc,
            evidence={
                "min_voltage": min_v,
                "mean_voltage": mean_v,
                "warn_threshold": WARN_VOLTAGE,
                "critical_threshold": CRIT_VOLTAGE,
                "samples_below_warn": int(len(warn_idx)),
                "samples_below_crit": int(n_crit),
            },
            timestamp_start=ts_warn_start,
            timestamp_end=ts_crit_start,
        )]

    # ------------------------------------------------------------------
    # Voltage sag under load
    # ------------------------------------------------------------------

    def _check_voltage_sag(self, bat: pd.DataFrame, cfg: dict[str, float]) -> list[Finding]:
        """Detect voltage sag when current spikes above the load threshold."""
        if "voltage" not in bat.columns or "current" not in bat.columns:
            return []

        df = bat[["timestamp", "voltage", "current"]].dropna()
        if len(df) < 10:
            return []

        CURRENT_SPIKE_THRESHOLD = cfg["current_spike_threshold_a"]
        SAG_DROP_THRESHOLD = cfg["sag_drop_threshold_v"]

        # Identify load events: windows where current exceeds the spike threshold
        high_load = df["current"] > CURRENT_SPIKE_THRESHOLD

        if not high_load.any():
            return [Finding(
                plugin_name=self.name,
                title="No significant load events detected for sag analysis",
                severity="info",
                score=75,
                description=(
                    f"Current never exceeded {CURRENT_SPIKE_THRESHOLD}A during the flight; "
                    "voltage sag under load could not be assessed."
                ),
                evidence={"current_spike_threshold": CURRENT_SPIKE_THRESHOLD},
            )]

        # Compare voltage at low-load vs high-load periods
        low_load_volts = df.loc[~high_load, "voltage"]
        high_load_volts = df.loc[high_load, "voltage"]

        baseline_v = float(low_load_volts.mean()) if not low_load_volts.empty else float(df["voltage"].mean())
        loaded_v = float(high_load_volts.mean())
        sag_mean = round(baseline_v - loaded_v, 3)
        sag_peak = round(float(low_load_volts.max() if not low_load_volts.empty else df["voltage"].max())
                         - float(high_load_volts.min()), 3)

        if sag_mean < SAG_DROP_THRESHOLD:
            return [Finding(
                plugin_name=self.name,
                title="Voltage sag under load within normal range",
                severity="pass",
                score=90,
                description=(
                    f"Mean voltage sag under load: {sag_mean}V (peak sag: {sag_peak}V). "
                    f"Both are below the {SAG_DROP_THRESHOLD}V concern threshold."
                ),
                evidence={
                    "baseline_voltage": round(baseline_v, 3),
                    "loaded_voltage": round(loaded_v, 3),
                    "mean_sag_v": sag_mean,
                    "peak_sag_v": sag_peak,
                    "sag_threshold": SAG_DROP_THRESHOLD,
                },
            )]

        severity = "critical" if sag_peak > 1.5 else "warning"
        score = 20 if severity == "critical" else 50

        # Find worst sag moment
        sag_idx = high_load_volts.idxmin()
        ts_sag = float(df.loc[sag_idx, "timestamp"]) if sag_idx in df.index else None

        return [Finding(
            plugin_name=self.name,
            title=f"Excessive voltage sag under load — peak {sag_peak}V drop",
            severity=severity,
            score=score,
            description=(
                f"Battery voltage sags {sag_mean}V on average (peak {sag_peak}V) when current "
                f"exceeds {CURRENT_SPIKE_THRESHOLD}A. "
                "High internal resistance may indicate an aged or damaged pack. "
                "Effective usable capacity and motor performance are reduced."
            ),
            evidence={
                "baseline_voltage": round(baseline_v, 3),
                "min_loaded_voltage": round(float(high_load_volts.min()), 3),
                "mean_sag_v": sag_mean,
                "peak_sag_v": sag_peak,
                "sag_threshold": SAG_DROP_THRESHOLD,
                "current_spike_threshold": CURRENT_SPIKE_THRESHOLD,
            },
            timestamp_start=ts_sag,
        )]

    # ------------------------------------------------------------------
    # Remaining percentage floor
    # ------------------------------------------------------------------

    def _check_remaining_pct(self, bat: pd.DataFrame, cfg: dict[str, float]) -> list[Finding]:
        """Check that remaining battery percentage never drops below the safe floor."""
        if "remaining_pct" not in bat.columns:
            return []

        pct = bat["remaining_pct"].dropna()
        if pct.empty:
            return []

        MIN_REMAINING_PCT = cfg["min_remaining_pct"]

        min_pct = round(float(pct.min()), 1)
        final_pct = round(float(pct.iloc[-1]), 1) if len(pct) else min_pct

        if min_pct >= MIN_REMAINING_PCT:
            return [Finding(
                plugin_name=self.name,
                title="Battery remaining percentage nominal",
                severity="pass",
                score=90,
                description=(
                    f"Battery remaining percentage stayed at or above {MIN_REMAINING_PCT}% "
                    f"throughout the flight. Minimum observed: {min_pct}%, final: {final_pct}%."
                ),
                evidence={
                    "min_remaining_pct": min_pct,
                    "final_remaining_pct": final_pct,
                    "threshold_pct": MIN_REMAINING_PCT,
                },
            )]

        ts = bat["timestamp"]
        low_idx = bat.index[bat["remaining_pct"] < MIN_REMAINING_PCT]
        ts_start = float(ts.loc[low_idx[0]]) if len(low_idx) else None
        ts_end = float(ts.loc[low_idx[-1]]) if len(low_idx) else None

        severity = "critical" if min_pct < 10.0 else "warning"
        score = 15 if severity == "critical" else 45

        return [Finding(
            plugin_name=self.name,
            title=f"Battery depleted below {MIN_REMAINING_PCT}% — minimum {min_pct}%",
            severity=severity,
            score=score,
            description=(
                f"Remaining battery percentage dropped to {min_pct}%, "
                f"below the recommended minimum of {MIN_REMAINING_PCT}%. "
                f"Final reading: {final_pct}%. "
                "Flying below this level accelerates cell degradation and increases risk of brownout."
            ),
            evidence={
                "min_remaining_pct": min_pct,
                "final_remaining_pct": final_pct,
                "threshold_pct": MIN_REMAINING_PCT,
                "samples_below_threshold": int(len(low_idx)),
            },
            timestamp_start=ts_start,
            timestamp_end=ts_end,
        )]

    # ------------------------------------------------------------------
    # Sudden voltage drops
    # ------------------------------------------------------------------

    def _check_sudden_drops(self, bat: pd.DataFrame, cfg: dict[str, float]) -> list[Finding]:
        """Detect abrupt voltage drops (>SUDDEN_DROP_VOLTS within SUDDEN_DROP_WINDOW_SEC)."""
        if "voltage" not in bat.columns:
            return []

        df = bat[["timestamp", "voltage"]].dropna().sort_values("timestamp").reset_index(drop=True)
        if len(df) < 4:
            return []

        SUDDEN_DROP_VOLTS = cfg["sudden_drop_volts"]
        SUDDEN_DROP_WINDOW_SEC = cfg["sudden_drop_window_sec"]

        drop_events: list[dict[str, Any]] = []

        for i in range(1, len(df)):
            t_curr = df.loc[i, "timestamp"]
            t_prev = df.loc[i - 1, "timestamp"]
            dt = t_curr - t_prev

            if dt <= 0 or dt > SUDDEN_DROP_WINDOW_SEC:
                continue

            v_curr = df.loc[i, "voltage"]
            v_prev = df.loc[i - 1, "voltage"]
            drop = v_prev - v_curr  # positive = drop

            if drop >= SUDDEN_DROP_VOLTS:
                drop_events.append({
                    "timestamp": round(float(t_curr), 3),
                    "voltage_before": round(float(v_prev), 3),
                    "voltage_after": round(float(v_curr), 3),
                    "drop_v": round(float(drop), 3),
                    "window_sec": round(float(dt), 3),
                })

        if not drop_events:
            return [Finding(
                plugin_name=self.name,
                title="No sudden voltage drops detected",
                severity="pass",
                score=95,
                description=(
                    f"No voltage drops exceeding {SUDDEN_DROP_VOLTS}V within "
                    f"{SUDDEN_DROP_WINDOW_SEC}s were detected."
                ),
                evidence={
                    "drop_threshold_v": SUDDEN_DROP_VOLTS,
                    "window_sec": SUDDEN_DROP_WINDOW_SEC,
                },
            )]

        max_drop = max(e["drop_v"] for e in drop_events)
        severity = "critical" if max_drop > 1.5 or len(drop_events) > 5 else "warning"
        score = 15 if severity == "critical" else 45

        return [Finding(
            plugin_name=self.name,
            title=f"Sudden voltage drop(s) detected — {len(drop_events)} event(s), max {max_drop}V",
            severity=severity,
            score=score,
            description=(
                f"Detected {len(drop_events)} voltage drop event(s) exceeding {SUDDEN_DROP_VOLTS}V "
                f"within {SUDDEN_DROP_WINDOW_SEC}s. Largest drop: {max_drop}V. "
                "Sudden drops may indicate a bad cell, loose connector, or high-current event "
                "coupled with high internal resistance."
            ),
            evidence={
                "drop_count": len(drop_events),
                "max_drop_v": max_drop,
                "drop_threshold_v": SUDDEN_DROP_VOLTS,
                "window_sec": SUDDEN_DROP_WINDOW_SEC,
                "events": drop_events[:20],  # cap evidence payload
            },
            timestamp_start=drop_events[0]["timestamp"],
            timestamp_end=drop_events[-1]["timestamp"],
        )]
