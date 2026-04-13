"""Link and telemetry health plugin.

Assesses RC link quality, telemetry dropouts, and GCS communication health
indicators using RC signal data and failsafe patterns.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest

# Configurable thresholds
DEFAULT_RSSI_MARGINAL_THRESHOLD = 0.1  # fraction of range from failsafe
DEFAULT_RC_LOSS_DURATION_SEC = 1.0
DEFAULT_TELEMETRY_GAP_MULTIPLIER = 2.0
DEFAULT_LINK_RECOVERY_COUNT = 3


class LinkTelemetryHealthPlugin(Plugin):
    """Assess RC link quality, telemetry dropouts, and GCS communication health."""

    name = "link_telemetry_health"
    description = "Assesses RC link quality, telemetry dropouts, and GCS communication health indicators"
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="link_telemetry_health",
        name="Link and Telemetry Health",
        version="1.0.0",
        author="Goose Flight",
        description=("Assesses RC link quality, telemetry dropouts, and GCS communication health indicators"),
        category=PluginCategory.HEALTH,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        # rc_input is the actual Flight attribute; rc_channels is the display name
        required_streams=["rc_input"],
        optional_streams=["flight_mode"],
        output_finding_types=[
            "rc_link_marginal",
            "rc_link_lost",
            "telemetry_gap",
            "link_recovery_anomaly",
        ],
        primary_stream="rc_channels",
    )

    # Class-level defaults
    DEFAULT_RSSI_MARGINAL_THRESHOLD = DEFAULT_RSSI_MARGINAL_THRESHOLD
    DEFAULT_RC_LOSS_DURATION_SEC = DEFAULT_RC_LOSS_DURATION_SEC
    DEFAULT_TELEMETRY_GAP_MULTIPLIER = DEFAULT_TELEMETRY_GAP_MULTIPLIER
    DEFAULT_LINK_RECOVERY_COUNT = DEFAULT_LINK_RECOVERY_COUNT

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run link and telemetry health analysis. Returns findings."""
        findings: list[Finding] = []
        cfg = config or {}

        rssi_marginal_frac = float(cfg.get("rssi_marginal_threshold", DEFAULT_RSSI_MARGINAL_THRESHOLD))
        rc_loss_sec = float(cfg.get("rc_loss_duration_sec", DEFAULT_RC_LOSS_DURATION_SEC))
        telem_gap_mult = float(cfg.get("telemetry_gap_multiplier", DEFAULT_TELEMETRY_GAP_MULTIPLIER))
        recovery_count = int(cfg.get("link_recovery_count", DEFAULT_LINK_RECOVERY_COUNT))

        rc = flight.rc_input
        if rc is None or rc.empty:
            return findings

        # RC link marginal
        marginal = self._check_rc_marginal(rc, rssi_marginal_frac)
        if marginal:
            findings.append(marginal)

        # RC link lost
        lost_findings, dropout_events = self._check_rc_lost(rc, rc_loss_sec)
        findings.extend(lost_findings)

        # Link recovery anomaly (multiple dropouts)
        if len(dropout_events) >= recovery_count:
            findings.append(self._make_recovery_anomaly(dropout_events, recovery_count))

        # Telemetry gap
        telem_gap = self._check_telemetry_gap(rc, telem_gap_mult)
        if telem_gap:
            findings.append(telem_gap)

        return findings

    # ------------------------------------------------------------------
    # RC link marginal
    # ------------------------------------------------------------------

    def _check_rc_marginal(self, rc: pd.DataFrame, rssi_marginal_frac: float) -> Finding | None:
        """RSSI near failsafe threshold for sustained periods."""
        if "rssi" not in rc.columns:
            return None

        rssi = rc["rssi"].dropna()
        if rssi.empty:
            return None

        rssi_min = float(rssi.min())
        rssi_max = float(rssi.max())
        rssi_range = rssi_max - rssi_min

        # If RSSI is perfectly constant (range == 0), we cannot infer anything
        # about proximity to failsafe — do not flag as marginal.
        if rssi_range <= 0.0:
            return None

        # "Marginal" = within rssi_marginal_frac of the observed minimum
        # (proxy for failsafe threshold when actual failsafe level is unknown)
        marginal_upper = rssi_min + rssi_range * rssi_marginal_frac
        marginal_mask = rssi <= marginal_upper

        if not marginal_mask.any():
            return None

        pct = round(float(marginal_mask.mean()) * 100, 1)
        # Only flag if marginal for >2% of flight (avoid single-sample noise)
        if pct < 2.0:
            return None

        ts_col = rc["timestamp"] if "timestamp" in rc.columns else None
        ts_start = float(ts_col[marginal_mask].iloc[0]) if ts_col is not None else None
        ts_end = float(ts_col[marginal_mask].iloc[-1]) if ts_col is not None else None

        return Finding(
            plugin_name=self.name,
            title=f"RC link marginal: RSSI near lower bound for {pct}% of flight",
            severity="warning",
            score=55,
            description=(
                f"RC RSSI was within {rssi_marginal_frac * 100:.0f}% of the observed "
                f"minimum ({rssi_min:.1f}) for {pct}% of the flight. "
                "This indicates the link was operating near its minimum observed quality, "
                "which may be close to failsafe threshold."
            ),
            evidence={
                "rssi_min_observed": round(rssi_min, 2),
                "rssi_marginal_upper": round(marginal_upper, 2),
                "pct_flight_marginal": pct,
                "rssi_marginal_frac": rssi_marginal_frac,
                "finding_type": "rc_link_marginal",
                "assumptions": [
                    "Failsafe RSSI level is approximated from observed minimum — actual failsafe threshold depends on transmitter configuration.",
                ],
            },
            timestamp_start=ts_start,
            timestamp_end=ts_end,
        )

    # ------------------------------------------------------------------
    # RC link lost
    # ------------------------------------------------------------------

    def _check_rc_lost(self, rc: pd.DataFrame, rc_loss_sec: float) -> tuple[list[Finding], list[dict[str, Any]]]:
        """Detect RC values going to zero or failsafe values for >= rc_loss_sec."""
        findings: list[Finding] = []
        dropout_events: list[dict[str, Any]] = []

        if "timestamp" not in rc.columns:
            return findings, dropout_events

        ts = rc["timestamp"].sort_values()
        if len(ts) < 2:
            return findings, dropout_events

        # Heuristic: detect gaps in the RC data stream >= rc_loss_sec
        gaps = ts.diff().dropna()
        loss_mask = gaps >= rc_loss_sec

        if not loss_mask.any():
            return findings, dropout_events

        gap_series = gaps[loss_mask]
        for idx_pos, (_, gap_val) in enumerate(gap_series.items()):
            # idx in ts is the position after the gap
            pos = ts.index.get_loc(_) if hasattr(ts.index, "get_loc") else idx_pos
            try:
                ts_gap_start = float(ts.iloc[pos - 1])
            except (IndexError, ValueError):
                ts_gap_start = float(ts.iloc[0])
            ts_gap_end = float(ts.iloc[pos]) if pos < len(ts) else ts_gap_start + float(gap_val)

            dropout_events.append(
                {
                    "timestamp_start": ts_gap_start,
                    "timestamp_end": ts_gap_end,
                    "duration_sec": round(float(gap_val), 3),
                }
            )

        if not dropout_events:
            return findings, dropout_events

        max_loss = max(e["duration_sec"] for e in dropout_events)
        score = 70 if max_loss >= 3.0 else 65

        findings.append(
            Finding(
                plugin_name=self.name,
                title=(f"RC link lost: {len(dropout_events)} loss event(s), longest {max_loss:.1f}s"),
                severity="warning",
                score=score,
                description=(
                    f"Detected {len(dropout_events)} RC data gap(s) of "
                    f">= {rc_loss_sec}s. Longest: {max_loss:.1f}s. "
                    "RC link loss at this duration may trigger failsafe behavior."
                ),
                evidence={
                    "dropout_count": len(dropout_events),
                    "max_loss_duration_sec": max_loss,
                    "rc_loss_threshold_sec": rc_loss_sec,
                    "events": dropout_events[:10],
                    "finding_type": "rc_link_lost",
                    "assumptions": [
                        "RC data gaps are used as proxy for link loss — logging interruptions are an alternative explanation.",
                    ],
                },
                timestamp_start=dropout_events[0]["timestamp_start"],
                timestamp_end=dropout_events[-1]["timestamp_end"],
            )
        )

        return findings, dropout_events

    # ------------------------------------------------------------------
    # Link recovery anomaly
    # ------------------------------------------------------------------

    def _make_recovery_anomaly(
        self,
        dropout_events: list[dict[str, Any]],
        recovery_count: int,
    ) -> Finding:
        """Multiple drop-and-recover cycles indicate marginal link quality."""
        count = len(dropout_events)
        ts_start = dropout_events[0]["timestamp_start"]
        ts_end = dropout_events[-1]["timestamp_end"]
        total_loss_sec = round(sum(e["duration_sec"] for e in dropout_events), 2)

        return Finding(
            plugin_name=self.name,
            title=(f"Link recovery anomaly: {count} drop-and-recover cycles (threshold: {recovery_count})"),
            severity="warning",
            score=62,
            description=(
                f"RC link dropped and recovered {count} time(s), exceeding the "
                f"threshold of {recovery_count}. "
                f"Total RC loss time: {total_loss_sec}s. "
                "Repeated drop-and-recover cycles are characteristic of a marginal link "
                "rather than a single clean loss event."
            ),
            evidence={
                "dropout_count": count,
                "total_loss_sec": total_loss_sec,
                "recovery_count_threshold": recovery_count,
                "finding_type": "link_recovery_anomaly",
                "assumptions": [
                    "Each data gap is treated as one drop-and-recover cycle; actual protocol-level reconnects may differ.",
                ],
            },
            timestamp_start=ts_start,
            timestamp_end=ts_end,
        )

    # ------------------------------------------------------------------
    # Telemetry gap
    # ------------------------------------------------------------------

    def _check_telemetry_gap(self, rc: pd.DataFrame, gap_multiplier: float) -> Finding | None:
        """Detect gaps in log message rate (> gap_multiplier * average interval)."""
        if "timestamp" not in rc.columns or len(rc) < 10:
            return None

        ts = rc["timestamp"].sort_values().reset_index(drop=True)
        intervals = ts.diff().dropna()
        if intervals.empty:
            return None

        avg_interval = float(intervals.median())
        if avg_interval <= 0:
            return None

        gap_threshold = avg_interval * gap_multiplier
        large_gaps = intervals[intervals > gap_threshold]

        if large_gaps.empty:
            return None

        max_gap = float(large_gaps.max())
        count = len(large_gaps)
        # Find timestamp of worst gap
        worst_pos = int(large_gaps.idxmax())
        try:
            ts_worst = float(ts.iloc[worst_pos - 1])
        except (IndexError, ValueError):
            ts_worst = float(ts.iloc[0])

        return Finding(
            plugin_name=self.name,
            title=(f"Telemetry gap detected: {count} gap(s), largest {max_gap:.2f}s ({gap_multiplier:.0f}x avg interval)"),
            severity="info",
            score=50,
            description=(
                f"Found {count} timestamp gap(s) exceeding {gap_multiplier:.1f}x "
                f"the average RC message interval ({avg_interval * 1000:.0f}ms). "
                f"Largest gap: {max_gap:.2f}s at t={ts_worst:.1f}s. "
                "Telemetry gaps may indicate link issues or a logging interruption."
            ),
            evidence={
                "gap_count": count,
                "max_gap_sec": round(max_gap, 3),
                "avg_interval_sec": round(avg_interval, 4),
                "gap_threshold_sec": round(gap_threshold, 4),
                "worst_gap_timestamp": round(ts_worst, 3),
                "finding_type": "telemetry_gap",
                "assumptions": [
                    "Telemetry gaps may indicate link issues or logging interruption — the two cannot be distinguished from log data alone.",
                ],
            },
            timestamp_start=ts_worst,
            timestamp_end=ts_worst + max_gap,
        )
