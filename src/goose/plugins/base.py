"""Plugin abstract base class for Goose analysis plugins."""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from goose.core.finding import Finding
from goose.core.flight import Flight

if TYPE_CHECKING:
    from goose.forensics.canonical import ForensicFinding
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

    def forensic_analyze(
        self,
        flight: Flight,
        evidence_id: str,
        run_id: str,
        config: dict[str, Any],
        parse_diagnostics: ParseDiagnostics,
    ) -> tuple[list[ForensicFinding], PluginDiagnostics]:
        """Run analysis and return ForensicFinding objects directly.

        Sprint 5 contract-compliant method. Checks required streams,
        runs the existing analyze() logic, and lifts results to
        ForensicFinding in-place.
        """
        from goose.plugins.contract import PluginDiagnostics as PDiag
        from goose.forensics.canonical import (
            EvidenceReference,
            FindingSeverity,
            ForensicFinding,
            _PLUGIN_STREAM_MAP,
        )

        t0 = time.perf_counter()

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

        # Run the existing analyze method
        thin_findings = self.analyze(flight, config)

        # Convert thin findings to ForensicFinding
        forensic_findings: list[ForensicFinding] = []
        warnings: list[str] = []

        for thin in thin_findings:
            stream = _PLUGIN_STREAM_MAP.get(thin.plugin_name)

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
