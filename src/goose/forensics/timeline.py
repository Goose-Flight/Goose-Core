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

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

logger = logging.getLogger(__name__)

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
    hypotheses: list | None = None,
) -> list[TimelineEvent]:
    """Convert ForensicFindings with timestamps into TimelineEvents.

    If ``hypotheses`` is provided, each finding-derived event will be linked
    to any hypothesis whose ``supporting_finding_ids`` contains the finding's ID.
    """
    # Build a lookup: finding_id -> list of hypothesis_ids that reference it
    fid_to_hyp_ids: dict[str, list[str]] = {}
    if hypotheses:
        for hyp in hypotheses:
            hyp_id = getattr(hyp, "hypothesis_id", None) or (
                hyp.get("hypothesis_id") if isinstance(hyp, dict) else None
            )
            if not hyp_id:
                continue
            supporting = getattr(hyp, "supporting_finding_ids", None) or (
                hyp.get("supporting_finding_ids", []) if isinstance(hyp, dict) else []
            )
            for fid in (supporting or []):
                fid_to_hyp_ids.setdefault(fid, []).append(hyp_id)

    events: list[TimelineEvent] = []
    for f in forensic_findings:
        t = f.start_time if f.start_time is not None else f.end_time
        if t is None:
            continue
        sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
        related_hyp_ids = fid_to_hyp_ids.get(f.finding_id, [])
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
            related_hypothesis_ids=related_hyp_ids,
            notes=f.description[:200] if f.description else "",
        ))
    return events


