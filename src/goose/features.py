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


# ---------------------------------------------------------------------------
# Feature tier matrix — doc 05 encoded as machine-readable data
# ---------------------------------------------------------------------------
#
# Maps named features to the minimum entitlement level at which they become
# available. This is the single source of truth for the tier matrix; the GUI,
# reports, and docs all consume this mapping rather than duplicating it.
#
# Unknown features default to enabled (``is_feature_enabled`` returns True)
# so legacy call sites continue to work while the matrix grows.
# ---------------------------------------------------------------------------
# Named capability constants — import these at call sites instead of using
# raw strings to get IDE completion and catch typos at import time.
# ---------------------------------------------------------------------------

# Always available — every OSS build, no entitlement check needed.
# Checks how complete a case is: evidence, analysis, attachments, metadata,
# exports. Returned by GET /api/cases/{id}/completeness.
CAPABILITY_CASE_COMPLETENESS_CHECK = "case_completeness_check"

# Side-by-side diff of two analysis runs within a case.
# Available in Local Pro and above — enforced at the workflow layer.
# Endpoint: GET /api/cases/{id}/runs/compare?run_a=...&run_b=...
CAPABILITY_MULTI_RUN_COMPARISON = "multi_run_comparison"

# Submit multiple flight logs for analysis in a single request.
# Batch queue + result aggregation. Local Pro feature.
CAPABILITY_BATCH_ANALYSIS = "batch_analysis"

# Save and re-apply analysis configuration templates across cases.
# Includes tuning profile presets and plugin selection presets. Local Pro.
CAPABILITY_SAVED_TEMPLATES = "saved_templates"

# Advanced ZIP export bundle: includes evidence file, findings, hypotheses,
# audit log, and replay verification in a signed archive. Local Pro.
CAPABILITY_ADVANCED_EXPORT_ZIP = "advanced_export_zip"


FEATURE_TIER_MATRIX: dict[str, EntitlementLevel] = {
    # Core analysis — all tiers
    "quick_analysis": EntitlementLevel.OSS_CORE,
    "investigation_case": EntitlementLevel.OSS_CORE,
    "evidence_ingest": EntitlementLevel.OSS_CORE,
    "parser_diagnostics": EntitlementLevel.OSS_CORE,
    "findings_hypotheses": EntitlementLevel.OSS_CORE,
    "basic_export": EntitlementLevel.OSS_CORE,
    "base_plugins": EntitlementLevel.OSS_CORE,
    "community_plugins": EntitlementLevel.OSS_CORE,
    "trust_visibility": EntitlementLevel.OSS_CORE,
    "profiles_roles": EntitlementLevel.OSS_CORE,
    # Local Pro features
    "advanced_reports": EntitlementLevel.LOCAL_PRO,
    "premium_plugin_packs": EntitlementLevel.LOCAL_PRO,
    "batch_analysis": EntitlementLevel.LOCAL_PRO,
    "saved_templates_presets": EntitlementLevel.LOCAL_PRO,
    "full_replay_export": EntitlementLevel.LOCAL_PRO,
    "advanced_charting": EntitlementLevel.LOCAL_PRO,
    "tuning_profile_management": EntitlementLevel.LOCAL_PRO,
    # Local Pro boundary stubs — currently at OSS_CORE but reserved for future
    # gating when Local Pro is formally released. These are listed here so the
    # boundary is explicit and call sites can be updated without hunting through
    # the codebase when the tier distinction is enforced.
    # To gate these: change the EntitlementLevel to LOCAL_PRO.
    "saved_analysis_templates": EntitlementLevel.OSS_CORE,  # PRO-reserved: template reuse across runs
    "multi_run_batch": EntitlementLevel.OSS_CORE,  # PRO-reserved: batch multiple logs at once
    "advanced_export_formats": EntitlementLevel.OSS_CORE,  # PRO-reserved: ZIP bundle with evidence file
    # Named capability constants (see module-level CAPABILITY_* names above)
    CAPABILITY_CASE_COMPLETENESS_CHECK: EntitlementLevel.OSS_CORE,  # always available
    CAPABILITY_MULTI_RUN_COMPARISON: EntitlementLevel.LOCAL_PRO,  # side-by-side run diff
    CAPABILITY_BATCH_ANALYSIS: EntitlementLevel.LOCAL_PRO,  # batch log processing
    CAPABILITY_SAVED_TEMPLATES: EntitlementLevel.LOCAL_PRO,  # config template reuse
    CAPABILITY_ADVANCED_EXPORT_ZIP: EntitlementLevel.LOCAL_PRO,  # signed ZIP bundle export
    # Hosted Team features
    "accounts_orgs": EntitlementLevel.HOSTED_TEAM,
    "shared_cases": EntitlementLevel.HOSTED_TEAM,
    "hosted_storage": EntitlementLevel.HOSTED_TEAM,
    "collaboration": EntitlementLevel.HOSTED_TEAM,
    "fleet_trend_views": EntitlementLevel.HOSTED_TEAM,
    # Enterprise / Gov features
    "plugin_allowlist_enforcement": EntitlementLevel.ENTERPRISE_GOV,
    "retention_controls": EntitlementLevel.ENTERPRISE_GOV,
    "enterprise_audit": EntitlementLevel.ENTERPRISE_GOV,
    "deployment_controls": EntitlementLevel.ENTERPRISE_GOV,
    "controlled_tuning_sets": EntitlementLevel.ENTERPRISE_GOV,
}


