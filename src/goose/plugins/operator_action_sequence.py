"""Operator action sequence plugin — analyzes RC input and mode switch sequences.

Detects anomalous control patterns that may indicate operator contribution to
a flight anomaly. This is intentionally conservative — it does not make causal
claims, only flags patterns for investigator attention.

Patterns detected:
1. Rapid mode switches — multiple mode changes in a short window
2. Disarm while airborne — disarm event with non-zero altitude
3. Abrupt stick inputs — sudden large RC input change near an anomaly window
4. Failsafe trigger at altitude — failsafe fires while vehicle is at height

Design rules:
- Requires rc_input OR mode_changes stream; degrades gracefully without both.
- Never attributes blame — findings are "operator action detected", not "pilot error".
- timestamp_start/end always set so findings appear on the timeline.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest

# Thresholds
DEFAULT_RAPID_SWITCH_WINDOW_SEC = 10.0  # time window to look for multiple mode changes
DEFAULT_RAPID_SWITCH_COUNT = 3  # mode changes in window = "rapid"
DEFAULT_STICK_CHANGE_THRESHOLD = 0.5  # normalized 0-1 step change = "abrupt"
DEFAULT_MIN_ALTITUDE_DISARM_M = 2.0  # altitude above this at disarm = flagged
DEFAULT_FAILSAFE_ALTITUDE_M = 3.0  # failsafe below this = low-level (less concern)


class OperatorActionSequencePlugin(Plugin):
    """Analyze RC input sequence and mode switches for anomalous operator action patterns.

    This plugin contributes to the 'operator_action' hypothesis theme.
    Findings are informational — they flag patterns for investigator attention,
    not causal conclusions.
    """

    name = "operator_action_sequence"
    description = "Analyzes RC input and mode switch sequences for anomalous operator action patterns. Contributes to operator_action hypothesis theme."
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="operator_action_sequence",
        name="Operator Action Sequence",
        version="1.0.0",
        author="Goose Flight",
        description=("Analyzes RC input and mode switch sequences for anomalous operator action patterns. Contributes to operator_action hypothesis theme."),
        category=PluginCategory.RF_COMMS,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=[],  # works with partial data
        optional_streams=["rc_input", "flight_mode", "position"],
        output_finding_types=[
            "rapid_mode_switches",
            "disarm_while_airborne",
            "abrupt_stick_input",
            "failsafe_at_altitude",
        ],
        primary_stream="rc_channels",
    )

    DEFAULT_RAPID_SWITCH_WINDOW_SEC = DEFAULT_RAPID_SWITCH_WINDOW_SEC
    DEFAULT_RAPID_SWITCH_COUNT = DEFAULT_RAPID_SWITCH_COUNT
    DEFAULT_STICK_CHANGE_THRESHOLD = DEFAULT_STICK_CHANGE_THRESHOLD
    DEFAULT_MIN_ALTITUDE_DISARM_M = DEFAULT_MIN_ALTITUDE_DISARM_M
    DEFAULT_FAILSAFE_ALTITUDE_M = DEFAULT_FAILSAFE_ALTITUDE_M

    DEFAULT_CONFIG: dict[str, Any] = {
        "rapid_switch_window_sec": DEFAULT_RAPID_SWITCH_WINDOW_SEC,
        "rapid_switch_count": DEFAULT_RAPID_SWITCH_COUNT,
        "stick_change_threshold": DEFAULT_STICK_CHANGE_THRESHOLD,
        "min_altitude_disarm_m": DEFAULT_MIN_ALTITUDE_DISARM_M,
        "failsafe_altitude_m": DEFAULT_FAILSAFE_ALTITUDE_M,
    }

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        cfg = {**self.DEFAULT_CONFIG, **config}
        findings: list[Finding] = []

        has_rc = not flight.rc_input.empty
        has_mode_changes = bool(getattr(flight, "mode_changes", []))
        has_events = bool(getattr(flight, "events", []))

        if not has_rc and not has_mode_changes and not has_events:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="Insufficient data for operator action analysis",
                    severity="info",
                    score=50,
                    description=("No RC input, mode change, or event data available. Operator action analysis requires at least one of these streams."),
                )
            )
            return findings

        # 1. Rapid mode switches
        rapid_finding = self._check_rapid_mode_switches(flight, cfg)
        if rapid_finding:
            findings.append(rapid_finding)

        # 2. Disarm while airborne
        disarm_finding = self._check_disarm_while_airborne(flight, cfg)
        if disarm_finding:
            findings.append(disarm_finding)

        # 3. Abrupt stick inputs (RC only)
        if has_rc:
            stick_findings = self._check_abrupt_stick_inputs(flight, cfg)
            findings.extend(stick_findings)

        # 4. Failsafe trigger at significant altitude
        fs_finding = self._check_failsafe_at_altitude(flight, cfg)
        if fs_finding:
            findings.append(fs_finding)

        if not findings:
            findings.append(
                Finding(
                    plugin_name=self.name,
                    title="No anomalous operator action patterns detected",
                    severity="pass",
                    score=90,
                    description=("RC input sequence and mode changes reviewed. No anomalous operator action patterns detected above threshold."),
                )
            )

        return findings

    def _check_rapid_mode_switches(self, flight: Flight, cfg: dict[str, Any]) -> Finding | None:
        """Detect multiple mode switches in a short time window."""
        mode_changes = getattr(flight, "mode_changes", []) or []
        if len(mode_changes) < cfg["rapid_switch_count"]:
            return None

        window = cfg["rapid_switch_window_sec"]
        count_threshold = int(cfg["rapid_switch_count"])

        timestamps = [float(mc.timestamp) for mc in mode_changes]
        timestamps.sort()

        # Sliding window: check every sub-sequence of count_threshold events
        best_window: tuple[float, float, int] | None = None
        for i in range(len(timestamps) - count_threshold + 1):
            window_start = timestamps[i]
            window_end = timestamps[i + count_threshold - 1]
            if window_end - window_start <= window:
                if best_window is None or (window_end - window_start) < (best_window[1] - best_window[0]):
                    best_window = (window_start, window_end, count_threshold)

        if best_window is None:
            return None

        t_start, t_end, n_switches = best_window
        duration = t_end - t_start

        # List modes in the window
        window_modes = [f"{mc.from_mode}→{mc.to_mode}" for mc in mode_changes if t_start <= float(mc.timestamp) <= t_end]

        return Finding(
            plugin_name=self.name,
            title=f"Rapid mode switching: {n_switches} switches in {duration:.1f}s",
            severity="warning",
            score=45,
            description=(
                f"{n_switches} mode changes occurred within {duration:.1f}s. "
                f"Sequence: {', '.join(window_modes)}. "
                "Rapid mode switching at a critical moment may indicate operator response to an anomaly "
                "or accidental input. Correlate with pilot account of events."
            ),
            evidence={
                "switch_count": n_switches,
                "window_sec": round(duration, 2),
                "threshold_switches": count_threshold,
                "threshold_window_sec": window,
                "mode_sequence": window_modes,
            },
            timestamp_start=t_start,
            timestamp_end=t_end,
        )

    def _check_disarm_while_airborne(self, flight: Flight, cfg: dict[str, Any]) -> Finding | None:
        """Detect if the vehicle was disarmed while still at altitude."""
        events = getattr(flight, "events", []) or []
        disarm_events = [e for e in events if "disarm" in (e.message or "").lower()]
        if not disarm_events:
            return None

        if flight.position.empty or "timestamp" not in flight.position.columns:
            return None

        alt_col = "alt_rel" if "alt_rel" in flight.position.columns else "alt_msl"
        if alt_col not in flight.position.columns:
            return None

        min_alt_threshold = cfg["min_altitude_disarm_m"]

        for ev in disarm_events:
            t = float(ev.timestamp)
            # Find altitude near disarm time
            pos_near = flight.position[(flight.position["timestamp"] >= t - 1.0) & (flight.position["timestamp"] <= t + 1.0)]
            if pos_near.empty:
                continue

            alt_at_disarm = float(pos_near[alt_col].mean())
            if alt_at_disarm > min_alt_threshold:
                return Finding(
                    plugin_name=self.name,
                    title=f"Disarm event while airborne ({alt_at_disarm:.1f}m altitude)",
                    severity="warning",
                    score=30,
                    description=(
                        f"Vehicle was disarmed at {alt_at_disarm:.1f}m altitude (>{min_alt_threshold}m threshold). "
                        "In-flight disarming causes immediate motor cut and freefall. "
                        "Determine whether this was intentional emergency disarm or accidental input."
                    ),
                    evidence={
                        "altitude_at_disarm_m": round(alt_at_disarm, 2),
                        "min_altitude_threshold_m": min_alt_threshold,
                        "disarm_event_message": ev.message,
                    },
                    timestamp_start=t,
                    timestamp_end=t,
                )

        return None

    def _check_abrupt_stick_inputs(self, flight: Flight, cfg: dict[str, Any]) -> list[Finding]:
        """Detect sudden large RC input changes that may indicate startle response."""
        findings: list[Finding] = []
        rc = flight.rc_input
        if rc.empty or "timestamp" not in rc.columns:
            return findings

        # Find channel columns (typically channel_1 through channel_8, or chan_*)
        chan_cols = [c for c in rc.columns if c.startswith(("channel_", "chan_", "ch_", "rc_"))]
        if not chan_cols:
            return findings

        threshold = cfg["stick_change_threshold"]
        ts = rc["timestamp"]

        for col in chan_cols[:4]:  # Check first 4 channels (primary flight controls)
            ch_vals = pd.to_numeric(rc[col], errors="coerce")
            if ch_vals.isna().all():
                continue

            # Normalize to 0-1 range
            ch_min = float(ch_vals.min())
            ch_max = float(ch_vals.max())
            if ch_max - ch_min < 100:  # Not PWM-like or too small range
                continue
            normalized = (ch_vals - ch_min) / (ch_max - ch_min)

            # Compute step changes
            step = normalized.diff().abs()
            big_steps = step[step > threshold]
            if big_steps.empty:
                continue

            # Report the single largest step
            max_step_idx = big_steps.idxmax()
            max_step = float(big_steps.loc[max_step_idx])
            t_step = float(ts.loc[max_step_idx])

            findings.append(
                Finding(
                    plugin_name=self.name,
                    title=f"Abrupt stick input on {col} ({max_step:.0%} change)",
                    severity="info",
                    score=60,
                    description=(
                        f"RC {col} changed by {max_step:.0%} (normalized) in a single sample at t={t_step:.1f}s. "
                        f"This may indicate a rapid corrective input, startle response, or stick stick glitch. "
                        f"Threshold: >{threshold:.0%} change per sample."
                    ),
                    evidence={
                        "channel": col,
                        "step_magnitude_normalized": round(max_step, 3),
                        "threshold": threshold,
                        "timestamp": t_step,
                    },
                    timestamp_start=t_step,
                    timestamp_end=t_step,
                )
            )

        return findings

    def _check_failsafe_at_altitude(self, flight: Flight, cfg: dict[str, Any]) -> Finding | None:
        """Detect failsafe events that occurred at significant altitude."""
        events = getattr(flight, "events", []) or []
        fs_events = [e for e in events if "failsafe" in (e.event_type or "").lower() or "failsafe" in (e.message or "").lower()]
        if not fs_events:
            return None

        if flight.position.empty or "timestamp" not in flight.position.columns:
            return None

        alt_col = "alt_rel" if "alt_rel" in flight.position.columns else "alt_msl"
        if alt_col not in flight.position.columns:
            return None

        alt_threshold = cfg["failsafe_altitude_m"]

        for ev in fs_events:
            t = float(ev.timestamp)
            pos_near = flight.position[(flight.position["timestamp"] >= t - 2.0) & (flight.position["timestamp"] <= t + 2.0)]
            if pos_near.empty:
                continue

            alt_at_fs = float(pos_near[alt_col].mean())
            if alt_at_fs > alt_threshold:
                return Finding(
                    plugin_name=self.name,
                    title=f"Failsafe triggered at {alt_at_fs:.1f}m altitude",
                    severity="warning",
                    score=35,
                    description=(
                        f"A failsafe event ('{ev.message}') was triggered at {alt_at_fs:.1f}m altitude. "
                        "Failsafe triggers at altitude indicate either an RC link loss or operator-induced "
                        "failsafe. Determine whether this was a link loss or intentional command."
                    ),
                    evidence={
                        "altitude_at_failsafe_m": round(alt_at_fs, 2),
                        "altitude_threshold_m": alt_threshold,
                        "failsafe_message": ev.message,
                        "failsafe_type": ev.event_type,
                    },
                    timestamp_start=t,
                    timestamp_end=t,
                )

        return None
