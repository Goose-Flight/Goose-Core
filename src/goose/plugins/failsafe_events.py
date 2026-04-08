"""Failsafe event analysis plugin — detects failsafe triggers and unexpected mode changes."""

from __future__ import annotations

from typing import Any

from goose.core.finding import Finding
from goose.core.flight import Flight, FlightEvent, ModeChange
from goose.plugins.base import Plugin
from goose.plugins.contract import PluginCategory, PluginManifest, PluginTrustState

# Modes that indicate an autonomous emergency response
EMERGENCY_MODES = {"rtl", "return", "land", "emergency", "failsafe", "parachute", "termination"}

# Mode transitions that are expected from pilot commands (not failsafe-induced)
PILOT_MODES = {"manual", "stabilized", "acro", "altitude", "position", "loiter", "auto"}


def _is_emergency_mode(mode: str) -> bool:
    return mode.lower() in EMERGENCY_MODES


class FailsafeEventsPlugin(Plugin):
    """Detect failsafe triggers and unexpected mode changes during flight."""

    name = "failsafe_events"
    description = "Failsafe trigger and mode change analysis"
    version = "1.0.0"
    min_mode = "manual"

    manifest = PluginManifest(
        plugin_id="failsafe_events",
        name="Failsafe Events",
        version="1.0.0",
        author="Goose Flight",
        description="Detects failsafe triggers and unexpected mode changes during flight",
        category=PluginCategory.HEALTH,
        supported_vehicle_types=["multirotor", "fixed_wing", "all"],
        required_streams=[],
        optional_streams=["mode_changes", "events"],
        output_finding_types=["failsafe_event", "emergency_mode_transition"],
    )

    def analyze(self, flight: Flight, config: dict[str, Any]) -> list[Finding]:
        findings: list[Finding] = []

        failsafe_events = self._collect_failsafe_events(flight.events)
        emergency_transitions = self._collect_emergency_transitions(flight.mode_changes)

        total_critical = sum(
            1 for e in failsafe_events if e.severity == "critical"
        )
        total_noncritical = len(failsafe_events) - total_critical
        total_emergency_transitions = len(emergency_transitions)

        # Overall score
        total_problems = len(failsafe_events) + total_emergency_transitions
        if total_problems == 0:
            score = 100
            overall_severity = "pass"
        elif total_critical == 0 and total_problems == 1:
            score = 80
            overall_severity = "warning"
        elif total_critical >= 1 and total_problems == 1:
            score = 50
            overall_severity = "warning"
        else:
            score = 20
            overall_severity = "critical"

        # Overall summary finding
        if total_problems == 0:
            findings.append(Finding(
                plugin_name=self.name,
                title="No failsafe events detected",
                severity="pass",
                score=100,
                description=(
                    "No failsafe events or unexpected emergency mode transitions "
                    "were detected during this flight."
                ),
                evidence={
                    "failsafe_count": 0,
                    "emergency_transitions": 0,
                },
            ))
        else:
            findings.append(Finding(
                plugin_name=self.name,
                title=(
                    f"Failsafe events detected — "
                    f"{len(failsafe_events)} event(s), "
                    f"{total_emergency_transitions} emergency transition(s)"
                ),
                severity=overall_severity,
                score=score,
                description=(
                    f"Found {len(failsafe_events)} failsafe event(s) "
                    f"({total_critical} critical, {total_noncritical} non-critical) "
                    f"and {total_emergency_transitions} emergency mode transition(s). "
                    "Failsafe events may indicate RC signal loss, low battery, GPS loss, "
                    "or other system faults."
                ),
                evidence={
                    "failsafe_count": len(failsafe_events),
                    "critical_count": total_critical,
                    "noncritical_count": total_noncritical,
                    "emergency_transitions": total_emergency_transitions,
                },
            ))

        # Individual findings for each failsafe event
        for event in failsafe_events:
            ev_score = 30 if event.severity == "critical" else 60
            findings.append(Finding(
                plugin_name=self.name,
                title=f"Failsafe event: {event.message}",
                severity=event.severity if event.severity in ("critical", "warning") else "warning",
                score=ev_score,
                description=(
                    f"Failsafe event recorded at t={event.timestamp:.2f}s: {event.message}. "
                    f"Event type: {event.event_type}, severity: {event.severity}."
                ),
                evidence={
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "message": event.message,
                },
                timestamp_start=event.timestamp,
                timestamp_end=event.timestamp,
            ))

        # Individual findings for each emergency transition
        for change in emergency_transitions:
            findings.append(Finding(
                plugin_name=self.name,
                title=f"Emergency mode transition: {change.from_mode} -> {change.to_mode}",
                severity="warning",
                score=55,
                description=(
                    f"Mode changed to emergency/autonomous mode '{change.to_mode}' "
                    f"from '{change.from_mode}' at t={change.timestamp:.2f}s. "
                    "This may indicate an automated failsafe response."
                ),
                evidence={
                    "from_mode": change.from_mode,
                    "to_mode": change.to_mode,
                },
                timestamp_start=change.timestamp,
                timestamp_end=change.timestamp,
            ))

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_failsafe_events(self, events: list[FlightEvent]) -> list[FlightEvent]:
        """Filter events list to failsafe-related events."""
        result = []
        for event in events:
            if (
                event.event_type == "failsafe"
                or event.severity == "critical"
                or "failsafe" in event.message.lower()
            ):
                result.append(event)
        return result

    def _collect_emergency_transitions(
        self, mode_changes: list[ModeChange]
    ) -> list[ModeChange]:
        """Find mode transitions that end in an emergency/autonomous-response mode."""
        return [mc for mc in mode_changes if _is_emergency_mode(mc.to_mode)]
