"""Feature gating scaffolding for Goose-Core.

v11 Strategy Sprint — capability model.

This module is a **scaffold**. In the OSS build ``FeatureGate`` always runs at
the ``OSS_CORE`` entitlement level; no billing, licensing, or online check is
performed anywhere in this file. The structure exists so that higher-tier
builds (Local Pro, Hosted Team, Enterprise/Gov) can bump the current level
without touching call sites scattered through the codebase.

Callers check availability with ``FeatureGate.is_enabled(capability)`` or
assert with ``FeatureGate.require(capability)``. The ``/api/features`` route
exposes the current state for the GUI.

IMPORTANT: do not put real licensing logic here. Any future billing or
entitlement enforcement must live outside the open-source core.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class EntitlementLevel(str, Enum):
    """Entitlement tiers. Ordered from least to most permissive.

    Ordering matters: a higher-index level implicitly includes every lower
    level. See ``FeatureGate.is_enabled`` for the check.
    """
    OSS_CORE = "oss_core"
    LOCAL_PRO = "local_pro"
    HOSTED_TEAM = "hosted_team"
    ENTERPRISE_GOV = "enterprise_gov"


class CapabilityGroup(str, Enum):
    """Capability buckets. Mapped to minimum entitlement level below."""
    CORE_CASE_WORKFLOW = "core_case_workflow"
    ADVANCED_REPORTS = "advanced_reports"
    PREMIUM_PLUGINS = "premium_plugins"
    BATCH_PROCESSING = "batch_processing"
    ADVANCED_WORKSPACE = "advanced_workspace"
    HOSTED_COLLABORATION = "hosted_collaboration"
    ORG_ADMIN = "org_admin"
    STRICT_PLUGIN_POLICY = "strict_plugin_policy"
    ENTERPRISE_CONTROLS = "enterprise_controls"


# Minimum entitlement level required for each capability.
CAPABILITY_REQUIREMENTS: dict[CapabilityGroup, EntitlementLevel] = {
    CapabilityGroup.CORE_CASE_WORKFLOW: EntitlementLevel.OSS_CORE,
    CapabilityGroup.ADVANCED_REPORTS: EntitlementLevel.LOCAL_PRO,
    CapabilityGroup.PREMIUM_PLUGINS: EntitlementLevel.LOCAL_PRO,
    CapabilityGroup.BATCH_PROCESSING: EntitlementLevel.LOCAL_PRO,
    CapabilityGroup.ADVANCED_WORKSPACE: EntitlementLevel.LOCAL_PRO,
    CapabilityGroup.HOSTED_COLLABORATION: EntitlementLevel.HOSTED_TEAM,
    CapabilityGroup.ORG_ADMIN: EntitlementLevel.HOSTED_TEAM,
    CapabilityGroup.STRICT_PLUGIN_POLICY: EntitlementLevel.ENTERPRISE_GOV,
    CapabilityGroup.ENTERPRISE_CONTROLS: EntitlementLevel.ENTERPRISE_GOV,
}


class FeatureGate:
    """Simple capability check.

    Defaults to ``OSS_CORE`` in the open-source build. Higher-tier builds can
    bump the current level by calling ``FeatureGate.set_level`` at startup.
    """

    _current_level: EntitlementLevel = EntitlementLevel.OSS_CORE

    @classmethod
    def set_level(cls, level: EntitlementLevel) -> None:
        cls._current_level = level

    @classmethod
    def current_level(cls) -> EntitlementLevel:
        return cls._current_level

    @classmethod
    def is_enabled(cls, capability: CapabilityGroup) -> bool:
        required = CAPABILITY_REQUIREMENTS[capability]
        levels = list(EntitlementLevel)
        return levels.index(cls._current_level) >= levels.index(required)

    @classmethod
    def require(cls, capability: CapabilityGroup) -> None:
        """Raise if capability not available at current entitlement level."""
        if not cls.is_enabled(capability):
            raise PermissionError(
                f"Capability '{capability.value}' requires "
                f"'{CAPABILITY_REQUIREMENTS[capability].value}' entitlement. "
                f"Current level: '{cls._current_level.value}'."
            )

    @classmethod
    def to_dict(cls) -> dict[str, Any]:
        """Return current entitlement state for API exposure."""
        return {
            "current_level": cls._current_level.value,
            "capabilities": {
                cap.value: cls.is_enabled(cap)
                for cap in CapabilityGroup
            },
            "requirements": {
                cap.value: req.value
                for cap, req in CAPABILITY_REQUIREMENTS.items()
            },
        }


def get_feature_status() -> dict[str, Any]:
    return FeatureGate.to_dict()
