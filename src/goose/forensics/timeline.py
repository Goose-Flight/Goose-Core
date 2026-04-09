"""Structured timeline model and builders.

v11 Strategy Sprint — promote the case timeline from an ad-hoc list of
finding timestamps into a formally typed event stream. Timeline events may
come from: parser output (flight phases, mode changes, arming events),
plugins (findings), or the user (manual annotations, attachment links).

Design rules:
- Facts (parsed data), findings, and manual notes remain distinct — the
  event ``source`` field records where each event came from.
- Every event has a ``label`` and ``start_time``; ``end_time`` is optional
  and used for interval-style events (flight phases, failsafe windows).
- Forward-compatible serialization: ``from_dict`` ignores unknown keys.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from goose.core.flight import Flight
    from goose.forensics.canonical import ForensicFinding


class TimelineEventType(str, Enum):
    PHASE = "phase"                     # flight phase (takeoff, cruise, landing, ...)
    MODE_CHANGE = "mode_change"         # autopilot mode change
    SYSTEM_EVENT = "system_event"       # arming, disarming, EKF reset, ...
    FAULT = "fault"                     # failsafe, GPS loss, battery warning
    FINDING = "finding"                 # linked to a ForensicFinding
    USER_ANNOTATION = "user_annotation" # manual note or attachment reference
    IMPACT = "impact"                   # impact signature


class TimelineEventCategory(str, Enum):
    FLIGHT_PHASE = "flight_phase"
    SYSTEM = "system"
    ANOMALY = "anomaly"
    FINDING = "finding"
    MANUAL = "manual"


@dataclass
class TimelineEvent:
    """A single event on the case timeline."""

    event_id: str
    event_type: TimelineEventType
    event_category: TimelineEventCategory
    label: str
    start_time: float                   # seconds from log start
    end_time: float | None = None
    source: str = "system"              # "parser" | "plugin" | "user" | "system"
    severity: str | None = None         # "critical" | "warning" | "info" | "none"
    confidence: float | None = None
    related_evidence_ids: list[str] = field(default_factory=list)
    related_finding_ids: list[str] = field(default_factory=list)
    related_hypothesis_ids: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "event_category": self.event_category.value,
            "label": self.label,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "source": self.source,
            "severity": self.severity,
            "confidence": self.confidence,
            "related_evidence_ids": list(self.related_evidence_ids),
            "related_finding_ids": list(self.related_finding_ids),
            "related_hypothesis_ids": list(self.related_hypothesis_ids),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TimelineEvent:
        d = dict(d)
        et = d.get("event_type", "system_event")
        if isinstance(et, str):
            try:
                d["event_type"] = TimelineEventType(et)
            except ValueError:
                d["event_type"] = TimelineEventType.SYSTEM_EVENT
        ec = d.get("event_category", "system")
        if isinstance(ec, str):
            try:
                d["event_category"] = TimelineEventCategory(ec)
            except ValueError:
                d["event_category"] = TimelineEventCategory.SYSTEM
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)


def _new_event_id() -> str:
    return f"TLE-{uuid.uuid4().hex[:8].upper()}"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_timeline_from_findings(
    forensic_findings: list[ForensicFinding],
    run_id: str,
) -> list[TimelineEvent]:
    """Convert ForensicFindings with timestamps into TimelineEvents."""
    events: list[TimelineEvent] = []
    for f in forensic_findings:
        t = f.start_time if f.start_time is not None else f.end_time
        if t is None:
            continue
        sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.FINDING,
            event_category=TimelineEventCategory.FINDING,
            label=f.title,
            start_time=float(t),
            end_time=float(f.end_time) if f.end_time is not None and f.end_time != t else None,
            source="plugin",
            severity=sev,
            confidence=float(f.confidence) if f.confidence is not None else None,
            related_finding_ids=[f.finding_id],
            notes=f.description[:200] if f.description else "",
        ))
    return events


def build_timeline_from_flight(flight: Flight, run_id: str) -> list[TimelineEvent]:
    """Extract timeline events from the canonical Flight object.

    Handles flight phases, mode changes, arming/failsafe events, and
    flight-end bookends. Safe to call on a partially populated Flight.
    """
    events: list[TimelineEvent] = []

    # --- Flight phases (takeoff, cruise, landing, etc.) --------------------
    for phase in getattr(flight, "phases", []) or []:
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.PHASE,
            event_category=TimelineEventCategory.FLIGHT_PHASE,
            label=f"Phase: {getattr(phase, 'phase_type', 'unknown')}",
            start_time=float(getattr(phase, "start_time", 0.0) or 0.0),
            end_time=float(getattr(phase, "end_time", 0.0) or 0.0),
            source="parser",
            severity=None,
        ))

    # --- Mode changes ------------------------------------------------------
    for mc in getattr(flight, "mode_changes", []) or []:
        ts = float(getattr(mc, "timestamp", 0.0) or 0.0)
        frm = getattr(mc, "from_mode", "?")
        to = getattr(mc, "to_mode", "?")
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.MODE_CHANGE,
            event_category=TimelineEventCategory.SYSTEM,
            label=f"Mode: {frm} -> {to}",
            start_time=ts,
            source="parser",
            severity=None,
        ))

    # --- Flight events (errors, warnings, failsafes) -----------------------
    for fe in getattr(flight, "events", []) or []:
        ts = float(getattr(fe, "timestamp", 0.0) or 0.0)
        et = getattr(fe, "event_type", "info")
        sev = getattr(fe, "severity", None)
        msg = getattr(fe, "message", "") or ""
        is_failsafe = "failsafe" in (et or "").lower() or (sev == "critical")
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.FAULT if is_failsafe else TimelineEventType.SYSTEM_EVENT,
            event_category=(
                TimelineEventCategory.ANOMALY if is_failsafe else TimelineEventCategory.SYSTEM
            ),
            label=msg or f"Event: {et}",
            start_time=ts,
            source="parser",
            severity=sev,
        ))

    # --- Flight start / end bookends --------------------------------------
    duration = 0.0
    meta = getattr(flight, "metadata", None)
    if meta is not None:
        duration = float(getattr(meta, "duration_sec", 0.0) or 0.0)
    if duration > 0.0:
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.PHASE,
            event_category=TimelineEventCategory.FLIGHT_PHASE,
            label="Flight start",
            start_time=0.0,
            source="parser",
        ))
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.PHASE,
            event_category=TimelineEventCategory.FLIGHT_PHASE,
            label="Flight end",
            start_time=duration,
            source="parser",
        ))

    return events


def build_full_timeline(
    flight: Flight | None,
    forensic_findings: list[ForensicFinding],
    run_id: str,
) -> list[TimelineEvent]:
    """Combine parser-derived and finding-derived events, sorted by start_time."""
    events: list[TimelineEvent] = []
    if flight is not None:
        events.extend(build_timeline_from_flight(flight, run_id))
    events.extend(build_timeline_from_findings(forensic_findings, run_id))
    events.sort(key=lambda e: e.start_time)
    return events