def build_timeline_from_flight(flight: Flight, run_id: str) -> list[TimelineEvent]:
    """Extract timeline events from the canonical Flight object.

    Handles flight phases, mode changes, arming/failsafe events, battery
    warning threshold crossings, GPS degradation windows, and flight-end
    bookends. Safe to call on a partially populated Flight.
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

    # --- Battery warning threshold crossings ------------------------------
    # Detect when voltage drops below warning thresholds or remaining_pct
    # drops below 20% and 10%.  Emit FAULT events at each crossing point.
    battery = getattr(flight, "battery", None)
    if battery is not None and not battery.empty:
        events.extend(_extract_battery_warning_events(battery))

    # --- GPS degradation windows ------------------------------------------
    # Detect when fix_type drops below 3D fix or satellite count falls below
    # a threshold, and emit FAULT events covering those windows.
    gps = getattr(flight, "gps", None)
    if gps is not None and not gps.empty:
        events.extend(_extract_gps_degradation_events(gps))

    # --- RC signal loss windows -------------------------------------------
    rc_input = getattr(flight, "rc_input", None)
    if rc_input is not None and not rc_input.empty:
        events.extend(_extract_rc_loss_events(rc_input))

    # --- EKF innovation spikes -------------------------------------------
    ekf = getattr(flight, "ekf", None)
    if ekf is not None and not ekf.empty:
        events.extend(_extract_ekf_innovation_spikes(ekf))

    # --- Motor saturation windows ----------------------------------------
    motors = getattr(flight, "motors", None)
    if motors is not None and not motors.empty:
        events.extend(_extract_motor_saturation_events(motors))

    # --- Crash / impact window -------------------------------------------
    if getattr(flight, "crashed", False):
        events.extend(_extract_crash_impact_event(flight))

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


# ---------------------------------------------------------------------------
# Battery and GPS event extraction helpers
# ---------------------------------------------------------------------------

_BATTERY_WARN_PCT = 20.0   # remaining_pct below this → battery warning
_BATTERY_CRIT_PCT = 10.0   # remaining_pct below this → battery critical
_BATTERY_WARN_V = 14.4     # voltage per 4S cell group — approximate threshold
_GPS_MIN_FIX = 3           # fix_type below this = degraded (1=no fix, 2=2D, 3=3D)
_GPS_MIN_SATS = 6          # satellite count below this = degraded


def _extract_battery_warning_events(battery: Any) -> list[TimelineEvent]:
    """Detect battery warning threshold crossings from telemetry.

    Emits a FAULT event at the first timestamp where:
    - remaining_pct drops below 20% (warning) or 10% (critical), OR
    - voltage drops below an approximate low-voltage threshold.

    Each threshold is only triggered once per flight to avoid event spam.
    """
    import pandas as pd
    events: list[TimelineEvent] = []

    if not isinstance(battery, pd.DataFrame) or battery.empty:
        return events
    if "timestamp" not in battery.columns:
        return events

    # remaining_pct thresholds
    if "remaining_pct" in battery.columns:
        pct = battery["remaining_pct"]
        ts = battery["timestamp"]

        for threshold, label, sev in [
            (_BATTERY_CRIT_PCT, "Battery critical (<10% remaining)", "critical"),
            (_BATTERY_WARN_PCT, "Battery warning (<20% remaining)", "warning"),
        ]:
            below = pct < threshold
            if below.any():
                first_idx = below.idxmax()
                t = float(ts.loc[first_idx])
                pct_val = float(pct.loc[first_idx])
                events.append(TimelineEvent(
                    event_id=_new_event_id(),
                    event_type=TimelineEventType.FAULT,
                    event_category=TimelineEventCategory.ANOMALY,
                    label=label,
                    start_time=t,
                    source="parser",
                    severity=sev,
                    notes=f"Battery remaining: {pct_val:.1f}%",
                ))

    # Low voltage crossing (only if voltage present but no remaining_pct)
    if "voltage" in battery.columns and "remaining_pct" not in battery.columns:
        voltage = battery["voltage"]
        ts = battery["timestamp"]
        # Rough 4S warning voltage: 14.4V = 3.6V/cell
        below_v = voltage < _BATTERY_WARN_V
        if below_v.any():
            first_idx = below_v.idxmax()
            t = float(ts.loc[first_idx])
            v_val = float(voltage.loc[first_idx])
            events.append(TimelineEvent(
                event_id=_new_event_id(),
                event_type=TimelineEventType.FAULT,
                event_category=TimelineEventCategory.ANOMALY,
                label=f"Low voltage detected ({v_val:.2f}V)",
                start_time=t,
                source="parser",
                severity="warning",
                notes=f"Voltage: {v_val:.2f}V (below {_BATTERY_WARN_V}V threshold)",
            ))

    return events


def _extract_gps_degradation_events(gps: Any) -> list[TimelineEvent]:
    """Detect GPS degradation windows from telemetry.

    Emits interval FAULT events covering windows where:
    - fix_type < 3 (not a 3D fix), OR
    - satellites < 6 (insufficient geometry).

    Merges consecutive degraded samples into windows (minimum 2 seconds).
    """
    import pandas as pd
    events: list[TimelineEvent] = []

    if not isinstance(gps, pd.DataFrame) or gps.empty:
        return events
    if "timestamp" not in gps.columns:
        return events

    ts = gps["timestamp"]

    # fix_type degradation: fix_type < 3 means no 3D fix
    if "fix_type" in gps.columns:
        fix = gps["fix_type"]
        degraded = fix < _GPS_MIN_FIX
        windows = _find_windows(ts, degraded, min_duration_sec=2.0)
        for (t_start, t_end) in windows:
            events.append(TimelineEvent(
                event_id=_new_event_id(),
                event_type=TimelineEventType.FAULT,
                event_category=TimelineEventCategory.ANOMALY,
                label="GPS degraded (no 3D fix)",
                start_time=t_start,
                end_time=t_end,
                source="parser",
                severity="warning",
                notes=f"GPS fix type below 3D for {t_end - t_start:.1f}s",
            ))

    # Low satellite count
    if "satellites" in gps.columns:
        sats = gps["satellites"]
        low_sats = sats < _GPS_MIN_SATS
        windows = _find_windows(ts, low_sats, min_duration_sec=2.0)
        for (t_start, t_end) in windows:
            events.append(TimelineEvent(
                event_id=_new_event_id(),
                event_type=TimelineEventType.FAULT,
                event_category=TimelineEventCategory.ANOMALY,
                label=f"Low GPS satellite count (<{_GPS_MIN_SATS})",
                start_time=t_start,
                end_time=t_end,
                source="parser",
                severity="warning",
                notes=f"Satellite count below {_GPS_MIN_SATS} for {t_end - t_start:.1f}s",
            ))

    return events


_RC_SIGNAL_ZERO_THRESHOLD = 50   # channel value below this considered a dropout
_EKF_INNOVATION_THRESHOLD = 0.5  # innovation magnitude above this is a spike
_MOTOR_SATURATION_THRESHOLD = 1900  # PWM value; motors above this are near-max


def _extract_rc_loss_events(rc: Any) -> list[TimelineEvent]:
    """Detect RC signal loss windows from rc_input DataFrame.

    Emits SYSTEM_EVENT "RC Signal Loss Window" with category ANOMALY and
    severity "warning" when any RC channel value drops to or near zero
    for a sustained window (minimum 1 second).  Degrades gracefully if
    no channel columns are found.
    """
    import pandas as pd
    events: list[TimelineEvent] = []
    if not isinstance(rc, pd.DataFrame) or rc.empty:
        return events
    if "timestamp" not in rc.columns:
        return events

    # Find columns that look like RC channels (not timestamp, not index)
    channel_cols = [
        c for c in rc.columns
        if c != "timestamp" and (
            c.startswith("chan") or c.startswith("rc") or c.startswith("channel")
            or c in ("roll", "pitch", "throttle", "yaw", "aux1", "aux2")
        )
    ]
    if not channel_cols:
        # Fallback: any numeric column that is not timestamp
        channel_cols = [c for c in rc.columns if c != "timestamp"]

    if not channel_cols:
        return events

    ts = rc["timestamp"]

    # An RC dropout is when ALL channels are near zero simultaneously
    all_zero = (rc[channel_cols].abs() < _RC_SIGNAL_ZERO_THRESHOLD).all(axis=1)
    windows = _find_windows(ts, all_zero, min_duration_sec=1.0)
    for t_start, t_end in windows:
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.SYSTEM_EVENT,
            event_category=TimelineEventCategory.ANOMALY,
            label="RC Signal Loss Window",
            start_time=t_start,
            end_time=t_end,
            source="parser",
            severity="warning",
            notes=f"RC signal dropout detected for {t_end - t_start:.1f}s",
        ))
    return events


def _extract_ekf_innovation_spikes(ekf: Any) -> list[TimelineEvent]:
    """Detect EKF innovation spikes from ekf DataFrame.

    Emits SYSTEM_EVENT "EKF Innovation Spike" with category ANOMALY when
    any innovation column exceeds a threshold.  Merges nearby spikes into
    windows (minimum 0.5 seconds).
    """
    import pandas as pd
    events: list[TimelineEvent] = []
    if not isinstance(ekf, pd.DataFrame) or ekf.empty:
        return events
    if "timestamp" not in ekf.columns:
        return events

    # Look for innovation columns
    innov_cols = [
        c for c in ekf.columns
        if "innov" in c.lower() or "innovation" in c.lower()
    ]
    if not innov_cols:
        return events

    ts = ekf["timestamp"]

    for col in innov_cols:
        try:
            vals = ekf[col].abs()
            spike_mask = vals > _EKF_INNOVATION_THRESHOLD
            windows = _find_windows(ts, spike_mask, min_duration_sec=0.5)
            for t_start, t_end in windows:
                events.append(TimelineEvent(
                    event_id=_new_event_id(),
                    event_type=TimelineEventType.SYSTEM_EVENT,
                    event_category=TimelineEventCategory.ANOMALY,
                    label="EKF Innovation Spike",
                    start_time=t_start,
                    end_time=t_end,
                    source="parser",
                    severity="warning",
                    notes=f"EKF innovation spike on '{col}' (>{_EKF_INNOVATION_THRESHOLD}) for {t_end - t_start:.1f}s",
                ))
        except Exception as exc:
            logger.warning("EKF innovation spike detection failed on column '%s': %s", col, exc)
            continue
    return events


def _extract_motor_saturation_events(motors: Any) -> list[TimelineEvent]:
    """Detect motor saturation windows from motors DataFrame.

    Emits SYSTEM_EVENT "Motor Saturation Window" with category ANOMALY when
    any motor output stays near maximum (>= _MOTOR_SATURATION_THRESHOLD) for
    a sustained window (minimum 2 seconds).
    """
    import pandas as pd
    events: list[TimelineEvent] = []
    if not isinstance(motors, pd.DataFrame) or motors.empty:
        return events
    if "timestamp" not in motors.columns:
        return events

    motor_cols = [c for c in motors.columns if c != "timestamp"]
    if not motor_cols:
        return events

    ts = motors["timestamp"]

    # Any motor at saturation
    any_saturated = (motors[motor_cols] >= _MOTOR_SATURATION_THRESHOLD).any(axis=1)
    windows = _find_windows(ts, any_saturated, min_duration_sec=2.0)
    for t_start, t_end in windows:
        events.append(TimelineEvent(
            event_id=_new_event_id(),
            event_type=TimelineEventType.SYSTEM_EVENT,
            event_category=TimelineEventCategory.ANOMALY,
            label="Motor Saturation Window",
            start_time=t_start,
            end_time=t_end,
            source="parser",
            severity="warning",
            notes=f"Motor(s) at saturation (>={_MOTOR_SATURATION_THRESHOLD}) for {t_end - t_start:.1f}s",
        ))
    return events


def _extract_crash_impact_event(flight: Any) -> list[TimelineEvent]:
    """Emit an IMPACT event near the end of log data when a crash is detected.

    Uses the last frames of attitude or velocity data to estimate the crash
    timestamp.  Falls back to the flight duration from metadata if no time
    series is available.
    """
    events: list[TimelineEvent] = []
    import pandas as pd

    crash_ts: float | None = None

    # Prefer attitude timestamp (most reliably logged until impact)
    attitude = getattr(flight, "attitude", None)
    if isinstance(attitude, pd.DataFrame) and not attitude.empty and "timestamp" in attitude.columns:
        crash_ts = float(attitude["timestamp"].iloc[-1])
    else:
        velocity = getattr(flight, "velocity", None)
        if isinstance(velocity, pd.DataFrame) and not velocity.empty and "timestamp" in velocity.columns:
            crash_ts = float(velocity["timestamp"].iloc[-1])

    if crash_ts is None:
        meta = getattr(flight, "metadata", None)
        if meta is not None:
            dur = getattr(meta, "duration_sec", None)
            if dur is not None:
                crash_ts = float(dur)

    if crash_ts is None:
        return events

    events.append(TimelineEvent(
        event_id=_new_event_id(),
        event_type=TimelineEventType.IMPACT,
        event_category=TimelineEventCategory.ANOMALY,
        label="Crash / Impact",
        start_time=crash_ts,
        source="parser",
        severity="critical",
        notes="Crash detected: rapid altitude loss near end of log.",
    ))
    return events


def _find_windows(
    timestamps: Any,
    mask: Any,
    min_duration_sec: float = 2.0,
) -> list[tuple[float, float]]:
    """Find contiguous True windows in a boolean mask, filtered by minimum duration.

    Returns list of (start_time, end_time) tuples.
    """
    windows: list[tuple[float, float]] = []
    if not mask.any():
        return windows

    in_window = False
    win_start = 0.0

    for i in range(len(mask)):
        if mask.iloc[i]:
            if not in_window:
                in_window = True
                win_start = float(timestamps.iloc[i])
        else:
            if in_window:
                win_end = float(timestamps.iloc[i])
                if win_end - win_start >= min_duration_sec:
                    windows.append((win_start, win_end))
                in_window = False

    # Handle window still open at end
    if in_window and len(timestamps) > 0:
        win_end = float(timestamps.iloc[-1])
        if win_end - win_start >= min_duration_sec:
            windows.append((win_start, win_end))

    return windows


def cluster_timeline_events(
    events: list[TimelineEvent],
    window_sec: float = 2.0,
) -> list[TimelineEvent]:
    """Group events occurring within ``window_sec`` of each other.

    When 3 or more events fall within a ``window_sec`` window, they are
    collapsed into a single composite SYSTEM_EVENT.  The composite event:
    - Uses the highest severity of the grouped events.
    - Label: "Multiple events ({count}) — {first label}..."
    - Retains all related_finding_ids and related_hypothesis_ids.
    - category ANOMALY if any grouped event is ANOMALY, else SYSTEM.
    - Groups with < 3 events are left as-is.
    """
    if not events:
        return events

    _SEV_RANK = {"critical": 0, "warning": 1, "info": 2, "none": 3, None: 3}

    sorted_events = sorted(events, key=lambda e: e.start_time)
    result: list[TimelineEvent] = []
    used: set[int] = set()

    for i, ev in enumerate(sorted_events):
        if i in used:
            continue
        # Collect all events that start within window_sec of ev
        group = [i]
        for j in range(i + 1, len(sorted_events)):
            if j in used:
                continue
            if sorted_events[j].start_time - ev.start_time <= window_sec:
                group.append(j)
            else:
                break  # events are sorted; no point continuing

        if len(group) < 3:
            result.append(ev)
            used.add(i)
        else:
            # Composite event
            grouped = [sorted_events[k] for k in group]
            for k in group:
                used.add(k)

            # Highest severity
            best_sev = sorted(
                [g.severity for g in grouped],
                key=lambda s: _SEV_RANK.get(s, 3),
            )[0]

            # Category: ANOMALY if any is ANOMALY
            cat = TimelineEventCategory.ANOMALY if any(
                g.event_category == TimelineEventCategory.ANOMALY for g in grouped
            ) else TimelineEventCategory.SYSTEM

            # Merge ids
            all_finding_ids: list[str] = []
            all_hyp_ids: list[str] = []
            seen_fids: set[str] = set()
            seen_hids: set[str] = set()
            for g in grouped:
                for fid in g.related_finding_ids:
                    if fid not in seen_fids:
                        all_finding_ids.append(fid)
                        seen_fids.add(fid)
                for hid in g.related_hypothesis_ids:
                    if hid not in seen_hids:
                        all_hyp_ids.append(hid)
                        seen_hids.add(hid)

            label = f"Multiple events ({len(grouped)}) — {grouped[0].label}..."
            result.append(TimelineEvent(
                event_id=_new_event_id(),
                event_type=TimelineEventType.SYSTEM_EVENT,
                event_category=cat,
                label=label,
                start_time=grouped[0].start_time,
                end_time=grouped[-1].start_time,
                source="system",
                severity=best_sev,
                related_finding_ids=all_finding_ids,
                related_hypothesis_ids=all_hyp_ids,
                notes=f"Cluster of {len(grouped)} events within {window_sec}s window.",
            ))

    result.sort(key=lambda e: e.start_time)
    return result


def build_full_timeline(
    flight: "Flight | None",
    forensic_findings: "list[ForensicFinding]",
    run_id: str,
    hypotheses: list | None = None,
) -> list[TimelineEvent]:
    """Combine parser-derived and finding-derived events, sorted by start_time."""
    events: list[TimelineEvent] = []
    if flight is not None:
        events.extend(build_timeline_from_flight(flight, run_id))
    events.extend(build_timeline_from_findings(forensic_findings, run_id, hypotheses=hypotheses))
    events.sort(key=lambda e: e.start_time)
    return events
