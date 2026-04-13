"""Tests for the v11 Strategy Sprint structured timeline model."""

from __future__ import annotations

from goose.forensics.canonical import (
    EvidenceReference,
    FindingSeverity,
    ForensicFinding,
)
from goose.forensics.timeline import (
    TimelineEvent,
    TimelineEventCategory,
    TimelineEventType,
    build_full_timeline,
    build_timeline_from_findings,
)


def _make_finding(
    finding_id: str = "FND-1",
    title: str = "Battery sag",
    severity: FindingSeverity = FindingSeverity.CRITICAL,
    start_time: float | None = 12.3,
    end_time: float | None = None,
) -> ForensicFinding:
    return ForensicFinding(
        finding_id=finding_id,
        plugin_id="battery_sag",
        plugin_version="1.0",
        title=title,
        description="test desc",
        severity=severity,
        score=20,
        confidence=0.8,
        start_time=start_time,
        end_time=end_time,
        evidence_references=[
            EvidenceReference(evidence_id="EV-1", support_summary="x")
        ],
    )


class TestBuildFromFindings:
    def test_builds_events_from_findings(self):
        findings = [
            _make_finding("FND-1", start_time=5.0),
            _make_finding("FND-2", start_time=10.0),
        ]
        events = build_timeline_from_findings(findings, run_id="RUN-1")
        assert len(events) == 2
        assert all(e.event_type == TimelineEventType.FINDING for e in events)
        assert all(e.event_category == TimelineEventCategory.FINDING for e in events)
        assert events[0].related_finding_ids == ["FND-1"]

    def test_skips_findings_without_timestamps(self):
        findings = [
            _make_finding("FND-1", start_time=None, end_time=None),
            _make_finding("FND-2", start_time=7.5),
        ]
        events = build_timeline_from_findings(findings, run_id="RUN-1")
        assert len(events) == 1
        assert events[0].related_finding_ids == ["FND-2"]

    def test_event_severity_is_string(self):
        findings = [_make_finding(severity=FindingSeverity.WARNING, start_time=1.0)]
        events = build_timeline_from_findings(findings, run_id="RUN-1")
        assert events[0].severity == "warning"


class TestTimelineEventSerialization:
    def test_roundtrip(self):
        ev = TimelineEvent(
            event_id="TLE-ABCD1234",
            event_type=TimelineEventType.FAULT,
            event_category=TimelineEventCategory.ANOMALY,
            label="Failsafe triggered",
            start_time=42.0,
            end_time=45.0,
            source="parser",
            severity="critical",
            confidence=0.9,
            related_finding_ids=["FND-9"],
        )
        d = ev.to_dict()
        restored = TimelineEvent.from_dict(d)
        assert restored.event_id == ev.event_id
        assert restored.event_type == TimelineEventType.FAULT
        assert restored.event_category == TimelineEventCategory.ANOMALY
        assert restored.start_time == 42.0
        assert restored.end_time == 45.0
        assert restored.severity == "critical"
        assert restored.related_finding_ids == ["FND-9"]

    def test_from_dict_ignores_unknown_keys(self):
        ev = TimelineEvent(
            event_id="TLE-1",
            event_type=TimelineEventType.PHASE,
            event_category=TimelineEventCategory.FLIGHT_PHASE,
            label="t",
            start_time=0.0,
        )
        d = ev.to_dict()
        d["unknown_key"] = "ignored"
        restored = TimelineEvent.from_dict(d)
        assert restored.event_id == "TLE-1"

    def test_from_dict_unknown_enum_falls_back(self):
        ev = TimelineEvent(
            event_id="TLE-1",
            event_type=TimelineEventType.PHASE,
            event_category=TimelineEventCategory.FLIGHT_PHASE,
            label="t",
            start_time=0.0,
        )
        d = ev.to_dict()
        d["event_type"] = "totally_unknown"
        d["event_category"] = "also_unknown"
        restored = TimelineEvent.from_dict(d)
        assert restored.event_type == TimelineEventType.SYSTEM_EVENT
        assert restored.event_category == TimelineEventCategory.SYSTEM


class TestBuildFullTimeline:
    def test_handles_none_flight(self):
        findings = [_make_finding(start_time=3.0)]
        events = build_full_timeline(None, findings, run_id="RUN-X")
        assert len(events) == 1
        assert events[0].label == "Battery sag"

    def test_sorted_by_start_time(self):
        findings = [
            _make_finding("FND-A", start_time=20.0),
            _make_finding("FND-B", start_time=5.0),
            _make_finding("FND-C", start_time=12.0),
        ]
        events = build_full_timeline(None, findings, run_id="RUN-Y")
        starts = [e.start_time for e in events]
        assert starts == sorted(starts)
