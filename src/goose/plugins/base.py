"""Plugin abstract base class for Goose analysis plugins."""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from goose.core.finding import Finding
from goose.core.flight import Flight

if TYPE_CHECKING:
    from goose.forensics.canonical import ForensicFinding
    from goose.forensics.tuning import TuningProfile
    from goose.parsers.diagnostics import ParseDiagnostics
    from goose.plugins.contract import PluginDiagnostics, PluginManifest

MODE_HIERARCHY: list[str] = ["manual", "stabilized", "altitude", "position", "mission"]


class Plugin(ABC):
    """Base class for all Goose analysis plugins."""

    name: str  # unique identifier e.g. "vibration"
    description: str  # human-readable description
    version: str  # semver e.g. "1.0.0"
    min_mode: str = "manual"  # minimum flight mode required
    manifest: PluginManifest  # Sprint 5: formal plugin manifest

    @abstractmethod
    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        """Run analysis on a flight. Return list of findings."""
        ...

    def forensic_analyze_native(
        self,
        flight: Flight,
        evidence_id: str,
        run_id: str,
        config: dict[str, Any],
        parse_diagnostics: ParseDiagnostics,
        tuning_profile: TuningProfile | None = None,
    ) -> tuple[list[ForensicFinding], PluginDiagnostics] | None:
        """Emit ForensicFinding directly, bypassing the thin-finding bridge.

        Override this in plugins that can construct fully-enriched
        ForensicFinding objects (with real timestamps, assumptions, and
        supporting_metrics) rather than going through the lifting bridge.

        The base implementation returns None, which signals forensic_analyze()
        to fall through to the standard thin-finding bridge.  Plugins that
        override this method must return a (findings, diagnostics) tuple.

        Migration path
        --------------
        Plugins are ported to native emission one at a time. forensic_analyze()
        checks whether this method has been overridden and, if so, calls it
        instead of the bridge. Non-ported plugins continue to use analyze().
        """
        return None

    def forensic_analyze(
        self,
        flight: Flight,
        evidence_id: str,
        run_id: str,
        config: dict[str, Any],
        parse_diagnostics: ParseDiagnostics,
        tuning_profile: TuningProfile | None = None,
    ) -> tuple[list[ForensicFinding], PluginDiagnostics]:
        """Run analysis and return ForensicFinding objects directly.

        Thin-finding bridge
        -------------------
        All 17 Core built-in plugins implement analyze() returning thin
        goose.core.finding.Finding objects. This method is the bridge that
        lifts them to ForensicFinding without requiring plugins to be rewritten.

        Plugins that override forensic_analyze_native() bypass the bridge
        entirely — their native emission is used instead. This gives a clean
        migration path without breaking non-ported plugins.

        The bridge will be retired progressively as plugins are ported to emit
        ForensicFinding directly. Until then this method is the single, canonical
        place where thin→forensic conversion happens for the plugin engine.

        Key bridge behaviours:
        - EvidenceReference.stream_name comes from self.manifest.primary_stream.
        - EvidenceReference.time_range_start/end come from thin.timestamp_start/end
          (None if the plugin didn't compute a window).
        - confidence = thin.score / 100.0 (proxy; plugins that declare own
          confidence directly in their ForensicFinding bypass this).
        - JSON-unsafe evidence dict values are stringified, not dropped.

        Sprint 5 contract-compliant method. Checks required streams,
        runs the existing analyze() logic, and lifts results to
        ForensicFinding in-place.

        If ``tuning_profile`` is supplied, the plugin's AnalyzerConfigProfile
        threshold values are merged into ``config`` before invoking
        ``analyze()``. Explicit entries in ``config`` take precedence over
        tuning-profile values so callers can override individual thresholds.
        """
        from goose.forensics.canonical import (
            EvidenceReference,
            FindingSeverity,
            ForensicFinding,
        )
        from goose.plugins.contract import PluginDiagnostics as PDiag

        # Dispatch to native emission if the plugin has overridden it.
        # We check by comparing the bound method to the base class version —
        # if they differ, the plugin has a native implementation.
        # Guard with hasattr for test stubs that don't inherit from Plugin.
        if (
            hasattr(type(self), "forensic_analyze_native")
            and type(self).forensic_analyze_native is not Plugin.forensic_analyze_native
        ):
            native_result = self.forensic_analyze_native(
                flight, evidence_id, run_id, config, parse_diagnostics, tuning_profile
            )
            if native_result is not None:
                return native_result

        t0 = time.perf_counter()

        # Merge tuning profile thresholds into config if supplied
        effective_config: dict[str, Any] = dict(config) if config else {}
        if tuning_profile is not None:
            plugin_cfg = tuning_profile.get_config_for_plugin(self.manifest.plugin_id)
            if plugin_cfg is not None and plugin_cfg.thresholds is not None:
                merged: dict[str, Any] = dict(plugin_cfg.thresholds.values)
                merged.update(effective_config)  # explicit config wins
                effective_config = merged

        # Check required streams
        missing = []
        for stream_name in self.manifest.required_streams:
            df = getattr(flight, stream_name, None)
            if df is None or (hasattr(df, "empty") and df.empty):
                missing.append(stream_name)

        if missing:
            elapsed = (time.perf_counter() - t0) * 1000
            diag = PDiag(
                plugin_id=self.manifest.plugin_id,
                plugin_version=self.manifest.version,
                run_id=run_id,
                executed=False,
                skipped=True,
                skip_reason=f"Missing required streams: {', '.join(missing)}",
                missing_streams=missing,
                findings_emitted=0,
                execution_duration_ms=round(elapsed, 2),
                trust_state=self.manifest.trust_state.value,
            )
            return [], diag

        # Run the existing analyze method with the merged config
        thin_findings = self.analyze(flight, effective_config)

        # Convert thin findings to ForensicFinding
        forensic_findings: list[ForensicFinding] = []
        warnings: list[str] = []

        for thin in thin_findings:
            stream = self.manifest.primary_stream or ""

            ev_ref = EvidenceReference(
                evidence_id=evidence_id,
                stream_name=stream,
                time_range_start=thin.timestamp_start,
                time_range_end=thin.timestamp_end,
                support_summary=thin.description[:200] if thin.description else "",
            )

            # Sanitize supporting metrics
            supporting: dict[str, Any] = {}
            for k, v in (thin.evidence or {}).items():
                try:
                    import json as _json
                    _json.dumps(v)
                    supporting[k] = v
                except (TypeError, ValueError):
                    supporting[k] = str(v)

            severity = (
                FindingSeverity(thin.severity)
                if thin.severity in FindingSeverity._value2member_map_
                else FindingSeverity.INFO
            )

            forensic_findings.append(ForensicFinding(
                finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
                plugin_id=thin.plugin_name,
                plugin_version=self.manifest.version,
                title=thin.title,
                description=thin.description,
                severity=severity,
                score=int(thin.score),
                confidence=round(int(thin.score) / 100.0, 2),
                confidence_scope="finding_analysis",
                phase=thin.phase,
                start_time=thin.timestamp_start,
                end_time=thin.timestamp_end,
                evidence_references=[ev_ref],
                supporting_metrics=supporting,
                contradicting_metrics={},
                assumptions=[],
                run_id=run_id,
            ))

        elapsed = (time.perf_counter() - t0) * 1000
        diag = PDiag(
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.version,
            run_id=run_id,
            executed=True,
            skipped=False,
            findings_emitted=len(forensic_findings),
            warnings=warnings,
            execution_duration_ms=round(elapsed, 2),
            trust_state=self.manifest.trust_state.value,
        )
        return forensic_findings, diag

    def applicable(self, flight: Flight) -> bool:
        """Check if this plugin can run on this flight (mode hierarchy check)."""
        flight_level = (
            MODE_HIERARCHY.index(flight.primary_mode)
            if flight.primary_mode in MODE_HIERARCHY
            else 0
        )
        required_level = (
            MODE_HIERARCHY.index(self.min_mode)
            if self.min_mode in MODE_HIERARCHY
            else 0
        )
        return flight_level >= required_level
