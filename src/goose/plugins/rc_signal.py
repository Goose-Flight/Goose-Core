"""RC signal quality plugin — RSSI monitoring, dropout detection, and failsafe analysis."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# RSSI thresholds (0-100 %)
RSSI_WARNING = 70.0
RSSI_CRITICAL = 50.0

# Dropout: gap in RC input data longer than this is considered a dropout
DROPOUT_GAP_SEC = 2.0

# Stuck channel: channel value unchanged for longer than this
STUCK_CHANNEL_SEC = 10.0


class RcSignalPlugin(Plugin):
    """Analyze RC signal quality — RSSI levels, dropouts, and stuck channels."""

    name = "rc_signal"
    description = "RC signal quality and failsafe detection"
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="rc_signal",
        name="RC Signal Quality",
        version="1.0.0",
        author="Goose Flight",
        description="Analyzes RC signal quality including RSSI levels, dropouts, and stuck channels",
        category=PluginCategory.RF_COMMS,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["rc_input"],
        optional_streams=[],
        output_finding_types=["rssi_level", "rc_dropout", "stuck_channel"],
    )

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run RC signal quality checks. Returns findings."""
        findings: list[Finding] = []

        if flight.rc_input is None or flight.rc_input.empty:
            findings.append(Finding(
                plugin_name=self.name,
                title="No RC input data available",
                severity="info",
                score=50,
                description="No RC input data found in the flight log. RC signal checks skipped.",
            ))
            return findings

        rc = flight.rc_input.copy()

        required_cols = {"timestamp", "rssi"}
        missing = required_cols - set(rc.columns)
        if missing:
            findings.append(Finding(
                plugin_name=self.name,
                title="RC data missing required columns",
                severity="info",
                score=50,
                description=f"RC input DataFrame is missing columns: {sorted(missing)}. Cannot assess signal quality.",
                evidence={"missing_columns": sorted(missing), "available_columns": list(rc.columns)},
            ))
            return findings

        findings.extend(self._check_rssi(rc))
        findings.extend(self._check_dropouts(rc))
        findings.extend(self._check_stuck_channels(rc))

        return findings

    # ------------------------------------------------------------------
    # RSSI level checks
    # ------------------------------------------------------------------

    def _check_rssi(self, rc: pd.DataFrame) -> list[Finding]:
        """Check minimum and average RSSI against warning/critical thresholds."""
        rssi = rc["rssi"].dropna()
        if rssi.empty:
            return []

        min_rssi = round(float(rssi.min()), 1)
        mean_rssi = round(float(rssi.mean()), 1)

        if min_rssi >= RSSI_WARNING:
            return [Finding(
                plugin_name=self.name,
                title="RC signal strength nominal",
                severity="pass",
                score=95,
                description=(
                    f"RSSI stayed above the warning threshold of {RSSI_WARNING}% throughout the flight. "
                    f"Minimum: {min_rssi}%, mean: {mean_rssi}%."
                ),
                evidence={
                    "min_rssi_pct": min_rssi,
                    "mean_rssi_pct": mean_rssi,
                    "warning_threshold": RSSI_WARNING,
                    "critical_threshold": RSSI_CRITICAL,
                },
            )]

        # Find timestamps of first threshold crossings
        ts = rc["timestamp"]
        warn_idx = rc.index[rc["rssi"] < RSSI_WARNING]
        crit_idx = rc.index[rc["rssi"] < RSSI_CRITICAL]

        ts_warn_start = float(ts.loc[warn_idx[0]]) if len(warn_idx) else None
        ts_crit_start = float(ts.loc[crit_idx[0]]) if len(crit_idx) else None

        n_warn = len(warn_idx)
        n_crit = len(crit_idx)
        pct_warn = round(n_warn / len(rssi) * 100, 1)
        pct_crit = round(n_crit / len(rssi) * 100, 1)

        if min_rssi < RSSI_CRITICAL:
            severity = "critical"
            score = 10
            title = f"Critical RC signal loss — minimum RSSI {min_rssi}% (threshold {RSSI_CRITICAL}%)"
            desc = (
                f"RC signal dropped below the critical threshold of {RSSI_CRITICAL}% "
                f"({n_crit} samples, {pct_crit}% of flight). "
                f"Minimum RSSI: {min_rssi}%, mean: {mean_rssi}%. Failsafe risk is high."
            )
        else:
            severity = "warning"
            score = 45
            title = f"Weak RC signal — minimum RSSI {min_rssi}% (warning threshold {RSSI_WARNING}%)"
            desc = (
                f"RC signal dropped below the warning threshold of {RSSI_WARNING}% "
                f"({n_warn} samples, {pct_warn}% of flight). "
                f"Minimum RSSI: {min_rssi}%, mean: {mean_rssi}%. Consider improving antenna placement."
            )

        return [Finding(
            plugin_name=self.name,
            title=title,
            severity=severity,
            score=score,
            description=desc,
            evidence={
                "min_rssi_pct": min_rssi,
                "mean_rssi_pct": mean_rssi,
                "warning_threshold": RSSI_WARNING,
                "critical_threshold": RSSI_CRITICAL,
                "samples_below_warning": n_warn,
                "samples_below_critical": n_crit,
                "pct_below_warning": pct_warn,
                "pct_below_critical": pct_crit,
            },
            timestamp_start=ts_warn_start,
            timestamp_end=ts_crit_start,
        )]

    # ------------------------------------------------------------------
    # Dropout detection
    # ------------------------------------------------------------------

    def _check_dropouts(self, rc: pd.DataFrame) -> list[Finding]:
        """Detect gaps in RC input data longer than DROPOUT_GAP_SEC."""
        ts = rc["timestamp"].sort_values().reset_index(drop=True)
        if len(ts) < 2:
            return []

        gaps = ts.diff().dropna()
        dropout_mask = gaps > DROPOUT_GAP_SEC
        dropout_gaps = gaps[dropout_mask]

        if dropout_gaps.empty:
            return [Finding(
                plugin_name=self.name,
                title="No RC signal dropouts detected",
                severity="pass",
                score=95,
                description=f"No gaps larger than {DROPOUT_GAP_SEC}s found in RC input data stream.",
                evidence={"dropout_threshold_sec": DROPOUT_GAP_SEC, "dropout_count": 0},
            )]

        dropout_events = []
        for pos, idx in enumerate(dropout_gaps.index):
            # idx is the RangeIndex position in ts (after reset_index); ts.iloc[idx-1] is the gap start
            try:
                ts_start_val = float(ts.iloc[int(idx) - 1])
            except (IndexError, ValueError):
                ts_start_val = float(ts.iloc[0])
            dropout_events.append({
                "timestamp": round(ts_start_val, 3),
                "gap_sec": round(float(dropout_gaps.iloc[pos]), 3),
            })

        max_gap = round(float(dropout_gaps.max()), 3)
        count = len(dropout_events)
        severity = "critical" if max_gap > 5.0 or count > 3 else "warning"
        score = 15 if severity == "critical" else 45

        return [Finding(
            plugin_name=self.name,
            title=f"RC signal dropout(s) detected — {count} event(s), longest {max_gap}s",
            severity=severity,
            score=score,
            description=(
                f"Detected {count} RC input gap(s) exceeding {DROPOUT_GAP_SEC}s. "
                f"Longest dropout: {max_gap}s. "
                "Signal dropouts may trigger the RC failsafe and cause uncontrolled behavior."
            ),
            evidence={
                "dropout_count": count,
                "max_gap_sec": max_gap,
                "dropout_threshold_sec": DROPOUT_GAP_SEC,
                "events": dropout_events[:20],
            },
            timestamp_start=dropout_events[0]["timestamp"] if dropout_events else None,
        )]

    # ------------------------------------------------------------------
    # Stuck channel detection
    # ------------------------------------------------------------------

    def _check_stuck_channels(self, rc: pd.DataFrame) -> list[Finding]:
        """Detect RC channels whose value is unchanged for longer than STUCK_CHANNEL_SEC."""
        channel_cols = [c for c in rc.columns if c.startswith("chan") or c.startswith("channel")]
        if not channel_cols:
            return []

        ts = rc["timestamp"]
        duration = float(ts.iloc[-1] - ts.iloc[0]) if len(ts) > 1 else 0.0
        if duration < STUCK_CHANNEL_SEC:
            return []

        stuck: list[str] = []
        for col in channel_cols:
            series = rc[col].dropna()
            if series.empty:
                continue
            # Check if the channel value is constant throughout the entire series
            if series.nunique() == 1:
                stuck.append(col)

        if not stuck:
            return [Finding(
                plugin_name=self.name,
                title="No stuck RC channels detected",
                severity="pass",
                score=95,
                description=(
                    f"All RC channels showed variation over the flight. "
                    f"Checked {len(channel_cols)} channel(s)."
                ),
                evidence={"checked_channels": channel_cols},
            )]

        return [Finding(
            plugin_name=self.name,
            title=f"Stuck RC channel(s) detected — {', '.join(stuck)}",
            severity="warning",
            score=40,
            description=(
                f"Channel(s) {stuck} showed no variation throughout the {duration:.1f}s flight. "
                "A stuck channel may indicate a hardware failure, misconfigured transmitter, "
                "or signal corruption."
            ),
            evidence={
                "stuck_channels": stuck,
                "checked_channels": channel_cols,
                "flight_duration_sec": round(duration, 1),
                "stuck_threshold_sec": STUCK_CHANNEL_SEC,
            },
        )]
