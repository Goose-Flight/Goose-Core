"""Tests for report model objects.

Hardening Sprint — test_report_objects
"""

from __future__ import annotations

import pytest

from goose.forensics.reports import (
    AnomalyReport,
    CrashMishapReport,
    MissionSummaryReport,
    ReplayMatchState,
    ReplayVerificationReport,
)


class TestReplayVerificationReport:
    def test_to_dict_roundtrip(self):
        report = ReplayVerificationReport(
            bundle_id="BDL-TEST1234",
            case_id="CASE-2026-000001",
            original_engine_version="1.3.0",
            current_engine_version="1.3.4",
            original_parser_version="1.0.0",
            current_parser_version="1.0.1",
            original_plugin_versions={"crash_detection": "1.0.0"},
            current_plugin_versions={"crash_detection": "1.0.1"},
            match_state=ReplayMatchState.VERSION_DRIFT,
            version_drifts=["engine: 1.3.0 -> 1.3.4"],
            verified_at="2026-04-08T12:00:00",
            notes="test",
        )
        d = report.to_dict()
        assert d["bundle_id"] == "BDL-TEST1234"
        assert d["match_state"] == "version_drift"
        assert d["version_drifts"] == ["engine: 1.3.0 -> 1.3.4"]

        # Round-trip
        report2 = ReplayVerificationReport.from_dict(d)
        assert report2.bundle_id == report.bundle_id
        assert report2.match_state == ReplayMatchState.VERSION_DRIFT

    def test_exact_match_state(self):
        report = ReplayVerificationReport(
            bundle_id="BDL-EXACT",
            case_id="CASE-2026-000001",
            original_engine_version="1.3.4",
            current_engine_version="1.3.4",
            original_parser_version="1.0.0",
            current_parser_version="1.0.0",
            original_plugin_versions={},
            current_plugin_versions={},
            match_state=ReplayMatchState.EXACT,
            version_drifts=[],
            verified_at="2026-04-08T12:00:00",
        )
        assert report.match_state == ReplayMatchState.EXACT
        assert report.to_dict()["match_state"] == "exact"


class TestMissionSummaryReport:
    def test_to_dict(self):
        report = MissionSummaryReport(
            case_id="CASE-2026-000001",
            run_id="RUN-ABCD1234",
            generated_at="2026-04-08T12:00:00",
            flight_duration_s=120.5,
            total_findings=10,
            critical_findings=2,
            warning_findings=3,
            top_hypothesis="Motor failure",
            top_hypothesis_confidence=0.85,
            parser_confidence=0.95,
            signal_quality_summary={"battery": 0.9, "gps": 0.8},
        )
        d = report.to_dict()
        assert d["case_id"] == "CASE-2026-000001"
        assert d["flight_duration_s"] == 120.5
        assert d["critical_findings"] == 2
        assert d["signal_quality_summary"]["battery"] == 0.9

    def test_from_dict_roundtrip(self):
        d = {
            "case_id": "CASE-2026-000001",
            "run_id": "RUN-TEST",
            "generated_at": "2026-04-08T12:00:00",
            "flight_duration_s": None,
            "total_findings": 0,
            "critical_findings": 0,
            "warning_findings": 0,
            "top_hypothesis": None,
            "top_hypothesis_confidence": None,
            "parser_confidence": None,
            "signal_quality_summary": {},
        }
        report = MissionSummaryReport.from_dict(d)
        assert report.flight_duration_s is None
        assert report.total_findings == 0


class TestAnomalyReport:
    def test_to_dict(self):
        findings = [
            {"severity": "critical", "title": "Motor failure"},
            {"severity": "warning", "title": "GPS degradation"},
        ]
        report = AnomalyReport(
            case_id="CASE-2026-000001",
            run_id="RUN-TEST",
            generated_at="2026-04-08T12:00:00",
            findings=findings,
            hypotheses=[],
        )
        d = report.to_dict()
        assert len(d["findings"]) == 2
        assert d["findings"][0]["severity"] == "critical"

    def test_empty_report(self):
        report = AnomalyReport(
            case_id="CASE-2026-000001",
            run_id="RUN-TEST",
            generated_at="2026-04-08T12:00:00",
        )
        d = report.to_dict()
        assert d["findings"] == []
        assert d["hypotheses"] == []


class TestCrashMishapReport:
    def test_to_dict_with_crash(self):
        report = CrashMishapReport(
            case_id="CASE-2026-000001",
            run_id="RUN-TEST",
            generated_at="2026-04-08T12:00:00",
            crash_detected=True,
            crash_findings=[{"title": "Crash detected", "severity": "critical"}],
            crash_hypotheses=[{"statement": "Motor failure led to crash", "confidence": 0.9}],
            evidence_references=[{"evidence_id": "EV-0001"}],
        )
        d = report.to_dict()
        assert d["crash_detected"] is True
        assert len(d["crash_findings"]) == 1
        assert len(d["evidence_references"]) == 1

    def test_no_crash(self):
        report = CrashMishapReport(
            case_id="CASE-2026-000001",
            run_id="RUN-TEST",
            generated_at="2026-04-08T12:00:00",
            crash_detected=False,
        )
        d = report.to_dict()
        assert d["crash_detected"] is False
        assert d["crash_findings"] == []

    def test_from_dict_roundtrip(self):
        d = {
            "case_id": "CASE-2026-000001",
            "run_id": "RUN-TEST",
            "generated_at": "2026-04-08T12:00:00",
            "crash_detected": True,
            "crash_findings": [{"title": "Impact"}],
            "crash_hypotheses": [],
            "evidence_references": [],
        }
        report = CrashMishapReport.from_dict(d)
        assert report.crash_detected is True
        assert len(report.crash_findings) == 1
