"""Formal plugin contract for Goose forensic analyzers.

Sprint 5 — Plugin Formalization

Every analysis plugin must implement the AnalyzerPlugin protocol and
declare a PluginManifest. Plugins emit ForensicFinding directly (not
thin Finding objects) and return PluginDiagnostics alongside results.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from goose.core.flight import Flight
    from goose.forensics.canonical import ForensicFinding
    from goose.parsers.diagnostics import ParseDiagnostics


class PluginCategory(str, Enum):
    HEALTH = "health"
    CRASH = "crash"
    FLIGHT_DYNAMICS = "flight_dynamics"
    NAVIGATION = "navigation"
    PROPULSION = "propulsion"
    RF_COMMS = "rf_comms"
    MISSION_RULES = "mission_rules"
    REPORTING = "reporting"


class PluginTrustState(str, Enum):
    BUILTIN_TRUSTED = "builtin_trusted"
    LOCAL_UNSIGNED = "local_unsigned"
    LOCAL_SIGNED = "local_signed"
    COMMUNITY = "community"
    ENTERPRISE_TRUSTED = "enterprise_trusted"
    BLOCKED = "blocked"


@dataclass
class PluginManifest:
    """Declarative metadata for an analysis plugin."""

    plugin_id: str
    name: str
    version: str
    author: str
    description: str
    category: PluginCategory
    supported_vehicle_types: list[str]
    required_streams: list[str]
    optional_streams: list[str]
    output_finding_types: list[str]
    minimum_contract_version: str = "2.0"
    plugin_type: str = "builtin"
    trust_state: PluginTrustState = PluginTrustState.BUILTIN_TRUSTED
    sha256_hash: str = ""
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "category": self.category.value,
            "supported_vehicle_types": self.supported_vehicle_types,
            "required_streams": self.required_streams,
            "optional_streams": self.optional_streams,
            "output_finding_types": self.output_finding_types,
            "minimum_contract_version": self.minimum_contract_version,
            "plugin_type": self.plugin_type,
            "trust_state": self.trust_state.value,
            "sha256_hash": self.sha256_hash,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PluginManifest:
        d = dict(d)
        d["category"] = PluginCategory(d["category"])
        d["trust_state"] = PluginTrustState(d.get("trust_state", "builtin_trusted"))
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class PluginDiagnostics:
    """Runtime diagnostics from a single plugin execution."""

    plugin_id: str
    plugin_version: str
    run_id: str
    executed: bool = True
    skipped: bool = False
    skip_reason: str = ""
    missing_streams: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings_emitted: int = 0
    execution_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "run_id": self.run_id,
            "executed": self.executed,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "missing_streams": self.missing_streams,
            "warnings": self.warnings,
            "findings_emitted": self.findings_emitted,
            "execution_duration_ms": self.execution_duration_ms,
        }


@runtime_checkable
class AnalyzerPlugin(Protocol):
    """Protocol that all forensic analyzer plugins must implement."""

    manifest: PluginManifest

    def analyze(
        self,
        flight: Flight,
        evidence_id: str,
        run_id: str,
        config: dict[str, Any],
        parse_diagnostics: ParseDiagnostics,
    ) -> tuple[list[ForensicFinding], PluginDiagnostics]:
        ...