class FeatureGate:
    """Simple capability check.

    Defaults to ``OSS_CORE`` in the open-source build. Higher-tier builds can
    bump the current level by calling ``FeatureGate.set_level`` at startup.

    OSS_CORE default:
    -----------------
    The open-source build runs at OSS_CORE and never degrades functionality
    below it. All 17 built-in plugins, the full case system, Quick Analysis,
    profiles, GUI, and CLI are available at OSS_CORE.

    Tier upgrade path:
    ------------------
    To enable a higher tier in a downstream build:
        FeatureGate.set_level(EntitlementLevel.LOCAL_PRO)
    This unlocks LOCAL_PRO features (advanced_reports, batch_analysis, etc.)
    without touching any per-call-site logic.

    IMPORTANT: Do not put billing, licensing, or remote-check logic here.
    The core is local-first and offline-first. Any entitlement enforcement
    for paid tiers must live in a separate wrapper outside this module.
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
    def is_enabled_for_level(cls, required: EntitlementLevel) -> bool:
        """Return True if the current level satisfies ``required``."""
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
            "capabilities": {cap.value: cls.is_enabled(cap) for cap in CapabilityGroup},
            "requirements": {cap.value: req.value for cap, req in CAPABILITY_REQUIREMENTS.items()},
            "features": {feature: cls.is_enabled_for_level(level) for feature, level in FEATURE_TIER_MATRIX.items()},
            "feature_requirements": {feature: level.value for feature, level in FEATURE_TIER_MATRIX.items()},
        }


def register_capability(
    feature_name: str,
    required_level: EntitlementLevel,
) -> None:
    """Register a named feature capability from a Pro or extension package.

    Pro packages call this at import time (e.g. in their package's ``__init__.py``)
    to add their capabilities to the feature tier matrix.  Once registered, the
    capability is available via ``is_feature_enabled()`` and visible through the
    ``/api/features`` route.

    If ``feature_name`` is already registered, the existing entry is overwritten.
    Core capabilities (defined in ``FEATURE_TIER_MATRIX`` above) should NOT be
    overwritten by extension packages — doing so is undefined behavior.

    Example (Pro package)::

        from goose.features import register_capability, EntitlementLevel
        register_capability("advanced_crash_reconstruction", EntitlementLevel.LOCAL_PRO)

    Args:
        feature_name:    Unique string key for this feature (e.g. ``"my_pro_feature"``).
        required_level:  Minimum EntitlementLevel at which this feature is available.
    """
    FEATURE_TIER_MATRIX[feature_name] = required_level


def is_feature_enabled(feature_name: str) -> bool:
    """Return True if ``feature_name`` is enabled at the current entitlement level.

    Unknown features default to enabled so call sites referencing features
    that haven't been added to the matrix yet continue to work.
    """
    required = FEATURE_TIER_MATRIX.get(feature_name)
    if required is None:
        return True
    return FeatureGate.is_enabled_for_level(required)


def get_feature_status() -> dict[str, Any]:
    return FeatureGate.to_dict()
