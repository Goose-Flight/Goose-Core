"""Formal plugin contract for Goose forensic analyzers.

Sprint 5 — Plugin Formalization

Every analysis plugin must implement the AnalyzerPlugin protocol and
declare a PluginManifest.  Plugins emit ForensicFinding directly (or via
the thin-finding bridge in Plugin.forensic_analyze()) and return
PluginDiagnostics alongside results.

Key types
---------
PluginCategory     — functional category enum for grouping/filtering plugins
PluginTrustState   — trust level declared by the plugin and enforced by TrustPolicy
PluginManifest     — declarative metadata struct every plugin must declare
PluginDiagnostics  — per-execution runtime report (RAN / SKIPPED / BLOCKED)
AnalyzerPlugin     — Protocol that all forensic analyzer plugins must satisfy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from goose.core.flight import Flight
    from goose.forensics.canonical import ForensicFinding
    from goose.parsers.diagnostics import ParseDiagnostics


class PluginCategory(str, Enum):
    """Functional category for grouping and filtering plugins.

    Used in PluginManifest.category and exposed in the ``/api/plugins`` response
    so the GUI and CLI can group plugins by role.

    HEALTH          — general sensor/system health checks (log_health, gps_health, etc.)
    CRASH           — crash detection and impact classification
    FLIGHT_DYNAMICS — attitude/position tracking, control quality
    NAVIGATION      — GPS, EKF, estimator state
    PROPULSION      — motor saturation, ESC health
    RF_COMMS        — RC signal, telemetry link quality
    MISSION_RULES   — mission phase checks, operator action sequencing
    REPORTING       — report generation (not currently used by analyzer plugins)
    """

    HEALTH = "health"
    CRASH = "crash"
    FLIGHT_DYNAMICS = "flight_dynamics"
    NAVIGATION = "navigation"
    PROPULSION = "propulsion"
    RF_COMMS = "rf_comms"
    MISSION_RULES = "mission_rules"
    REPORTING = "reporting"


class PluginTrustState(str, Enum):
    """Trust level for a plugin, declared in its manifest and enforced by TrustPolicy.

    The forensic engine's TrustPolicy evaluates each plugin's manifest trust
    state before execution.  Plugins that cannot satisfy the active policy are
    BLOCKED (not silently skipped — they appear in PluginDiagnostics with
    blocked=True).

    BUILTIN_TRUSTED   — ships inside goose-flight; hash not checked at runtime
    LOCAL_UNSIGNED    — installed locally, no signature verification
    LOCAL_SIGNED      — installed locally, signature verified against known key
    COMMUNITY         — community plugin, treated as lower trust than signed local
    ENTERPRISE_TRUSTED — signed and verified against an enterprise key store
    BLOCKED           — explicitly blocked; plugin will not execute
    """

    BUILTIN_TRUSTED = "builtin_trusted"
    LOCAL_UNSIGNED = "local_unsigned"
    LOCAL_SIGNED = "local_signed"
    COMMUNITY = "community"
    ENTERPRISE_TRUSTED = "enterprise_trusted"
    BLOCKED = "blocked"


@dataclass
class PluginManifest:
    """Declarative metadata that every analysis plugin must provide.

    Declared as a class-level attribute on Plugin subclasses.  The forensic
    engine reads this before execution: required_streams drives the skip check,
    trust_state feeds TrustPolicy, and primary_stream names the EvidenceReference
    stream attached to findings lifted by the thin-finding bridge.

    Fields
    ------
    plugin_id             — stable machine identifier (e.g. ``"battery_sag"``)
    name                  — human display name
    version               — semver string (e.g. ``"1.0.0"``)
    author                — author or maintainer
    description           — one-sentence description for the GUI
    category              — PluginCategory enum value
    supported_vehicle_types — list of vehicle types (e.g. ``["multirotor"]``)
    required_streams      — Flight attribute names that must be non-empty to run
    optional_streams      — streams used if present but not required to run
    output_finding_types  — list of finding type labels this plugin can emit
    minimum_contract_version — minimum Plugin contract version required
    plugin_type           — ``"builtin"`` for Core plugins; ``"extension"`` for Pro
    trust_state           — PluginTrustState declared by this plugin
    sha256_hash           — SHA-256 of the plugin source (filled by TrustPolicy)
    signature             — cryptographic signature (for LOCAL_SIGNED plugins)
    primary_stream        — main telemetry stream for EvidenceReference construction
    """

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
    primary_stream: str = ""

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
    blocked: bool = False
    block_reason: str = ""
    missing_streams: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings_emitted: int = 0
    execution_duration_ms: float = 0.0
    trust_state: str = ""

    @property
    def execution_status(self) -> str:
        """Derive execution status from flags: RAN | SKIPPED | BLOCKED."""
        if self.blocked:
            return "BLOCKED"
        if self.skipped:
            return "SKIPPED"
        if self.executed:
            return "RAN"
        return "NOT_RUN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "run_id": self.run_id,
            "executed": self.executed,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "missing_streams": self.missing_streams,
            "warnings": self.warnings,
            "findings_emitted": self.findings_emitted,
            "execution_duration_ms": self.execution_duration_ms,
            "execution_status": self.execution_status,
            "trust_state": self.trust_state,
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
    ) -> tuple[list[ForensicFinding], PluginDiagnostics]: ...
