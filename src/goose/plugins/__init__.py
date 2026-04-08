"""Analysis plugins for Goose flight log analysis.

Sprint 5: Plugin registry with formal manifests and contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goose.plugins.contract import PluginManifest

if TYPE_CHECKING:
    from goose.plugins.base import Plugin

# Import all plugin classes
from goose.plugins.crash_detection import CrashDetectionPlugin
from goose.plugins.vibration import VibrationPlugin
from goose.plugins.battery_sag import BatterySagPlugin
from goose.plugins.gps_health import GPSHealthPlugin
from goose.plugins.motor_saturation import MotorSaturationPlugin
from goose.plugins.ekf_consistency import EkfConsistencyPlugin
from goose.plugins.rc_signal import RcSignalPlugin
from goose.plugins.attitude_tracking import AttitudeTrackingPlugin
from goose.plugins.position_tracking import PositionTrackingPlugin
from goose.plugins.failsafe_events import FailsafeEventsPlugin
from goose.plugins.log_health import LogHealthPlugin

_PLUGIN_CLASSES: list[type] = [
    CrashDetectionPlugin,
    VibrationPlugin,
    BatterySagPlugin,
    GPSHealthPlugin,
    MotorSaturationPlugin,
    EkfConsistencyPlugin,
    RcSignalPlugin,
    AttitudeTrackingPlugin,
    PositionTrackingPlugin,
    FailsafeEventsPlugin,
    LogHealthPlugin,
]

# Singleton registry: plugin_id -> plugin instance
PLUGIN_REGISTRY: dict[str, Plugin] = {}

for _cls in _PLUGIN_CLASSES:
    _inst = _cls()
    PLUGIN_REGISTRY[_inst.manifest.plugin_id] = _inst


def get_plugin_manifests() -> list[PluginManifest]:
    """Return manifests for all registered plugins."""
    return [p.manifest for p in PLUGIN_REGISTRY.values()]


def get_plugin(plugin_id: str) -> Plugin | None:
    """Look up a plugin by its manifest plugin_id."""
    return PLUGIN_REGISTRY.get(plugin_id)
