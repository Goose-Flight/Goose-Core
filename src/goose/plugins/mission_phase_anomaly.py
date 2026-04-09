"""Mission phase anomaly plugin — detects anomalies in specific flight phases.

Analyzes flight data split by detected flight phase (takeoff, climb, cruise,
approach, landing) and emits findings when anomaly signatures are concentrated
in a specific phase. This provides phase-level context that helps investigators
narrow the search window.

Design rules:
- Only emits findings when phase information is available (Flight.phases).
  Degrades gracefully to no findings if phase data is absent.
- Does NOT duplicate checks from other plugins (crash_detection, battery_sag,
  etc.) — it adds phase label context to multi-plugin findings.
- Emits ForensicFinding with phase label and timing so timeline events and
  hypothesis themes carry the right temporal framing.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightPhase
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# Thresholds
DEFAULT_ALTITUDE_LOSS_RATE = 3.0       # m/s — descent rate considered anomalous per phase
DEFAULT_BATTERY_DROP_RATE = 0.5        # %/sec — battery drain rate considered anomalous
DEFAULT_PHASE_VIBRATION_RATIO = 2.0    # factor above whole-flight baseline = anomalous
DEFAULT_SHORT_PHASE_SEC = 5.0          # phase shorter than this = suspiciously short


class MissionPhaseAnomalyPlugin(Plugin):
    """Detect anomalies correlated with specific flight phases.

    When flight phase information is available, this plugin checks whether
    key metrics (altitude stability, battery drain, vibration) are anomalous
    within individual phases. Phase-localized anomalies are stronger evidence
    than whole-flight averages.
    """

    name = "mission_phase_anomaly"
    description = (
        "Detects anomalies in specific flight phases (takeoff, climb, cruise, landing). "
        "Provides phase-level temporal context for forensic investigation."
    )
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="mission_phase_anomaly",
        name="Mission Phase Anomaly",
        version="1.0.0",
        author="Goose Flight",
        description=(
            "Detects anomalies in specific flight phases (takeoff, climb, cruise, landing). "
            "Provides phase-level temporal context for forensic investigation."
        ),
        category=PluginCategory.FLIGHT_DYNAMICS,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["position"],
        optional_streams=["battery", "vibration", "attitude"],
        output_finding_types=[
            "phase_altitude_anomaly",
            "phase_battery_anomaly",
            "phase_vibration_spike",
            "phase_too_short",
        ],
        primary_stream="position",
    )

    DEFAULT_ALTITUDE_LOSS_RATE = DEFAULT_ALTITUDE_LOSS_RATE
    DEFAULT_BATTERY_DROP_RATE = DEFAULT_BATTERY_DROP_RATE
    DEFAULT_PHASE_VIBRATION_RATIO = DEFAULT_PHASE_VIBRATION_RATIO
    DEFAULT_SHORT_PHASE_SEC = DEFAULT_SHORT_PHASE_SEC

    DEFAULT_CONFIG: dict[str, Any] = {
        "altitude_loss_rate": DEFAULT_ALTITUDE_LOSS_RATE,
        "battery_drop_rate": DEFAULT_BATTERY_DROP_RATE,
        "phase_vibration_ratio": DEFAULT_PHASE_VIBRATION_RATIO,
        "short_phase_sec": DEFAULT_SHORT_PHASE_SEC,
    }

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        cfg = {**self.DEFAULT_CONFIG, **config}
        findings: list[Finding] = []

        phases = getattr(flight, "phases", []) or []
        if not phases:
            # No phase data — emit an info finding and return
            findings.append(Finding(
                plugin_name=self.name,
                title="Flight phase data unavailable",
                severity="info",
                score=50,
                description=(
                    "No flight phase information extracted from this log. "
                    "Phase-anomaly analysis requires flight phase detection data."
                ),
            ))
            return findings

        # Run per-phase checks
        for phase in phases:
            phase_type = getattr(phase, "phase_type", "unknown")
            t_start = float(getattr(phase, "start_time", 0.0) or 0.0)
            t_end = float(getattr(phase, "end_time", 0.0) or 0.0)
            phase_dur = t_end - t_start

            # 1. Suspiciously short phases
            if 0 < phase_dur < cfg["short_phase_sec"]:
                findings.append(Finding(
                    plugin_name=self.name,
                    title=f"Phase '{phase_type}' unusually short ({phase_dur:.1f}s)",
                    severity="warning",
                    score=55,
                    description=(
                        f"The '{phase_type}' phase lasted only {phase_dur:.1f}s — "
                        f"shorter than the expected minimum of {cfg['short_phase_sec']}s. "
                        "This may indicate an aborted maneuver, a failsafe trigger, or a logging gap."
                    ),
                    evidence={
                        "phase": phase_type,
                        "duration_sec": round(phase_dur, 2),
                        "threshold_sec": cfg["short_phase_sec"],
                    },
                    phase=phase_type,
                    timestamp_start=t_start,
                    timestamp_end=t_end,
                ))

            # 2. Phase-specific altitude anomaly
            alt_finding = self._check_phase_altitude(flight, phase_type, t_start, t_end, cfg)
            if alt_finding:
                findings.append(alt_finding)

            # 3. Phase-specific battery anomaly
            bat_finding = self._check_phase_battery(flight, phase_type, t_start, t_end, cfg)
            if bat_finding:
                findings.append(bat_finding)

            # 4. Phase-specific vibration spike
            vib_finding = self._check_phase_vibration(flight, phase_type, t_start, t_end, cfg)
            if vib_finding:
                findings.append(vib_finding)

        if not findings:
            findings.append(Finding(
                plugin_name=self.name,
                title="No phase-specific anomalies detected",
                severity="pass",
                score=95,
                description=(
                    f"Checked {len(phases)} flight phase(s). "
                    "No phase-localized anomalies found above threshold."
                ),
            ))

        return findings

    def _check_phase_altitude(
        self,
        flight: Flight,
        phase_type: str,
        t_start: float,
        t_end: float,
        cfg: dict[str, Any],
    ) -> Finding | None:
        """Check for anomalous altitude loss within a specific phase."""
        if flight.position.empty or "timestamp" not in flight.position.columns:
            return None

        mask = (flight.position["timestamp"] >= t_start) & (flight.position["timestamp"] <= t_end)
        phase_pos = flight.position[mask]
        if len(phase_pos) < 5:
            return None

        alt_col = "alt_rel" if "alt_rel" in phase_pos.columns else "alt_msl"
        if alt_col not in phase_pos.columns:
            return None

        alt = phase_pos[alt_col].dropna()
        ts = phase_pos["timestamp"][alt.index]
        if len(alt) < 2:
            return None

        dt = float(ts.iloc[-1] - ts.iloc[0])
        if dt < 0.5:
            return None

        alt_change = float(alt.iloc[-1] - alt.iloc[0])  # negative = descent
        rate = -alt_change / dt  # positive = descending

        threshold = cfg["altitude_loss_rate"]

        # Flag descent during phases where we expect stability or climb
        anomalous_descent_phases = {"cruise", "on_mission", "hold", "loiter", "hover"}
        is_anomalous = (
            rate > threshold
            and phase_type.lower() in anomalous_descent_phases
        )

        # Also flag if landing is steeper than expected
        if phase_type.lower() in ("landing", "descent") and rate > threshold * 2:
            is_anomalous = True

        if not is_anomalous:
            return None

        return Finding(
            plugin_name=self.name,
            title=f"Altitude loss during '{phase_type}' phase ({rate:.1f} m/s)",
            severity="warning",
            score=40,
            description=(
                f"Altitude decreased at {rate:.1f} m/s during the '{phase_type}' phase "
                f"({dt:.1f}s window). Expected: stable or climbing. "
                f"Threshold: >{threshold} m/s."
            ),
            evidence={
                "phase": phase_type,
                "descent_rate_ms": round(rate, 2),
                "altitude_change_m": round(alt_change, 2),
                "window_sec": round(dt, 2),
                "threshold_ms": threshold,
            },
            phase=phase_type,
            timestamp_start=t_start,
            timestamp_end=t_end,
        )

    def _check_phase_battery(
        self,
        flight: Flight,
        phase_type: str,
        t_start: float,
        t_end: float,
        cfg: dict[str, Any],
    ) -> Finding | None:
        """Check for anomalous battery drain within a specific phase."""
        if flight.battery.empty or "timestamp" not in flight.battery.columns:
            return None
        if "remaining_pct" not in flight.battery.columns:
            return None

        mask = (flight.battery["timestamp"] >= t_start) & (flight.battery["timestamp"] <= t_end)
        phase_bat = flight.battery[mask]
        if len(phase_bat) < 3:
            return None

        pct = phase_bat["remaining_pct"].dropna()
        ts = phase_bat["timestamp"][pct.index]
        if len(pct) < 2:
            return None

        dt = float(ts.iloc[-1] - ts.iloc[0])
        if dt < 1.0:
            return None

        pct_drop = float(pct.iloc[0] - pct.iloc[-1])  # positive = drained
        drain_rate = pct_drop / dt  # %/sec

        threshold = cfg["battery_drop_rate"]
        if drain_rate <= threshold:
            return None

        return Finding(
            plugin_name=self.name,
            title=f"High battery drain during '{phase_type}' phase ({drain_rate:.2f}%/s)",
            severity="warning",
            score=45,
            description=(
                f"Battery drained at {drain_rate:.2f}%/s during the '{phase_type}' phase "
                f"({pct_drop:.1f}% over {dt:.1f}s). "
                f"This is above the {threshold}%/s threshold."
            ),
            evidence={
                "phase": phase_type,
                "drain_rate_pct_per_sec": round(drain_rate, 3),
                "total_pct_drop": round(pct_drop, 2),
                "window_sec": round(dt, 2),
                "threshold": threshold,
            },
            phase=phase_type,
            timestamp_start=t_start,
            timestamp_end=t_end,
        )

    def _check_phase_vibration(
        self,
        flight: Flight,
        phase_type: str,
        t_start: float,
        t_end: float,
        cfg: dict[str, Any],
    ) -> Finding | None:
        """Detect vibration spikes relative to whole-flight baseline in a phase."""
        if flight.vibration.empty or "timestamp" not in flight.vibration.columns:
            return None

        accel_cols = [c for c in flight.vibration.columns if c.startswith("accel_")]
        if not accel_cols:
            return None

        # Whole-flight baseline RMS
        total_rms = float(np.sqrt(
            sum((flight.vibration[c] ** 2).mean() for c in accel_cols) / len(accel_cols)
        ))
        if total_rms < 0.1:
            return None

        # Phase window RMS
        mask = (flight.vibration["timestamp"] >= t_start) & (flight.vibration["timestamp"] <= t_end)
        phase_vib = flight.vibration[mask]
        if len(phase_vib) < 5:
            return None

        phase_rms = float(np.sqrt(
            sum((phase_vib[c] ** 2).mean() for c in accel_cols if c in phase_vib.columns) / len(accel_cols)
        ))

        ratio = phase_rms / total_rms if total_rms > 0 else 1.0
        threshold = cfg["phase_vibration_ratio"]

        if ratio <= threshold:
            return None

        return Finding(
            plugin_name=self.name,
            title=f"Vibration spike during '{phase_type}' phase ({ratio:.1f}x baseline)",
            severity="warning",
            score=40,
            description=(
                f"Vibration RMS during the '{phase_type}' phase ({phase_rms:.1f} m/s²) is "
                f"{ratio:.1f}x the whole-flight baseline ({total_rms:.1f} m/s²). "
                f"Threshold: >{threshold}x. Inspect for phase-specific mechanical stress."
            ),
            evidence={
                "phase": phase_type,
                "phase_rms_ms2": round(phase_rms, 2),
                "baseline_rms_ms2": round(total_rms, 2),
                "ratio": round(ratio, 2),
                "threshold": threshold,
            },
            phase=phase_type,
            timestamp_start=t_start,
            timestamp_end=t_end,
        )
