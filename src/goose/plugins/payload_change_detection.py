"""Payload change detection plugin — Phase 1 candidate detector.

Detects candidate mid-flight payload or mass-change events by correlating
current draw with throttle/motor output and (when available) vertical
response. Phase 1 is intentionally a low-confidence candidate detector
meant as an investigator review aid, not a final classification.

Use cases:
    - prison / contraband drop investigations
    - delivery / release mechanism validation
    - tactical payload event review
    - unintentional payload detach detection
    - load / snag events
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import (
    PluginCategory,
    PluginManifest,
    PluginTrustState,
)


class PayloadChangeDetectionPlugin(Plugin):
    """Detect candidate mid-flight payload / mass-change events."""

    name = "payload_change_detection"
    description = (
        "Phase 1 candidate detector for mid-flight payload / mass-change events."
    )
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="payload_change_detection",
        name="Payload Change Detection",
        version="1.0.0",
        author="Goose-Core",
        description=(
            "Detects candidate mid-flight payload or mass-change events by "
            "correlating current draw, thrust demand, and motor output patterns. "
            "Phase 1: candidate detector with medium-low confidence. Use as "
            "investigator review aid, not final classification."
        ),
        category=PluginCategory.MISSION_RULES,
        supported_vehicle_types=["multirotor", "all"],
        # The base Plugin.forensic_analyze() checks required_streams via
        # getattr(flight, stream_name). The canonical Flight model exposes
        # battery as a DataFrame with a 'current' column — so we require
        # the "battery" stream itself.
        required_streams=["battery"],
        optional_streams=[
            "motors",
            "velocity",
            "position",
            "attitude",
            "rc_input",
        ],
        output_finding_types=[
            "possible_payload_release_event",
            "possible_mass_reduction_event",
            "possible_load_increase_event",
            "possible_midflight_load_shift",
        ],
        minimum_contract_version="2.0",
        plugin_type="builtin",
        trust_state=PluginTrustState.BUILTIN_TRUSTED,
    )

    # Default thresholds — all overridable via config / tuning profile.
    DEFAULT_CURRENT_DELTA_THRESHOLD = 3.0   # amps — minimum sustained current change
    DEFAULT_SUSTAINED_DURATION_S = 1.5      # seconds — change must persist this long
    DEFAULT_PRE_POST_WINDOW_S = 5.0         # seconds for pre/post moving average
    DEFAULT_COMMAND_TOLERANCE = 0.15        # fractional throttle tolerance
    DEFAULT_MIN_FLIGHT_DURATION_S = 10.0    # minimum flight duration to run analysis

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Phase 1: detect abrupt sustained current changes not explained by throttle."""
        findings: list[Finding] = []
        cfg = config or {}

        current_delta = float(
            cfg.get("current_delta_threshold", self.DEFAULT_CURRENT_DELTA_THRESHOLD)
        )
        sustained_s = float(
            cfg.get("sustained_duration_s", self.DEFAULT_SUSTAINED_DURATION_S)
        )
        pre_post_s = float(
            cfg.get("pre_post_window_s", self.DEFAULT_PRE_POST_WINDOW_S)
        )
        cmd_tolerance = float(
            cfg.get("command_tolerance", self.DEFAULT_COMMAND_TOLERANCE)
        )
        min_flight_s = float(
            cfg.get("min_flight_duration_s", self.DEFAULT_MIN_FLIGHT_DURATION_S)
        )

        # Required: battery current stream
        current_stream = self._get_current_stream(flight)
        if current_stream is None or len(current_stream) < 10:
            return findings

        times = [p[0] for p in current_stream]
        currents = [p[1] for p in current_stream]

        # Need a minimum flight duration
        if times[-1] - times[0] < min_flight_s:
            return findings

        # Optional throttle stream (derived from motors or rc_input) for
        # false-positive suppression.
        throttle_stream = self._get_throttle_stream(flight)

        # Find candidate windows
        candidates = self._find_candidate_windows(
            times, currents, current_delta, sustained_s, pre_post_s
        )

        for cand in candidates:
            # Suppress if throttle moved proportionally around the event window
            if throttle_stream and self._throttle_explains_change(
                throttle_stream,
                cand["start_time"],
                cand["end_time"],
                cand["delta_amps"],
                cmd_tolerance,
            ):
                continue

            change_type = "reduction" if cand["delta_amps"] < 0 else "increase"
            if change_type == "reduction":
                finding_type = "possible_mass_reduction_event"
            else:
                finding_type = "possible_load_increase_event"

            # Phase 1: intentionally low-confidence (0.25-0.45 range)
            confidence_base = 0.35
            if abs(cand["delta_amps"]) > current_delta * 2:
                confidence_base += 0.10  # up to ~0.45

            severity = (
                "warning"
                if abs(cand["delta_amps"]) > current_delta * 2
                else "info"
            )

            findings.append(
                Finding(
                    plugin_name=self.manifest.plugin_id,
                    title=f"Possible payload {change_type} event detected",
                    description=(
                        f"Current draw changed by {cand['delta_amps']:+.1f}A at "
                        f"T={cand['start_time']:.1f}s and sustained for "
                        f"{cand['duration_s']:.1f}s without a proportional throttle "
                        "change. This may indicate a mid-flight mass/load change. "
                        "Phase 1 detection — treat as investigator review aid, "
                        "not confirmed classification."
                    ),
                    severity=severity,
                    score=int(round(confidence_base * 100)),
                    evidence={
                        "current_delta_amps": round(cand["delta_amps"], 3),
                        "pre_event_avg_amps": round(cand["pre_avg"], 3),
                        "post_event_avg_amps": round(cand["post_avg"], 3),
                        "sustained_duration_s": round(cand["duration_s"], 3),
                        "detection_phase": "phase_1_candidate",
                        "stream_used": "battery.current",
                        "finding_type": finding_type,
                        "confidence": round(confidence_base, 2),
                        "assumptions": [
                            "Phase 1 detection: correlates current draw only, "
                            "not full multi-signal analysis",
                            "Low-confidence candidate — requires investigator review",
                            "Throttle change suppression applied but may not cover "
                            "all false-positive cases",
                        ],
                        "recommendations": [
                            "Review chart of battery current around this time window",
                            "Check motor outputs for corresponding change",
                            "Check altitude/vertical velocity for response change",
                            "Consider flight context: was a release, drop, or load "
                            "change expected?",
                        ],
                    },
                    phase=None,
                    timestamp_start=cand["start_time"],
                    timestamp_end=cand["end_time"],
                )
            )

        return findings

    # ------------------------------------------------------------------
    # Stream helpers
    # ------------------------------------------------------------------

    def _get_current_stream(
        self, flight: Flight
    ) -> list[tuple[float, float]] | None:
        """Return [(timestamp, current_amps), ...] from the battery DataFrame."""
        bat = getattr(flight, "battery", None)
        if bat is None or not isinstance(bat, pd.DataFrame) or bat.empty:
            return None
        if "timestamp" not in bat.columns or "current" not in bat.columns:
            return None
        df = bat[["timestamp", "current"]].dropna()
        if df.empty:
            return None
        df = df.sort_values("timestamp").reset_index(drop=True)
        return [(float(t), float(c)) for t, c in zip(df["timestamp"], df["current"])]

    def _get_throttle_stream(
        self, flight: Flight
    ) -> list[tuple[float, float]] | None:
        """Return [(timestamp, throttle_frac_0_1), ...] derived from motors or rc_input.

        Tries ``flight.motors`` first (average motor output across motor columns),
        then falls back to ``flight.rc_input`` throttle channel. Returns None if
        neither is available.
        """
        # Try motors DataFrame — average of motor_{i} columns
        motors = getattr(flight, "motors", None)
        if (
            isinstance(motors, pd.DataFrame)
            and not motors.empty
            and "timestamp" in motors.columns
        ):
            motor_cols = [c for c in motors.columns if c.startswith("motor_")]
            if motor_cols:
                df = motors[["timestamp", *motor_cols]].dropna()
                if not df.empty:
                    df = df.sort_values("timestamp").reset_index(drop=True)
                    avg = df[motor_cols].mean(axis=1)
                    return [
                        (float(t), float(v))
                        for t, v in zip(df["timestamp"], avg)
                    ]

        # Fallback: rc_input throttle channel
        rc = getattr(flight, "rc_input", None)
        if (
            isinstance(rc, pd.DataFrame)
            and not rc.empty
            and "timestamp" in rc.columns
        ):
            for col in ("throttle", "throttle_pct", "channel_2", "ch2"):
                if col in rc.columns:
                    df = rc[["timestamp", col]].dropna()
                    if df.empty:
                        continue
                    df = df.sort_values("timestamp").reset_index(drop=True)
                    return [
                        (float(t), float(v))
                        for t, v in zip(df["timestamp"], df[col])
                    ]

        return None

    # ------------------------------------------------------------------
    # Detection primitives
    # ------------------------------------------------------------------

    def _find_candidate_windows(
        self,
        times: list[float],
        currents: list[float],
        delta_threshold: float,
        sustained_s: float,
        pre_post_s: float,
    ) -> list[dict[str, Any]]:
        """Find windows where current changes > delta_threshold and stays changed.

        Returns a list of dicts with keys:
            start_time, end_time, delta_amps, pre_avg, post_avg, duration_s
        """
        candidates: list[dict[str, Any]] = []
        n = len(times)
        if n < 4:
            return candidates

        total_dt = times[-1] - times[0]
        if total_dt <= 0:
            return candidates

        avg_dt = total_dt / max(1, n - 1)
        window_points = max(3, int(sustained_s / max(0.01, avg_dt)))

        if n <= window_points * 2:
            return candidates

        last_range = (n - window_points * 2) - 1
        if last_range <= 0:
            return candidates

        for i in range(last_range):
            pre_start = max(0, i - window_points)
            pre_slice = currents[pre_start : i + 1]
            if not pre_slice:
                continue
            pre_avg = sum(pre_slice) / len(pre_slice)

            post_end = min(n, i + window_points * 2)
            post_slice = currents[i + window_points : post_end]
            if not post_slice:
                continue
            post_avg = sum(post_slice) / len(post_slice)

            delta = post_avg - pre_avg
            if abs(delta) < delta_threshold:
                continue

            event_start = times[i]
            end_idx = min(i + window_points, n - 1)
            event_end = times[end_idx]
            duration = event_end - event_start
            if duration < sustained_s:
                continue

            new_cand = {
                "start_time": event_start,
                "end_time": event_end,
                "delta_amps": delta,
                "pre_avg": pre_avg,
                "post_avg": post_avg,
                "duration_s": duration,
            }

            # De-duplicate: keep larger magnitude candidate within 10s cluster
            if candidates and (event_start - candidates[-1]["start_time"]) < 10.0:
                if abs(delta) > abs(candidates[-1]["delta_amps"]):
                    candidates[-1] = new_cand
            else:
                candidates.append(new_cand)

        return candidates

    def _throttle_explains_change(
        self,
        throttle_stream: list[tuple[float, float]],
        start_time: float,
        end_time: float,
        delta_amps: float,
        tolerance: float,
    ) -> bool:
        """Return True if throttle changed by > tolerance near the event window.

        We consider the throttle to "explain" the current change if the mean
        throttle within 5 seconds before the event differs from the mean within
        5 seconds after the event by more than ``tolerance``. This is a coarse
        Phase 1 filter; Phase 2 will do tighter correlation.
        """
        before = [v for t, v in throttle_stream if start_time - 5.0 < t < start_time]
        after = [v for t, v in throttle_stream if end_time < t < end_time + 5.0]
        if not before or not after:
            return False

        throttle_delta = (sum(after) / len(after)) - (sum(before) / len(before))
        return abs(throttle_delta) > tolerance


plugin = PayloadChangeDetectionPlugin()
