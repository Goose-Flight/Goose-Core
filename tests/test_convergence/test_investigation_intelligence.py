"""Tests for Deep Technical Sprint 2, Workstream C — Investigation Intelligence.

Covers:
  - C1: Timeline depth (RC loss, failsafe, EKF spikes, crash impact, motor sat)
  - C1b: Finding->Hypothesis linkage on timeline events
  - C1c: Timeline clustering
  - C2a: Hypothesis score_components transparency
  - C2c: unknown_mixed notes enrichment
  - C3a: ForensicCaseReport timeline_summary key
  - C3b: AnomalyReport dominant_theme key
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
import pytest

from goose.forensics.canonical import (
    EvidenceReference,
    FindingSeverity,
    ForensicFinding,
    Hypothesis,
    HypothesisStatus,
)
from goose.forensics.lifting import generate_hypotheses
from goose.forensics.timeline import (
    TimelineEvent,
    TimelineEventCategory,
    TimelineEventType,
    build_full_timeline,
    build_timeline_from_findings,
    cluster_timeline_events,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "test-run-C2"


def _finding(
    plugin_id: str,
    severity: FindingSeverity,
    title: str = "Test finding",
    finding_id: str | None = None,
    start_time: float | None = 10.0,
    stream_name: str = "test_stream",
) -> ForensicFinding:
    """Create a minimal ForensicFinding."""
    return ForensicFinding(
        finding_id=finding_id or f"FND-{uuid.uuid4().hex[:8].upper()}",
        plugin_id=plugin_id,
        plugin_version="1.0.0",
        title=title,
        description="Test description",
        severity=severity,
        score=80 if severity != FindingSeverity.PASS else 100,
        confidence=0.8 if severity != FindingSeverity.PASS else 1.0,
        evidence_references=[EvidenceReference(evidence_id="EV-001", stream_name=stream_name)],
        start_time=start_time,
    )


def _make_flight_with_failsafe():
    """Create a minimal Flight-like object with failsafe events."""

    from goose.core.flight import Flight, FlightEvent, FlightMetadata

    meta = FlightMetadata(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type=None,
        hardware=None,
        duration_sec=60.0,
        start_time_utc=None,
        log_format="ulog",
        motor_count=4,
    )
    flight = Flight(metadata=meta)
    flight.events = [
        FlightEvent(
            timestamp=15.0,
            event_type="failsafe",
            severity="critical",
            message="RC Failsafe Triggered",
        ),
        FlightEvent(
            timestamp=20.0,
            event_type="failsafe",
            severity="warning",
            message="Battery Failsafe",
        ),
    ]
    return flight


def _make_flight_with_rc_dropout():
    """Create a minimal Flight with RC input that drops to zero."""

    from goose.core.flight import Flight, FlightMetadata

    meta = FlightMetadata(
        source_file="test.ulg",
        autopilot="px4",
        firmware_version="1.14.0",
        vehicle_type="quadcopter",
        frame_type=None,
        hardware=None,
        duration_sec=60.0,
        start_time_utc=None,
        log_format="ulog",
        motor_count=4,
    )
    flight = Flight(metadata=meta)
    # Create RC input: channels are nominal, then drop to zero for 5 seconds
    timestamps = list(range(60))
    chan1 = [1500] * 20 + [0] * 5 + [1500] * 35
    flight.rc_input = pd.DataFrame(
        {
            "timestamp": [float(t) for t in timestamps],
            "chan1": chan1,
            "chan2": chan1,
            "chan3": chan1,
            "chan4": chan1,
        }
    )
    return flight


# ---------------------------------------------------------------------------
# C1: Timeline event extraction
# ---------------------------------------------------------------------------


class TestTimelineExtractsFailsafeEvents:
    def test_failsafe_events_produce_fault_timeline_events(self):
        flight = _make_flight_with_failsafe()
        from goose.forensics.timeline import build_timeline_from_flight

        events = build_timeline_from_flight(flight, RUN_ID)

        fault_events = [e for e in events if e.event_type == TimelineEventType.FAULT]
        assert len(fault_events) >= 2, (
            f"Expected at least 2 FAULT events from failsafe FlightEvents, got {len(fault_events)}; all events: {[(e.event_type, e.label) for e in events]}"
        )
        labels = [e.label for e in fault_events]
        assert any("Failsafe" in lbl or "failsafe" in lbl.lower() or "RC" in lbl or "Battery" in lbl for lbl in labels), f"Failsafe labels not found: {labels}"

    def test_failsafe_event_timestamps_are_correct(self):
        flight = _make_flight_with_failsafe()
        from goose.forensics.timeline import build_timeline_from_flight

        events = build_timeline_from_flight(flight, RUN_ID)
        fault_events = [e for e in events if e.event_type == TimelineEventType.FAULT and "failsafe" in e.label.lower()]
        timestamps = sorted(e.start_time for e in fault_events)
        assert 15.0 in timestamps or any(abs(t - 15.0) < 0.01 for t in timestamps), f"Expected timestamp ~15.0 in fault events, got: {timestamps}"


class TestTimelineExtractsRcLossWindow:
    def test_rc_dropout_produces_anomaly_event(self):
        flight = _make_flight_with_rc_dropout()
        from goose.forensics.timeline import build_timeline_from_flight

        events = build_timeline_from_flight(flight, RUN_ID)

        rc_events = [e for e in events if "rc" in e.label.lower() or "signal" in e.label.lower()]
        assert len(rc_events) >= 1, f"Expected at least 1 RC loss event, got 0; events: {[(e.label, e.event_category.value) for e in events]}"
        rc_ev = rc_events[0]
        assert rc_ev.event_category == TimelineEventCategory.ANOMALY
        assert rc_ev.severity == "warning"

    def test_rc_event_spans_dropout_window(self):
        flight = _make_flight_with_rc_dropout()
        from goose.forensics.timeline import build_timeline_from_flight

        events = build_timeline_from_flight(flight, RUN_ID)
        rc_events = [e for e in events if "rc" in e.label.lower() or "signal" in e.label.lower()]
        if rc_events:
            ev = rc_events[0]
            # dropout starts at t=20, lasts 5 seconds
            assert ev.start_time >= 18.0, f"RC loss start too early: {ev.start_time}"
            assert ev.start_time <= 22.0, f"RC loss start too late: {ev.start_time}"


# ---------------------------------------------------------------------------
# C1b: Finding -> Hypothesis linkage
# ---------------------------------------------------------------------------


class TestTimelineFindingLinksToHypothesis:
    def test_finding_derived_event_has_hypothesis_id(self):
        fid = "FND-TESTAB01"
        hyp_id = "HYP-TESTHYP1"
        finding = _finding("battery_sag", FindingSeverity.WARNING, finding_id=fid)

        hyp = Hypothesis(
            hypothesis_id=hyp_id,
            statement="Power issue",
            supporting_finding_ids=[fid],
            confidence=0.7,
            status=HypothesisStatus.CANDIDATE,
            theme="power",
            category="battery / power issue",
        )

        events = build_timeline_from_findings([finding], RUN_ID, hypotheses=[hyp])
        assert len(events) == 1
        ev = events[0]
        assert hyp_id in ev.related_hypothesis_ids, f"Expected {hyp_id} in related_hypothesis_ids, got {ev.related_hypothesis_ids}"

    def test_finding_not_in_hypothesis_has_no_hypothesis_id(self):
        fid = "FND-TESTAB02"
        other_fid = "FND-OTHER001"
        finding = _finding("battery_sag", FindingSeverity.WARNING, finding_id=fid)

        hyp = Hypothesis(
            hypothesis_id="HYP-OTHER001",
            statement="Unrelated hypothesis",
            supporting_finding_ids=[other_fid],
            confidence=0.5,
            status=HypothesisStatus.CANDIDATE,
            theme="power",
            category="battery / power issue",
        )

        events = build_timeline_from_findings([finding], RUN_ID, hypotheses=[hyp])
        assert len(events) == 1
        assert events[0].related_hypothesis_ids == []

    def test_build_full_timeline_threads_hypotheses(self):
        fid = "FND-FULLTEST1"
        hyp_id = "HYP-FULLTEST1"
        finding = _finding("crash_detection", FindingSeverity.CRITICAL, finding_id=fid)
        hyp = Hypothesis(
            hypothesis_id=hyp_id,
            statement="Crash occurred",
            supporting_finding_ids=[fid],
            confidence=0.8,
            status=HypothesisStatus.CANDIDATE,
            theme="crash",
            category="impact / damage class",
        )

        events = build_full_timeline(None, [finding], RUN_ID, hypotheses=[hyp])
        finding_events = [e for e in events if e.event_type == TimelineEventType.FINDING]
        assert len(finding_events) == 1
        assert hyp_id in finding_events[0].related_hypothesis_ids


# ---------------------------------------------------------------------------
# C1c: Timeline clustering
# ---------------------------------------------------------------------------


class TestClusterTimelineEventsGroupsRapidSequence:
    def _make_event(self, t: float, label: str, severity: str = "warning", category: TimelineEventCategory = TimelineEventCategory.ANOMALY) -> TimelineEvent:
        return TimelineEvent(
            event_id=f"TLE-{uuid.uuid4().hex[:8].upper()}",
            event_type=TimelineEventType.SYSTEM_EVENT,
            event_category=category,
            label=label,
            start_time=t,
            source="parser",
            severity=severity,
        )

    def test_five_events_in_one_second_cluster(self):
        events = [
            self._make_event(10.0, "RC Loss"),
            self._make_event(10.1, "Failsafe"),
            self._make_event(10.2, "Mode change"),
            self._make_event(10.3, "EKF spike"),
            self._make_event(10.4, "Battery warning"),
        ]
        clustered = cluster_timeline_events(events, window_sec=2.0)
        # All 5 are within 2s of the first — should collapse to 1 composite
        assert len(clustered) == 1, f"Expected 1 cluster, got {len(clustered)}"
        assert "Multiple events" in clustered[0].label
        assert "(5)" in clustered[0].label

    def test_cluster_uses_highest_severity(self):
        events = [
            self._make_event(10.0, "Warning event", severity="warning"),
            self._make_event(10.1, "Critical event", severity="critical"),
            self._make_event(10.2, "Info event", severity="info"),
        ]
        clustered = cluster_timeline_events(events, window_sec=2.0)
        assert len(clustered) == 1
        assert clustered[0].severity == "critical"

    def test_two_events_are_not_clustered(self):
        events = [
            self._make_event(10.0, "Event A"),
            self._make_event(10.5, "Event B"),
        ]
        clustered = cluster_timeline_events(events, window_sec=2.0)
        # Only 2 events — below threshold of 3 for clustering
        assert len(clustered) == 2

    def test_separate_windows_cluster_independently(self):
        events = [
            # Window 1
            self._make_event(10.0, "A"),
            self._make_event(10.1, "B"),
            self._make_event(10.2, "C"),
            # Window 2 (separated by >2s)
            self._make_event(20.0, "X"),
            self._make_event(20.1, "Y"),
            self._make_event(20.2, "Z"),
        ]
        clustered = cluster_timeline_events(events, window_sec=2.0)
        assert len(clustered) == 2

    def test_cluster_retains_finding_and_hypothesis_ids(self):
        fid1 = "FND-C1"
        fid2 = "FND-C2"
        hid1 = "HYP-C1"
        e1 = TimelineEvent(
            event_id="TLE-01",
            event_type=TimelineEventType.FINDING,
            event_category=TimelineEventCategory.FINDING,
            label="Finding A",
            start_time=5.0,
            source="plugin",
            related_finding_ids=[fid1],
            related_hypothesis_ids=[hid1],
        )
        e2 = TimelineEvent(
            event_id="TLE-02",
            event_type=TimelineEventType.SYSTEM_EVENT,
            event_category=TimelineEventCategory.ANOMALY,
            label="System event",
            start_time=5.5,
            source="parser",
            related_finding_ids=[fid2],
        )
        e3 = TimelineEvent(
            event_id="TLE-03",
            event_type=TimelineEventType.FAULT,
            event_category=TimelineEventCategory.ANOMALY,
            label="Fault",
            start_time=6.0,
            source="parser",
        )
        clustered = cluster_timeline_events([e1, e2, e3], window_sec=2.0)
        assert len(clustered) == 1
        assert fid1 in clustered[0].related_finding_ids
        assert fid2 in clustered[0].related_finding_ids
        assert hid1 in clustered[0].related_hypothesis_ids


# ---------------------------------------------------------------------------
# C2a: Hypothesis score_components transparency
# ---------------------------------------------------------------------------


class TestHypothesisScoreComponentsVisible:
    def test_score_components_in_supporting_metrics(self):
        findings = [
            _finding("battery_sag", FindingSeverity.WARNING, "Battery voltage sag"),
            _finding("battery_sag", FindingSeverity.CRITICAL, "Battery critical"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        power_hyps = [h for h in hypotheses if h.theme == "power"]
        assert len(power_hyps) >= 1, "Expected a power hypothesis"
        hyp = power_hyps[0]
        assert "score_components" in hyp.supporting_metrics, f"score_components not in supporting_metrics: {hyp.supporting_metrics}"
        sc = hyp.supporting_metrics["score_components"]
        assert "supporting_findings_count" in sc
        assert "contradicting_findings_count" in sc
        assert "missing_stream_penalty" in sc
        assert "raw_confidence" in sc
        assert "final_confidence" in sc

    def test_score_components_values_are_correct(self):
        findings = [
            _finding("battery_sag", FindingSeverity.WARNING),
            _finding("battery_sag", FindingSeverity.CRITICAL),
            _finding("battery_sag", FindingSeverity.PASS, "Battery PASS"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        power_hyps = [h for h in hypotheses if h.theme == "power"]
        assert power_hyps
        sc = power_hyps[0].supporting_metrics["score_components"]
        assert sc["supporting_findings_count"] == 2
        assert sc["contradicting_findings_count"] == 1
        assert sc["raw_confidence"] == pytest.approx(round(2 / 3, 2), abs=0.01)

    def test_final_confidence_matches_hypothesis_confidence(self):
        findings = [_finding("battery_sag", FindingSeverity.CRITICAL)]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        power_hyps = [h for h in hypotheses if h.theme == "power"]
        if power_hyps:
            sc = power_hyps[0].supporting_metrics["score_components"]
            assert sc["final_confidence"] == pytest.approx(power_hyps[0].confidence, abs=0.01)


# ---------------------------------------------------------------------------
# C2c: unknown_mixed enrichment
# ---------------------------------------------------------------------------


class TestUnknownMixedHasUsefulNotes:
    def test_unknown_mixed_fires_when_no_theme_reaches_threshold(self):
        # Single low-weight finding that won't reach 0.3 confidence threshold
        # (no theme fires = unknown_mixed fires)
        findings: list[ForensicFinding] = []
        hypotheses = generate_hypotheses(findings, RUN_ID)
        unknown = [h for h in hypotheses if h.theme == "unknown_mixed"]
        assert len(unknown) == 1, f"Expected unknown_mixed hypothesis, got: {[h.theme for h in hypotheses]}"

    def test_unknown_mixed_has_analyst_notes(self):
        hypotheses = generate_hypotheses([], RUN_ID)
        unknown = [h for h in hypotheses if h.theme == "unknown_mixed"]
        if unknown:
            notes = unknown[0].analyst_notes
            assert notes, "analyst_notes should be non-empty for unknown_mixed"
            assert "not a cause" in notes.lower() or "more data" in notes.lower() or "forensic signal" in notes.lower(), (
                f"Expected forensic signal note, got: {notes}"
            )

    def test_unknown_mixed_unresolved_questions_contain_evidence_review(self):
        hypotheses = generate_hypotheses([], RUN_ID)
        unknown = [h for h in hypotheses if h.theme == "unknown_mixed"]
        if unknown:
            questions = unknown[0].unresolved_questions
            assert any("dominant cause" in q.lower() or "reviewing" in q.lower() or "consider" in q.lower() for q in questions), (
                f"Expected guidance question, got: {questions}"
            )

    def test_unknown_mixed_contradicting_findings_are_pass_findings(self):
        # When PASS findings exist, unknown_mixed should include them as contradicting
        findings = [
            _finding("battery_sag", FindingSeverity.PASS, "Battery PASS"),
            _finding("crash_detection", FindingSeverity.PASS, "Crash PASS"),
        ]
        hypotheses = generate_hypotheses(findings, RUN_ID)
        unknown = [h for h in hypotheses if h.theme == "unknown_mixed"]
        if unknown:
            cf_ids = unknown[0].contradicting_finding_ids
            assert len(cf_ids) >= 2, f"Expected PASS findings as contradicting in unknown_mixed, got: {cf_ids}"


# ---------------------------------------------------------------------------
# C3a: ForensicCaseReport has timeline_summary
# ---------------------------------------------------------------------------


class TestForensicCaseReportHasTimelineSummary:
    def _make_case_dir(self, tmp_path: Path) -> Path:
        import json

        case_dir = tmp_path / "test_case"
        case_dir.mkdir()

        # Minimal case.json
        (case_dir / "case.json").write_text(
            json.dumps(
                {
                    "case_id": "CASE-TEST-001",
                    "status": "open",
                    "platform_name": "TestQuad",
                    "operator_name": "TestOp",
                }
            ),
            encoding="utf-8",
        )

        # analysis dir with findings, hypotheses, timeline
        analysis_dir = case_dir / "analysis"
        analysis_dir.mkdir()
        (analysis_dir / "findings.json").write_text(
            json.dumps({"findings": [{"finding_id": "FND-001", "severity": "warning", "title": "Test finding", "plugin_id": "test"}]}), encoding="utf-8"
        )
        (analysis_dir / "hypotheses.json").write_text(
            json.dumps(
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "HYP-001",
                            "statement": "Test hypothesis",
                            "confidence": 0.7,
                            "status": "candidate",
                            "category": "test",
                            "contradicting_findings": [],
                            "unresolved_questions": ["Question 1"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (analysis_dir / "timeline.json").write_text(
            json.dumps(
                {
                    "events": [
                        {"event_type": "fault", "event_category": "anomaly", "label": "Test", "start_time": 5.0},
                        {"event_type": "system_event", "event_category": "system", "label": "Test2", "start_time": 10.0},
                    ]
                }
            ),
            encoding="utf-8",
        )

        # parsed dir
        parsed_dir = case_dir / "parsed"
        parsed_dir.mkdir()
        (parsed_dir / "parse_diagnostics.json").write_text(
            json.dumps(
                {
                    "parser_confidence": 0.9,
                    "warnings": [],
                    "stream_coverage": [],
                }
            ),
            encoding="utf-8",
        )
        (parsed_dir / "provenance.json").write_text(json.dumps({}), encoding="utf-8")

        # manifests dir
        manifests_dir = case_dir / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "evidence_manifest.json").write_text(json.dumps([]), encoding="utf-8")

        return case_dir

    def test_forensic_case_report_has_timeline_summary_key(self, tmp_path):
        from goose.forensics.reports import generate_forensic_case_report

        case_dir = self._make_case_dir(tmp_path)
        report = generate_forensic_case_report(case_dir, "run-001")
        d = report.to_dict()
        assert "timeline_summary" in d
        ts = d["timeline_summary"]
        assert isinstance(ts, dict), f"Expected dict, got {type(ts)}"
        assert "total_events" in ts
        assert ts["total_events"] == 2

    def test_forensic_case_report_has_hypothesis_summary(self, tmp_path):
        from goose.forensics.reports import generate_forensic_case_report

        case_dir = self._make_case_dir(tmp_path)
        report = generate_forensic_case_report(case_dir, "run-001")
        d = report.to_dict()
        hyp_inv = d["hypotheses_inventory"]
        assert isinstance(hyp_inv, list)
        if hyp_inv:
            h = hyp_inv[0]
            assert "id" in h
            assert "confidence" in h
            assert "contradicting_findings_count" in h
            assert "unresolved_questions_count" in h

    def test_forensic_case_report_has_evidence_quality(self, tmp_path):
        from goose.forensics.reports import generate_forensic_case_report

        case_dir = self._make_case_dir(tmp_path)
        report = generate_forensic_case_report(case_dir, "run-001")
        d = report.to_dict()
        assert "evidence_quality" in d
        eq = d["evidence_quality"]
        assert "mean_completeness" in eq
        assert "degraded_streams" in eq

    def test_forensic_case_report_has_investigation_completeness(self, tmp_path):
        from goose.forensics.reports import generate_forensic_case_report

        case_dir = self._make_case_dir(tmp_path)
        report = generate_forensic_case_report(case_dir, "run-001")
        d = report.to_dict()
        assert "investigation_completeness" in d
        ic = d["investigation_completeness"]
        assert isinstance(ic, int)
        assert 0 <= ic <= 100


# ---------------------------------------------------------------------------
# C3b: AnomalyReport has dominant_theme
# ---------------------------------------------------------------------------


class TestAnomalyReportHasDominantTheme:
    def _make_case_dir_with_hypotheses(self, tmp_path: Path) -> Path:
        import json

        case_dir = tmp_path / "anomaly_case"
        case_dir.mkdir()

        (case_dir / "case.json").write_text(
            json.dumps(
                {
                    "case_id": "CASE-ANOM-001",
                }
            ),
            encoding="utf-8",
        )

        analysis_dir = case_dir / "analysis"
        analysis_dir.mkdir()
        (analysis_dir / "findings.json").write_text(
            json.dumps(
                {
                    "findings": [
                        {"finding_id": "FND-001", "severity": "warning", "title": "Battery sag", "plugin_id": "battery_sag"},
                        {"finding_id": "FND-002", "severity": "critical", "title": "Crash", "plugin_id": "crash_detection"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (analysis_dir / "hypotheses.json").write_text(
            json.dumps(
                {
                    "hypotheses": [
                        {
                            "hypothesis_id": "HYP-001",
                            "statement": "Battery failure",
                            "confidence": 0.8,
                            "status": "candidate",
                            "category": "battery / power issue",
                            "theme": "power",
                        },
                        {
                            "hypothesis_id": "HYP-002",
                            "statement": "Crash detected",
                            "confidence": 0.6,
                            "status": "candidate",
                            "category": "impact / damage class",
                            "theme": "crash",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        (analysis_dir / "timeline.json").write_text(
            json.dumps(
                {
                    "events": [
                        {"event_type": "fault", "event_category": "anomaly", "label": "Battery warn", "start_time": 20.0},
                        {"event_type": "fault", "event_category": "anomaly", "label": "Crash", "start_time": 21.0},
                    ]
                }
            ),
            encoding="utf-8",
        )

        parsed_dir = case_dir / "parsed"
        parsed_dir.mkdir()
        (parsed_dir / "parse_diagnostics.json").write_text(
            json.dumps(
                {
                    "warnings": [],
                    "missing_streams": [],
                }
            ),
            encoding="utf-8",
        )

        return case_dir

    def test_anomaly_report_has_dominant_theme(self, tmp_path):
        from goose.forensics.reports import generate_anomaly_report

        case_dir = self._make_case_dir_with_hypotheses(tmp_path)
        report = generate_anomaly_report(case_dir, "CASE-ANOM-001", "run-001")
        d = report.to_dict()
        assert "dominant_theme" in d
        assert d["dominant_theme"] is not None
        assert d["dominant_theme"] in ("battery / power issue", "impact / damage class"), f"Unexpected dominant_theme: {d['dominant_theme']}"

    def test_anomaly_report_has_anomaly_windows(self, tmp_path):
        from goose.forensics.reports import generate_anomaly_report

        case_dir = self._make_case_dir_with_hypotheses(tmp_path)
        report = generate_anomaly_report(case_dir, "CASE-ANOM-001", "run-001")
        d = report.to_dict()
        assert "anomaly_windows" in d
        # The two anomaly events are within 5s of each other
        assert len(d["anomaly_windows"]) >= 1, f"Expected at least 1 anomaly window, got: {d['anomaly_windows']}"

    def test_anomaly_report_has_data_limitations(self, tmp_path):
        from goose.forensics.reports import generate_anomaly_report

        case_dir = self._make_case_dir_with_hypotheses(tmp_path)
        report = generate_anomaly_report(case_dir, "CASE-ANOM-001", "run-001")
        d = report.to_dict()
        assert "data_limitations" in d
        assert isinstance(d["data_limitations"], list)
