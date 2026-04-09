"""Crash detection plugin — detects and classifies drone crashes from flight data."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightPhase
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# Crash classification types
CRASH_TYPES = (
    "motor_failure",
    "power_loss",
    "gps_loss",
    "pilot_error",
    "mechanical",
    "unknown",
)


def _descent_rate(position: pd.DataFrame, window_sec: float = 1.0) -> pd.Series:
    """Compute descent rate (m/s, positive = descending) over a rolling window."""
    alt_col = "alt_rel" if "alt_rel" in position.columns else "alt_msl"
    if alt_col not in position.columns:
        return pd.Series(dtype=float)
    dt = position["timestamp"].diff()
    dalt = -position[alt_col].diff()  # negative diff = descending, flip sign
    rate = dalt / dt
    # Rolling mean over ~window_sec samples
    samples = max(1, int(window_sec / dt.median())) if dt.median() > 0 else 1
    return rate.rolling(samples, min_periods=1).mean()


def _attitude_divergence(
    attitude: pd.DataFrame,
    attitude_sp: pd.DataFrame,
) -> pd.DataFrame | None:
    """Compute attitude error between actual and setpoint in degrees."""
    if attitude.empty or attitude_sp.empty:
        return None
    # Merge on nearest timestamp
    merged = pd.merge_asof(
        attitude.sort_values("timestamp"),
        attitude_sp.sort_values("timestamp"),
        on="timestamp",
        suffixes=("", "_sp"),
        direction="nearest",
        tolerance=0.5,
    )
    if merged.empty:
        return None
    result = pd.DataFrame()
    result["timestamp"] = merged["timestamp"]
    for axis in ("roll", "pitch"):
        if axis in merged.columns and f"{axis}_sp" in merged.columns:
            result[f"{axis}_error_deg"] = np.degrees(
                np.abs(merged[axis] - merged[f"{axis}_sp"])
            )
    return result


class CrashDetectionPlugin(Plugin):
    """Detect and classify drone crashes from flight log data."""

    name = "crash_detection"
    description = "Detects crashes via altitude loss, attitude divergence, motor failure, and impact signatures"
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="crash_detection",
        name="Crash Detection",
        version="1.0.0",
        author="Goose Flight",
        description="Detects crashes via altitude loss, attitude divergence, motor failure, and impact signatures",
        category=PluginCategory.CRASH,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["position"],
        optional_streams=["attitude", "attitude_setpoint", "motors", "vibration"],
        output_finding_types=["crash_detected", "altitude_loss", "attitude_divergence", "motor_failure", "impact"],
        primary_stream="position",
    )

    # Configurable thresholds (overridable via config dict)
    DEFAULT_CONFIG: dict[str, Any] = {
        "descent_rate_threshold": 5.0,  # m/s sustained descent
        "descent_sustained_sec": 1.0,  # seconds of sustained descent
        "attitude_divergence_deg": 30.0,  # degrees from setpoint
        "attitude_divergence_sec": 2.0,  # max time for divergence to count
        "impact_accel_g": 3.0,  # g-force spike threshold
        "motor_drop_threshold": 0.05,  # output below this = "off"
    }

    # Convenience default constants (for tuning profile parity tests)
    DEFAULT_DESCENT_RATE_THRESHOLD = 5.0
    DEFAULT_DESCENT_SUSTAINED_SEC = 1.0
    DEFAULT_ATTITUDE_DIVERGENCE_DEG = 30.0
    DEFAULT_ATTITUDE_DIVERGENCE_SEC = 2.0
    DEFAULT_IMPACT_ACCEL_G = 3.0
    DEFAULT_MOTOR_DROP_THRESHOLD = 0.05

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run crash detection analysis. Returns findings with crash classification."""
        cfg = {**self.DEFAULT_CONFIG, **config}
        findings: list[Finding] = []

        crash_signals: list[dict[str, Any]] = []

        # 1. Rapid altitude loss
        alt_signal = self._check_altitude_loss(flight, cfg)
        if alt_signal:
            crash_signals.append(alt_signal)

        # 2. Attitude divergence
        att_signal = self._check_attitude_divergence(flight, cfg)
        if att_signal:
            crash_signals.append(att_signal)

        # 3. Motor output drop (single motor while others run)
        motor_signal = self._check_motor_failure(flight, cfg)
        if motor_signal:
            crash_signals.append(motor_signal)

        # 4. Impact signature (high-g spike)
        impact_signal = self._check_impact(flight, cfg)
        if impact_signal:
            crash_signals.append(impact_signal)

        # 5. Abrupt flight termination (takeoff immediately followed by landing)
        abort_signal = self._check_abrupt_termination(flight)
        if abort_signal:
            crash_signals.append(abort_signal)

        if not crash_signals:
            findings.append(Finding(
                plugin_name=self.name,
                title="No crash detected",
                severity="pass",
                score=100,
                description="Flight completed without crash indicators.",
            ))
            return findings

        # Classify the crash
        classification = self._classify(crash_signals, flight)
        confidence = self._compute_confidence(crash_signals)
        timeline = self._build_timeline(crash_signals)

        evidence: dict[str, Any] = {
            "crash_type": classification,
            "confidence": round(confidence, 2),
            "timeline": timeline,
            "signals": [s["type"] for s in crash_signals],
            "root_cause_chain": self._root_cause_chain(classification, crash_signals),
        }

        # Determine severity based on confidence
        if confidence >= 0.7:
            severity = "critical"
            score = 0
        elif confidence >= 0.4:
            severity = "warning"
            score = 25
        else:
            severity = "warning"
            score = 50

        earliest_ts = min(
            (s.get("timestamp_start", float("inf")) for s in crash_signals),
            default=None,
        )
        latest_ts = max(
            (s.get("timestamp_end", 0.0) for s in crash_signals),
            default=None,
        )

        findings.append(Finding(
            plugin_name=self.name,
            title=f"Crash detected: {classification}",
            severity=severity,
            score=score,
            description=(
                f"Crash classified as '{classification}' with {confidence:.0%} confidence. "
                f"Signals: {', '.join(s['type'] for s in crash_signals)}."
            ),
            evidence=evidence,
            timestamp_start=earliest_ts if earliest_ts != float("inf") else None,
            timestamp_end=latest_ts if latest_ts else None,
        ))

        # Add individual signal findings
        for signal in crash_signals:
            findings.append(Finding(
                plugin_name=self.name,
                title=signal["title"],
                severity="warning",
                score=signal.get("score", 30),
                description=signal["description"],
                evidence=signal.get("evidence", {}),
                timestamp_start=signal.get("timestamp_start"),
                timestamp_end=signal.get("timestamp_end"),
            ))

        return findings

    def _check_altitude_loss(
        self, flight: Flight, cfg: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Detect rapid sustained altitude loss (>threshold m/s for >duration)."""
        if flight.position.empty or len(flight.position) < 20:
            return None

        rate = _descent_rate(flight.position, window_sec=cfg["descent_sustained_sec"])
        if rate.empty:
            return None

        threshold = cfg["descent_rate_threshold"]
        sustained_sec = cfg["descent_sustained_sec"]

        # Find runs of rapid descent
        fast_descent = rate > threshold
        if not fast_descent.any():
            return None

        # Check if any run lasts longer than sustained_sec
        timestamps = flight.position["timestamp"]
        in_run = False
        run_start = 0.0
        for i in range(len(fast_descent)):
            if fast_descent.iloc[i]:
                if not in_run:
                    in_run = True
                    run_start = timestamps.iloc[i]
            else:
                if in_run:
                    run_duration = timestamps.iloc[i] - run_start
                    if run_duration >= sustained_sec:
                        max_rate = float(rate.iloc[max(0, i - int(run_duration)):i].max())
                        return {
                            "type": "altitude_loss",
                            "title": f"Rapid altitude loss at {max_rate:.1f} m/s",
                            "description": (
                                f"Sustained descent of >{threshold} m/s detected for "
                                f"{run_duration:.1f}s (peak {max_rate:.1f} m/s)."
                            ),
                            "score": 15,
                            "evidence": {
                                "max_descent_rate": max_rate,
                                "duration_sec": round(run_duration, 2),
                            },
                            "timestamp_start": run_start,
                            "timestamp_end": timestamps.iloc[i],
                        }
                    in_run = False

        # Check if still in a run at end of data
        if in_run:
            run_duration = timestamps.iloc[-1] - run_start
            if run_duration >= sustained_sec:
                max_rate = float(rate.iloc[-max(1, int(run_duration)):].max())
                return {
                    "type": "altitude_loss",
                    "title": f"Rapid altitude loss at {max_rate:.1f} m/s",
                    "description": (
                        f"Sustained descent of >{threshold} m/s detected for "
                        f"{run_duration:.1f}s until end of log (peak {max_rate:.1f} m/s)."
                    ),
                    "score": 10,
                    "evidence": {
                        "max_descent_rate": max_rate,
                        "duration_sec": round(run_duration, 2),
                        "end_of_log": True,
                    },
                    "timestamp_start": run_start,
                    "timestamp_end": float(timestamps.iloc[-1]),
                }

        return None

    def _check_attitude_divergence(
        self, flight: Flight, cfg: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Detect sudden attitude divergence from setpoint."""
        if not flight.has_attitude_setpoints:
            return None

        div = _attitude_divergence(flight.attitude, flight.attitude_setpoint)
        if div is None or div.empty:
            return None

        threshold_deg = cfg["attitude_divergence_deg"]
        max_sec = cfg["attitude_divergence_sec"]

        for axis in ("roll", "pitch"):
            err_col = f"{axis}_error_deg"
            if err_col not in div.columns:
                continue
            # Find where error exceeds threshold
            exceeded = div[div[err_col] > threshold_deg]
            if exceeded.empty:
                continue

            # Check if the divergence happened rapidly (within max_sec)
            first_exceed = exceeded["timestamp"].iloc[0]
            # Look back to find when error started growing
            before = div[div["timestamp"] < first_exceed]
            if not before.empty:
                normal = before[before[err_col] < threshold_deg / 2]
                if not normal.empty:
                    onset = normal["timestamp"].iloc[-1]
                    ramp_time = first_exceed - onset
                    if ramp_time <= max_sec:
                        peak_error = float(exceeded[err_col].max())
                        return {
                            "type": "attitude_divergence",
                            "title": f"Sudden {axis} divergence: {peak_error:.0f} deg",
                            "description": (
                                f"{axis.title()} diverged >{threshold_deg} deg from setpoint "
                                f"in {ramp_time:.1f}s (peak {peak_error:.0f} deg)."
                            ),
                            "score": 20,
                            "evidence": {
                                "axis": axis,
                                "peak_error_deg": round(peak_error, 1),
                                "ramp_time_sec": round(ramp_time, 2),
                            },
                            "timestamp_start": onset,
                            "timestamp_end": float(exceeded["timestamp"].iloc[-1]),
                        }

        return None

    def _check_motor_failure(
        self, flight: Flight, cfg: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Detect motor output dropping to zero while others remain active."""
        if flight.motors.empty:
            return None

        motor_cols = [c for c in flight.motors.columns if c.startswith("output_")]
        if not motor_cols:
            return None

        threshold = cfg["motor_drop_threshold"]
        timestamps = flight.motors["timestamp"]

        # Skip first 10% (startup) and check for any motor dropping while others run
        start_idx = max(1, len(timestamps) // 10)

        for i in range(start_idx, len(timestamps)):
            outputs = [float(flight.motors[c].iloc[i]) for c in motor_cols]
            active = [o for o in outputs if o > threshold]
            dead = [j for j, o in enumerate(outputs) if o <= threshold]

            if dead and len(active) >= len(motor_cols) // 2:
                # At least one motor dead while majority still running
                return {
                    "type": "motor_failure",
                    "title": f"Motor {dead[0]} output dropped to zero",
                    "description": (
                        f"Motor(s) {dead} output fell below {threshold} "
                        f"while {len(active)} motors remained active."
                    ),
                    "score": 10,
                    "evidence": {
                        "failed_motors": dead,
                        "active_motors": len(active),
                        "outputs_at_failure": {
                            motor_cols[j]: round(outputs[j], 3)
                            for j in range(len(motor_cols))
                        },
                    },
                    "timestamp_start": float(timestamps.iloc[i]),
                    "timestamp_end": float(timestamps.iloc[-1]),
                }

        return None

    def _check_impact(
        self, flight: Flight, cfg: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Detect impact signature: high-g spike followed by data stop or flatline."""
        if flight.vibration.empty:
            return None

        accel_cols = [c for c in flight.vibration.columns if c.startswith("accel_")]
        if not accel_cols:
            return None

        threshold_g = cfg["impact_accel_g"]
        threshold_ms2 = threshold_g * 9.81

        timestamps = flight.vibration["timestamp"]
        total_accel = np.sqrt(sum(
            flight.vibration[c] ** 2 for c in accel_cols
        ))

        spikes = total_accel > threshold_ms2
        if not spikes.any():
            return None

        # Find the last major spike (impact is usually near end)
        spike_indices = np.where(spikes.values)[0]
        last_spike_idx = spike_indices[-1]
        remaining_samples = len(timestamps) - last_spike_idx

        # Impact = spike near end of log (last 20% of data after spike)
        total_samples = len(timestamps)
        if remaining_samples < total_samples * 0.2:
            peak_g = float(total_accel.iloc[last_spike_idx] / 9.81)
            return {
                "type": "impact",
                "title": f"Impact detected: {peak_g:.1f}g spike",
                "description": (
                    f"High-g spike of {peak_g:.1f}g detected near end of log "
                    f"({remaining_samples} samples remaining). "
                    "Consistent with ground impact."
                ),
                "score": 5,
                "evidence": {
                    "peak_g": round(peak_g, 2),
                    "remaining_samples_after": remaining_samples,
                    "pct_remaining": round(remaining_samples / total_samples * 100, 1),
                },
                "timestamp_start": float(timestamps.iloc[last_spike_idx]),
                "timestamp_end": float(timestamps.iloc[-1]),
            }

        return None

    def _check_abrupt_termination(
        self, flight: Flight
    ) -> dict[str, Any] | None:
        """Detect abrupt flight termination: takeoff followed by immediate landing."""
        takeoff_ts: float | None = None
        landing_ts: float | None = None

        for event in flight.events:
            msg = event.message.lower()
            if "takeoff" in msg and takeoff_ts is None:
                takeoff_ts = event.timestamp
            if ("landing" in msg or "disarm" in msg) and takeoff_ts is not None:
                landing_ts = event.timestamp
                break

        if takeoff_ts is None or landing_ts is None:
            return None

        flight_duration = landing_ts - takeoff_ts
        if flight_duration > 10.0:  # only flag very short flights
            return None

        return {
            "type": "abrupt_termination",
            "title": f"Abrupt flight termination after {flight_duration:.1f}s",
            "description": (
                f"Flight lasted only {flight_duration:.1f}s from takeoff to landing. "
                "Possible in-flight failure, safety landing, or crash."
            ),
            "score": 20,
            "evidence": {
                "takeoff_timestamp": takeoff_ts,
                "landing_timestamp": landing_ts,
                "flight_duration_sec": round(flight_duration, 2),
            },
            "timestamp_start": takeoff_ts,
            "timestamp_end": landing_ts,
        }

    def _classify(
        self, signals: list[dict[str, Any]], flight: Flight
    ) -> str:
        """Classify the crash type based on detected signals."""
        signal_types = {s["type"] for s in signals}

        if "motor_failure" in signal_types:
            return "motor_failure"


        # Power loss: altitude drop + no motor output at all near end
        if "altitude_loss" in signal_types and not flight.motors.empty:
            motor_cols = [c for c in flight.motors.columns if c.startswith("output_")]
            if motor_cols:
                tail = flight.motors.tail(10)
                avg_output = sum(tail[c].mean() for c in motor_cols) / len(motor_cols)
                if avg_output < 0.05:
                    return "power_loss"

        # GPS loss check: if events mention GPS
        for event in flight.events:
            if "gps" in event.message.lower() and event.severity in ("critical", "warning"):
                if "altitude_loss" in signal_types:
                    return "gps_loss"

        if "attitude_divergence" in signal_types:
            return "mechanical"

        if "altitude_loss" in signal_types or "impact" in signal_types:
            return "unknown"

        return "unknown"

    def _compute_confidence(self, signals: list[dict[str, Any]]) -> float:
        """Compute crash confidence from 0.0 to 1.0 based on signal count and strength."""
        if not signals:
            return 0.0

        # Each signal type adds confidence
        weights: dict[str, float] = {
            "altitude_loss": 0.3,
            "attitude_divergence": 0.25,
            "motor_failure": 0.35,
            "impact": 0.3,

            "abrupt_termination": 0.3,
        }

        total = sum(weights.get(s["type"], 0.1) for s in signals)
        return min(1.0, total)

    def _build_timeline(self, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build a chronological crash timeline from signals."""
        events = []
        for s in signals:
            ts = s.get("timestamp_start")
            if ts is not None:
                events.append({
                    "timestamp": ts,
                    "event": s["type"],
                    "detail": s["title"],
                })
        return sorted(events, key=lambda e: e["timestamp"])

    def _root_cause_chain(
        self, classification: str, signals: list[dict[str, Any]]
    ) -> list[str]:
        """Build probable root cause chain for the crash."""
        chain: list[str] = []

        if classification == "motor_failure":
            chain.append("Motor output anomaly detected")
            if any(s["type"] == "attitude_divergence" for s in signals):
                chain.append("Vehicle lost attitude control")
            chain.append("Uncontrolled descent")
        elif classification == "power_loss":
            chain.append("All motor outputs dropped simultaneously")
            chain.append("Probable battery disconnection or ESC failure")
            chain.append("Freefall descent")
        elif classification == "gps_loss":
            chain.append("GPS signal degradation or loss")
            chain.append("Position estimation failure")
            chain.append("Uncontrolled flight path")
        elif classification == "mechanical":
            chain.append("Attitude divergence from setpoint")
            chain.append("Probable mechanical failure (prop, arm, frame)")
            chain.append("Loss of control authority")
        else:
            chain.append("Anomalous flight data detected")
            chain.append("Multiple failure indicators present")

        if any(s["type"] == "impact" for s in signals):
            chain.append("Ground impact confirmed by accelerometer spike")

        return chain
