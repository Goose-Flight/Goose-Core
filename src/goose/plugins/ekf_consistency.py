"""EKF consistency plugin — innovation ratio monitoring and filter health checks."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# Innovation ratio thresholds (normalized, unitless)
INNOV_WARNING = 0.8
INNOV_CRITICAL = 1.0

# EKF fault flag column name (may vary by autopilot)
EKF_FAULT_COLS = ["ekf_fault_flags", "solution_status_flags", "filter_fault_flags"]


class EkfConsistencyPlugin(Plugin):
    """Monitor EKF innovation ratios and detect filter health issues."""

    name = "ekf_consistency"
    description = "EKF innovation monitoring and filter health"
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="ekf_consistency",
        name="EKF Consistency",
        version="1.0.0",
        author="Goose Flight",
        description="Monitors EKF innovation ratios and detects filter health issues",
        category=PluginCategory.NAVIGATION,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=["ekf"],
        optional_streams=[],
        output_finding_types=["velocity_innovation", "position_innovation", "ekf_fault_flags"],
    )

    DEFAULT_INNOVATION_WARNING = INNOV_WARNING
    DEFAULT_INNOVATION_CRITICAL = INNOV_CRITICAL

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run EKF health checks. Returns findings."""
        findings: list[Finding] = []
        cfg = config or {}
        warn = float(cfg.get("innovation_warning", INNOV_WARNING))
        crit = float(cfg.get("innovation_critical", INNOV_CRITICAL))

        if flight.ekf is None or flight.ekf.empty:
            findings.append(Finding(
                plugin_name=self.name,
                title="No EKF data available",
                severity="info",
                score=50,
                description="No EKF data found in the flight log. Filter health checks skipped.",
            ))
            return findings

        ekf = flight.ekf.copy()

        findings.extend(self._check_velocity_innovations(ekf, warn, crit))
        findings.extend(self._check_position_innovations(ekf, warn, crit))
        findings.extend(self._check_fault_flags(ekf))

        return findings

    # ------------------------------------------------------------------
    # Velocity innovation ratios
    # ------------------------------------------------------------------

    def _check_velocity_innovations(
        self,
        ekf: pd.DataFrame,
        INNOV_WARNING: float = INNOV_WARNING,
        INNOV_CRITICAL: float = INNOV_CRITICAL,
    ) -> list[Finding]:
        """Check velocity innovation ratio columns vel_innov_x/y/z."""
        vel_cols = {
            "x": "vel_innov_x",
            "y": "vel_innov_y",
            "z": "vel_innov_z",
        }
        available = {axis: col for axis, col in vel_cols.items() if col in ekf.columns}

        if not available:
            return []

        return self._check_innovation_group(
            ekf, available, group="velocity",
            INNOV_WARNING=INNOV_WARNING, INNOV_CRITICAL=INNOV_CRITICAL,
        )

    # ------------------------------------------------------------------
    # Position innovation ratios
    # ------------------------------------------------------------------

    def _check_position_innovations(
        self,
        ekf: pd.DataFrame,
        INNOV_WARNING: float = INNOV_WARNING,
        INNOV_CRITICAL: float = INNOV_CRITICAL,
    ) -> list[Finding]:
        """Check position innovation ratio columns pos_innov_x/y/z."""
        pos_cols = {
            "x": "pos_innov_x",
            "y": "pos_innov_y",
            "z": "pos_innov_z",
        }
        available = {axis: col for axis, col in pos_cols.items() if col in ekf.columns}

        if not available:
            return []

        return self._check_innovation_group(
            ekf, available, group="position",
            INNOV_WARNING=INNOV_WARNING, INNOV_CRITICAL=INNOV_CRITICAL,
        )

    # ------------------------------------------------------------------
    # Shared innovation ratio evaluation
    # ------------------------------------------------------------------

    def _check_innovation_group(
        self,
        ekf: pd.DataFrame,
        cols: dict[str, str],
        group: str,
        INNOV_WARNING: float = INNOV_WARNING,
        INNOV_CRITICAL: float = INNOV_CRITICAL,
    ) -> list[Finding]:
        """Evaluate innovation ratios for a group of axes and return findings."""
        axis_results: dict[str, dict[str, Any]] = {}
        worst = "pass"

        for axis, col in cols.items():
            series = ekf[col].dropna().abs()
            if series.empty:
                continue

            max_ratio = round(float(series.max()), 4)
            mean_ratio = round(float(series.mean()), 4)
            pct_warn = round(float((series > INNOV_WARNING).sum() / len(series) * 100), 2)
            pct_crit = round(float((series > INNOV_CRITICAL).sum() / len(series) * 100), 2)

            if max_ratio >= INNOV_CRITICAL:
                level = "critical"
                worst = "critical"
            elif max_ratio >= INNOV_WARNING:
                level = "warning"
                if worst == "pass":
                    worst = "warning"
            else:
                level = "pass"

            axis_results[axis] = {
                "max_ratio": max_ratio,
                "mean_ratio": mean_ratio,
                "pct_above_warning": pct_warn,
                "pct_above_critical": pct_crit,
                "level": level,
            }

        if not axis_results:
            return []

        if worst == "pass":
            return [Finding(
                plugin_name=self.name,
                title=f"EKF {group} innovations within limits",
                severity="pass",
                score=95,
                description=(
                    f"All {group} innovation ratios remained below the warning threshold of {INNOV_WARNING}."
                ),
                evidence={
                    "group": group,
                    "axes": axis_results,
                    "warning_threshold": INNOV_WARNING,
                    "critical_threshold": INNOV_CRITICAL,
                },
            )]

        if worst == "critical":
            severity = "critical"
            score = 15
            title = f"EKF {group} innovation ratio critical — filter consistency degraded"
            desc = (
                f"One or more {group} innovation ratios exceeded the critical threshold of {INNOV_CRITICAL}. "
                "This indicates the EKF filter is inconsistent with sensor measurements. "
                "Navigation accuracy may be severely compromised."
            )
        else:
            severity = "warning"
            score = 50
            title = f"Elevated EKF {group} innovation ratios detected"
            desc = (
                f"One or more {group} innovation ratios exceeded the warning threshold of {INNOV_WARNING}. "
                "Monitor for further degradation. Check sensor calibration and GPS health."
            )

        # Find earliest timestamp where any axis exceeded warning
        ts_start = None
        if "timestamp" in ekf.columns:
            for col in cols.values():
                if col not in ekf.columns:
                    continue
                exceed_idx = ekf.index[ekf[col].abs() >= INNOV_WARNING]
                if len(exceed_idx):
                    t = float(ekf.loc[exceed_idx[0], "timestamp"])
                    if ts_start is None or t < ts_start:
                        ts_start = t

        return [Finding(
            plugin_name=self.name,
            title=title,
            severity=severity,
            score=score,
            description=desc,
            evidence={
                "group": group,
                "axes": axis_results,
                "warning_threshold": INNOV_WARNING,
                "critical_threshold": INNOV_CRITICAL,
            },
            timestamp_start=ts_start,
        )]

    # ------------------------------------------------------------------
    # EKF fault flag checks
    # ------------------------------------------------------------------

    def _check_fault_flags(self, ekf: pd.DataFrame) -> list[Finding]:
        """Check EKF fault flag columns for any set fault bits."""
        found_col = None
        for col in EKF_FAULT_COLS:
            if col in ekf.columns:
                found_col = col
                break

        if found_col is None:
            return []

        flags = ekf[found_col].dropna()
        if flags.empty:
            return []

        faulted = flags[flags != 0]
        if faulted.empty:
            return [Finding(
                plugin_name=self.name,
                title="No EKF fault flags set",
                severity="pass",
                score=95,
                description=f"EKF fault flag column '{found_col}' showed no fault conditions during flight.",
                evidence={"fault_col": found_col, "fault_count": 0},
            )]

        fault_count = int(len(faulted))
        pct_faulted = round(fault_count / len(flags) * 100, 2)
        unique_flags = sorted(int(v) for v in faulted.unique())

        ts_start = None
        if "timestamp" in ekf.columns:
            fault_idx = ekf.index[ekf[found_col] != 0]
            if len(fault_idx):
                ts_start = float(ekf.loc[fault_idx[0], "timestamp"])

        severity = "critical" if pct_faulted > 5.0 else "warning"
        score = 10 if severity == "critical" else 40

        return [Finding(
            plugin_name=self.name,
            title=f"EKF fault flags active — {fault_count} samples ({pct_faulted}% of flight)",
            severity=severity,
            score=score,
            description=(
                f"EKF reported fault conditions in {fault_count} samples ({pct_faulted}% of flight). "
                f"Unique flag values observed: {unique_flags}. "
                "Fault conditions indicate the filter rejected sensor data or detected inconsistency."
            ),
            evidence={
                "fault_col": found_col,
                "fault_count": fault_count,
                "pct_faulted": pct_faulted,
                "unique_flag_values": unique_flags,
                "total_samples": int(len(flags)),
            },
            timestamp_start=ts_start,
        )]
