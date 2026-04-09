"""Core built-in plugin registry for Goose flight log analysis.

TWO PLUGIN SYSTEMS — READ THIS FIRST
-------------------------------------
There are two complementary plugin systems in Goose.  They are intentionally
separate and serve different roles:

1. ``PLUGIN_REGISTRY`` (this module)
   The Core internal registry.  Populated at import time with the 17 built-in
   analyzers shipped as part of goose-flight.  This is the single authoritative
   source of truth for Core plugins.  The forensic engine (analysis.py) runs
   plugins from this dict.  It is a plain dict — no magic discovery, no
   entry_points, no runtime scanning.

2. ``get_all_plugins()`` / ``registry.py``
   The Pro extension seam.  ``registry.py`` uses Python entry_points
   (group ``goose.plugins``) to discover plugins installed by third-party
   packages (e.g. goose-pro, goose-enterprise).  ``get_all_plugins()`` in
   this module returns Core built-ins PLUS any entry_point-discovered plugins,
   and is what the analysis orchestrator should use when it wants the merged set.

Rule: Core never imports Pro.  Pro extends Core by installing packages that
register entry_points.  ``get_all_plugins()`` is the one place where Core
and Pro plugins are combined — nowhere else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goose.plugins.contract import PluginManifest

if TYPE_CHECKING:
    from goose.plugins.base import Plugin

# ---------------------------------------------------------------------------
# Core built-in plugin classes
# ---------------------------------------------------------------------------

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
from goose.plugins.payload_change_detection import PayloadChangeDetectionPlugin
from goose.plugins.mission_phase_anomaly import MissionPhaseAnomalyPlugin
from goose.plugins.operator_action_sequence import OperatorActionSequencePlugin
from goose.plugins.environment_conditions import EnvironmentConditionsPlugin
from goose.plugins.damage_impact_classification import DamageImpactClassificationPlugin
from goose.plugins.link_telemetry_health import LinkTelemetryHealthPlugin

# Ordered list of Core built-in plugin classes.  Order here becomes the default
# execution order when no profile preference is specified.
_CORE_PLUGIN_CLASSES: list[type] = [
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
    PayloadChangeDetectionPlugin,
    MissionPhaseAnomalyPlugin,
    OperatorActionSequencePlugin,
    EnvironmentConditionsPlugin,
    DamageImpactClassificationPlugin,
    LinkTelemetryHealthPlugin,
]

# ---------------------------------------------------------------------------
# PLUGIN_REGISTRY — Core internal dict, plugin_id -> Plugin instance.
#
# This is the forensic engine's primary source of truth for Core built-ins.
# The analysis orchestrator (web/routes/analysis.py) reads directly from this
# dict when running per-case analysis.  Pro plugins do NOT appear here — they
# are discovered separately via get_all_plugins().
# ---------------------------------------------------------------------------
PLUGIN_REGISTRY: dict[str, Plugin] = {}

for _cls in _CORE_PLUGIN_CLASSES:
    _inst = _cls()
    PLUGIN_REGISTRY[_inst.manifest.plugin_id] = _inst

# Keep legacy name for any code that imported _PLUGIN_CLASSES before the rename.
# RETIRE: remove once all internal references are updated to _CORE_PLUGIN_CLASSES.
_PLUGIN_CLASSES = _CORE_PLUGIN_CLASSES


def get_plugin_manifests() -> list[PluginManifest]:
    """Return manifests for all Core built-in plugins."""
    return [p.manifest for p in PLUGIN_REGISTRY.values()]


def get_plugin(plugin_id: str) -> Plugin | None:
    """Look up a Core built-in plugin by its manifest plugin_id."""
    return PLUGIN_REGISTRY.get(plugin_id)


def get_all_plugins() -> dict[str, Plugin]:
    """Return Core built-ins merged with any Pro/extension plugins.

    This is the merged registry that the analysis orchestrator should use when
    it wants the full set of available plugins (Core + Pro extensions).

    Pro packages register their plugins via Python entry_points under the
    ``goose.plugins`` group.  Installing a Pro package is sufficient —
    ``get_all_plugins()`` discovers them automatically at call time.

    Extension plugins (e.g. from goose-pro) take precedence over Core built-ins
    when they share the same plugin_id. This allows an official Pro package to
    upgrade a Core plugin with an enhanced implementation. Third-party extensions
    that should NOT override Core should use unique plugin_ids.

    Returns a new dict on every call so callers may mutate it safely.
    """
    from goose.plugins.registry import discover_pro_plugins

    # Start with Core, then let Pro overrides win
    merged: dict[str, Plugin] = dict(PLUGIN_REGISTRY)
    for ext_plugin in discover_pro_plugins():
        merged[ext_plugin.manifest.plugin_id] = ext_plugin  # Pro wins
    return merged
