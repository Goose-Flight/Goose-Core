"""Plugin trust and fingerprinting for Goose-Core.

Hardening Sprint — Plugin Trust Hardening

Provides:
- fingerprint_plugin(): SHA-256 of plugin source code
- TrustPolicy: evaluate whether a plugin is allowed to run
"""

from __future__ import annotations

import hashlib
import inspect
from enum import Enum
from typing import Any

from goose.plugins.contract import PluginManifest, PluginTrustState


def fingerprint_plugin(plugin_instance: Any) -> str:
    """Compute SHA-256 of the plugin class source code.

    Returns hex digest string, or empty string if source cannot be inspected.
    """
    try:
        source = inspect.getsource(type(plugin_instance))
        return hashlib.sha256(source.encode("utf-8")).hexdigest()
    except (OSError, TypeError) as exc:
        import logging
        logging.getLogger(__name__).debug(
            "Cannot fingerprint plugin %s (source unavailable): %s",
            type(plugin_instance).__name__, exc,
        )
        return ""


class TrustPolicy:
    """Determines whether a plugin is allowed to run based on trust state and policy."""

    class PolicyMode(str, Enum):
        PERMISSIVE = "permissive"           # all plugins run, warnings shown
        WARNED = "warned"                   # unsigned/community plugins run with warnings
        ALLOWLIST_ONLY = "allowlist_only"   # only explicitly allowed plugins run

    def __init__(
        self,
        mode: PolicyMode = PolicyMode.PERMISSIVE,
        allowlist: list[str] | None = None,
    ) -> None:
        self.mode = mode
        self.allowlist = allowlist or []

    def evaluate(
        self,
        manifest: PluginManifest,
        computed_fingerprint: str,
    ) -> tuple[bool, str]:
        """Evaluate whether a plugin should be allowed to run.

        Returns (allowed, reason).
        """
        # Blocked plugins are never allowed regardless of policy mode
        if manifest.trust_state == PluginTrustState.BLOCKED:
            return False, "plugin is blocked"

        if self.mode == self.PolicyMode.ALLOWLIST_ONLY:
            if manifest.plugin_id not in self.allowlist:
                return False, f"plugin {manifest.plugin_id} not in allowlist"

        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "allowlist": self.allowlist,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrustPolicy:
        return cls(
            mode=cls.PolicyMode(d.get("mode", "permissive")),
            allowlist=d.get("allowlist", []),
        )
