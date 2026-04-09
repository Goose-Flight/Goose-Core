"""Tuning profile system for Goose-Core.

Advanced Forensic Validation Sprint — Named, versioned collections of
analyzer configurations with threshold provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ThresholdSet:
    """Named collection of threshold values for one or more plugins."""

    threshold_set_id: str
    name: str
    description: str
    values: dict[str, float | int | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold_set_id": self.threshold_set_id,
            "name": self.name,
            "description": self.description,
            "values": self.values,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ThresholdSet:
        known = {"threshold_set_id", "name", "description", "values"}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class AnalyzerConfigProfile:
    """Configuration for a specific analyzer/plugin."""

    plugin_id: str
    config_schema_version: str = "1.0"
    thresholds: ThresholdSet | None = None
    enabled: bool = True
    extra_params: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "config_schema_version": self.config_schema_version,
            "thresholds": self.thresholds.to_dict() if self.thresholds else None,
            "enabled": self.enabled,
            "extra_params": self.extra_params,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnalyzerConfigProfile:
        d = dict(d)
        ts = d.get("thresholds")
        d["thresholds"] = ThresholdSet.from_dict(ts) if ts else None
        known = {"plugin_id", "config_schema_version", "thresholds", "enabled", "extra_params"}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class TuningProfile:
    """A named, versioned collection of analyzer configs."""

    profile_id: str
    name: str
    version: str
    description: str
    created_at: str
    is_default: bool = True
    target_vehicle_class: str = "all"
    target_log_type: str = "all"
    analyzer_configs: list[AnalyzerConfigProfile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "created_at": self.created_at,
            "is_default": self.is_default,
            "target_vehicle_class": self.target_vehicle_class,
            "target_log_type": self.target_log_type,
            "analyzer_configs": [c.to_dict() for c in self.analyzer_configs],
        }

    def get_config_for_plugin(self, plugin_id: str) -> AnalyzerConfigProfile | None:
        """Return the config for a specific plugin, or None."""
        for cfg in self.analyzer_configs:
            if cfg.plugin_id == plugin_id:
                return cfg
        return None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuningProfile:
        d = dict(d)
        d["analyzer_configs"] = [
            AnalyzerConfigProfile.from_dict(c) for c in d.get("analyzer_configs", [])
        ]
        known = {
            "profile_id", "name", "version", "description", "created_at",
            "is_default", "target_vehicle_class", "target_log_type",
            "analyzer_configs",
        }
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def default(cls) -> TuningProfile:
        """Return the default tuning profile with all 11 plugin configs."""
        return TuningProfile(
            profile_id="default",
            name="Default",
            version="1.0.0",
            description="Default tuning profile with factory thresholds for all 11 builtin analyzers",
            created_at=datetime.now().isoformat(),
            is_default=True,
            target_vehicle_class="all",
            target_log_type="all",
            analyzer_configs=_build_default_configs(),
        )


def _build_default_configs() -> list[AnalyzerConfigProfile]:
    """Build AnalyzerConfigProfile for each of the 11 builtin plugins.

    Thresholds are extracted from each plugin's source-level constants.
    """
    return [
        AnalyzerConfigProfile(
            plugin_id="crash_detection",
            thresholds=ThresholdSet(
                threshold_set_id="crash_detection_default",
                name="crash_detection defaults",
                description="Default crash detection thresholds",
                values={
                    "descent_rate_threshold": 5.0,
                    "descent_sustained_sec": 1.0,
                    "attitude_divergence_deg": 30.0,
                    "attitude_divergence_sec": 2.0,
                    "impact_accel_g": 3.0,
                    "motor_drop_threshold": 0.05,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="vibration",
            thresholds=ThresholdSet(
                threshold_set_id="vibration_default",
                name="vibration defaults",
                description="PX4 vibration thresholds",
                values={
                    "vibration_good_ms2": 15.0,
                    "vibration_warning_ms2": 30.0,
                    "forward_flight_factor": 1.3,
                    "clipping_threshold_ms2": 156.0,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="battery_sag",
            thresholds=ThresholdSet(
                threshold_set_id="battery_sag_default",
                name="battery_sag defaults",
                description="4S LiPo battery voltage thresholds",
                values={
                    "cell_count": 4,
                    "warn_voltage_per_cell": 3.5,
                    "crit_voltage_per_cell": 3.3,
                    "min_remaining_pct": 20.0,
                    "current_spike_threshold_a": 10.0,
                    "sag_drop_threshold_v": 0.5,
                    "sudden_drop_volts": 0.5,
                    "sudden_drop_window_sec": 2.0,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="gps_health",
            thresholds=ThresholdSet(
                threshold_set_id="gps_health_default",
                name="gps_health defaults",
                description="GPS satellite and accuracy thresholds",
                values={
                    "min_satellites": 8,
                    "max_hdop": 2.0,
                    "position_jump_meters": 5.0,
                    "dropout_gap_sec": 2.0,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="motor_saturation",
            thresholds=ThresholdSet(
                threshold_set_id="motor_saturation_default",
                name="motor_saturation defaults",
                description="Motor output saturation and imbalance thresholds",
                values={
                    "saturation_threshold": 0.95,
                    "imbalance_threshold": 0.15,
                    "sustained_saturation_sec": 3.0,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="ekf_consistency",
            thresholds=ThresholdSet(
                threshold_set_id="ekf_consistency_default",
                name="ekf_consistency defaults",
                description="EKF innovation ratio thresholds",
                values={
                    "innovation_warning": 0.8,
                    "innovation_critical": 1.0,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="rc_signal",
            thresholds=ThresholdSet(
                threshold_set_id="rc_signal_default",
                name="rc_signal defaults",
                description="RC signal RSSI thresholds",
                values={
                    "rssi_warning_pct": 70.0,
                    "rssi_critical_pct": 50.0,
                    "dropout_gap_sec": 2.0,
                    "stuck_channel_sec": 10.0,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="attitude_tracking",
            thresholds=ThresholdSet(
                threshold_set_id="attitude_tracking_default",
                name="attitude_tracking defaults",
                description="Attitude tracking error thresholds",
                values={
                    "tracking_error_warning_deg": 5.0,
                    "tracking_error_critical_deg": 15.0,
                    "oscillation_sign_changes_per_sec": 2.0,
                    "merge_tolerance_sec": 0.05,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="position_tracking",
            thresholds=ThresholdSet(
                threshold_set_id="position_tracking_default",
                name="position_tracking defaults",
                description="Position tracking error and hover drift thresholds",
                values={
                    "warn_mean_error_m": 3.0,
                    "critical_mean_error_m": 10.0,
                    "warn_vert_error_m": 2.0,
                    "critical_vert_error_m": 5.0,
                    "hover_drift_m": 1.0,
                    "low_velocity_threshold_ms": 0.5,
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="failsafe_events",
            thresholds=ThresholdSet(
                threshold_set_id="failsafe_events_default",
                name="failsafe_events defaults",
                description="Failsafe event detection (no numeric thresholds; mode lists)",
                values={
                    "emergency_modes": "rtl,return,land,emergency,failsafe,parachute,termination",
                },
            ),
        ),
        AnalyzerConfigProfile(
            plugin_id="log_health",
            thresholds=ThresholdSet(
                threshold_set_id="log_health_default",
                name="log_health defaults",
                description="Log health and completeness thresholds",
                values={
                    "dropout_gap_sec": 1.0,
                    "min_data_rate_hz": 1.0,
                    "duration_tolerance_sec": 5.0,
                },
            ),
        ),
    ]


# Module-level default profile instance
DEFAULT_TUNING_PROFILE = TuningProfile.default()
