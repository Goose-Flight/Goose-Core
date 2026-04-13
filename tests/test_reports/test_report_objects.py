"""Tests for v11 report object schemas.

Covers the nine report families defined in ``goose.forensics.reports``:

- ForensicCaseReport
- EvidenceManifestReport
- ServiceRepairSummary
- QAValidationReport
- QuickAnalysisSummary
- Extended MissionSummaryReport / AnomalyReport / CrashMishapReport fields
- API routes for each
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goose.forensics.case_service import CaseService
from goose.forensics.reports import (
    AnomalyReport,
    CrashMishapReport,
    EvidenceManifestReport,
    ForensicCaseReport,
    MissionSummaryReport,
    QuickAnalysisSummary,
    ServiceRepairSummary,
    generate_evidence_manifest_report,
    generate_forensic_case_report,
    generate_qa_validation_report,
    generate_quick_analysis_summary,
    generate_service_repair_summary,
)
from goose.web import cases_api
from goose.web.app import create_app


@pytest.fixture
def svc(tmp_path: Path) -> CaseService:
    s = CaseService(base_dir=tmp_path / "cases")
    cases_api._set_service(s)
    return s


@pytest.fixture
def client(svc: CaseService) -> TestClient:
    app = create_app()
    return TestClient(app)


def _write_analysis(case_dir: Path, *, findings=None, hypotheses=None, timeline=None):
    analysis = case_dir / "analysis"
    analysis.mkdir(exist_ok=True)
    if findings is not None:
        (analysis / "findings.json").write_text(json.dumps({"findings": findings}), encoding="utf-8")
    if hypotheses is not None:
        (analysis / "hypotheses.json").write_text(json.dumps({"hypotheses": hypotheses}), encoding="utf-8")
    if timeline is not None:
        (analysis / "timeline.json").write_text(json.dumps({"events": timeline}), encoding="utf-8")


# ---------------------------------------------------------------------------
# ForensicCaseReport
# ---------------------------------------------------------------------------


class TestForensicCaseReport:
    def test_to_dict_has_required_fields(self):
        report = ForensicCaseReport(
            generated_at="2026-04-08T12:00:00",
            case_id="CASE-2026-000001",
            run_id="RUN-TEST",
            profile="default",
            engine_version="0.6.0",
        )
        d = report.to_dict()
        required = {
            "report_type",
            "report_version",
            "generated_at",
            "case_id",
            "run_id",
            "profile",
            "engine_version",
            "case_summary",
            "evidence_inventory",
            "parser_diagnostics_summary",
            "findings_inventory",
            "hypotheses_inventory",
            "timeline_summary",
            "plugin_execution_summary",
            "trust_tuning_context",
            "limitations",
            "export_replay_context",
        }
        assert required.issubset(set(d.keys()))
        assert d["report_type"] == "forensic_case_report"
        assert d["report_version"] == "1.0"

    def test_from_dict_roundtrip(self):
        report = ForensicCaseReport(
            generated_at="2026-04-08T12:00:00",
            case_id="CASE-X",
            run_id="RUN-X",
            profile="racer",
            engine_version="0.6.0",
            limitations=["missing gps stream"],
        )
        d = report.to_dict()
        rebuilt = ForensicCaseReport.from_dict(d)
        assert rebuilt.case_id == "CASE-X"
        assert rebuilt.profile == "racer"
        assert rebuilt.limitations == ["missing gps stream"]

    def test_generator_handles_empty_case_dir(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        report = generate_forensic_case_report(case_dir, run_id="RUN-1")
        assert report.case_id == case.case_id
        assert report.run_id == "RUN-1"
        assert report.findings_inventory == []
        assert report.hypotheses_inventory == []

    def test_generator_populates_findings_and_hypotheses(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        _write_analysis(
            case_dir,
            findings=[
                {"severity": "critical", "title": "Motor failure", "finding_id": "F-1"},
                {"severity": "warning", "title": "Low battery", "finding_id": "F-2"},
            ],
            hypotheses=[
                {"statement": "Motor failure", "confidence": 0.9},
            ],
            timeline=[{"event_type": "arm", "timestamp": "2026-04-08T12:00:00"}],
        )
        report = generate_forensic_case_report(case_dir, run_id="RUN-1")
        assert len(report.findings_inventory) == 2
        assert len(report.hypotheses_inventory) == 1
        # timeline_summary is a dict with enriched structure (C3a sprint);
        # check total_events count matches the 1 event we wrote.
        assert report.timeline_summary.get("total_events", len(report.timeline_summary)) == 1


# ---------------------------------------------------------------------------
# EvidenceManifestReport
# ---------------------------------------------------------------------------


class TestEvidenceManifestReport:
    def test_builds_from_empty_case_directory_gracefully(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        report = generate_evidence_manifest_report(case_dir)
        assert report.case_id == case.case_id
        assert report.evidence_items == []
        assert report.attachments == []
        # empty evidence -> all_verified vacuously True
        assert report.immutability_verification["all_verified"] is True
        assert report.immutability_verification["total_count"] == 0

    def test_to_dict_shape(self):
        report = EvidenceManifestReport(
            generated_at="2026-04-08T12:00:00",
            case_id="CASE-EV",
        )
        d = report.to_dict()
        assert d["report_type"] == "evidence_manifest_report"
        assert "provenance_summary" in d
        assert "audit_summary" in d
        assert "immutability_verification" in d

    def test_from_dict_roundtrip(self):
        d = {
            "generated_at": "2026-04-08T12:00:00",
            "case_id": "CASE-EV",
            "evidence_items": [{"evidence_id": "EV-1", "immutable": True}],
        }
        report = EvidenceManifestReport.from_dict(d)
        assert report.case_id == "CASE-EV"
        assert len(report.evidence_items) == 1


# ---------------------------------------------------------------------------
# ServiceRepairSummary
# ---------------------------------------------------------------------------


class TestServiceRepairSummary:
    def test_handles_none_customer_name_and_ticket_id(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        report = generate_service_repair_summary(case_dir, run_id="RUN-1")
        assert report.customer_name is None
        assert report.ticket_id is None
        # When no hypotheses exist we should still get a sensible default
        assert report.likely_cause == "No definitive cause identified"
        assert report.likely_cause_confidence is None

    def test_picks_top_hypothesis_as_likely_cause(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        _write_analysis(
            case_dir,
            findings=[{"severity": "critical", "title": "Motor burnt"}],
            hypotheses=[
                {"statement": "Motor failure", "confidence": 0.9},
                {"statement": "ESC failure", "confidence": 0.5},
            ],
        )
        report = generate_service_repair_summary(case_dir, run_id="RUN-1")
        assert report.likely_cause == "Motor failure"
        assert report.likely_cause_confidence == 0.9
        assert "Motor failure" in report.customer_summary

    def test_to_dict_contains_plain_language_summary(self):
        report = ServiceRepairSummary(
            generated_at="2026-04-08T12:00:00",
            case_id="CASE-REP",
            run_id="RUN-1",
            customer_name="Acme",
            ticket_id="T-1",
            platform_name="Quad-X",
            technician_name="Alex",
            damage_summary="prop broken",
            likely_cause="Motor failure",
            likely_cause_confidence=0.9,
            customer_summary="Your drone crashed due to motor failure.",
        )
        d = report.to_dict()
        assert d["report_type"] == "service_repair_summary"
        assert d["customer_summary"].startswith("Your drone")


# ---------------------------------------------------------------------------
# QAValidationReport
# ---------------------------------------------------------------------------


class TestQAValidationReport:
    def test_pass_disposition_with_no_findings(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        _write_analysis(case_dir, findings=[])  # empty list, file exists
        report = generate_qa_validation_report(case_dir, run_id="RUN-1")
        assert report.overall_disposition == "PASS"
        assert report.out_of_tolerance_findings == []

    def test_fail_disposition_with_critical_finding(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        _write_analysis(
            case_dir,
            findings=[
                {"severity": "critical", "title": "Motor saturated", "finding_id": "F-1"},
            ],
        )
        report = generate_qa_validation_report(case_dir, run_id="RUN-1")
        assert report.overall_disposition == "FAIL"
        assert len(report.out_of_tolerance_findings) == 1

    def test_conditional_pass_with_only_warnings(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        _write_analysis(
            case_dir,
            findings=[{"severity": "warning", "title": "Mild vibration"}],
        )
        report = generate_qa_validation_report(case_dir, run_id="RUN-1")
        assert report.overall_disposition == "CONDITIONAL_PASS"

    def test_requires_review_when_no_findings_file(self, svc: CaseService):
        case = svc.create_case(created_by="test")
        case_dir = svc.case_dir(case.case_id)
        # No findings.json written
        report = generate_qa_validation_report(case_dir, run_id="RUN-1")
        assert report.overall_disposition == "REQUIRES_REVIEW"


# ---------------------------------------------------------------------------
# QuickAnalysisSummary
# ---------------------------------------------------------------------------


class TestQuickAnalysisSummary:
    def test_to_dict_roundtrip(self):
        report = QuickAnalysisSummary(
            generated_at="2026-04-08T12:00:00",
            profile="racer",
            engine_version="0.6.0",
            filename="flight.ulg",
            file_size_bytes=12345,
            parser_confidence=0.95,
            flight_duration_s=120.5,
            top_findings=[{"severity": "warning", "title": "Vibration"}],
            primary_hypothesis={"statement": "Prop imbalance", "confidence": 0.7},
            quick_checks=["Check prop balance"],
            limitations=[],
        )
        d = report.to_dict()
        rebuilt = QuickAnalysisSummary.from_dict(d)
        assert rebuilt.filename == "flight.ulg"
        assert rebuilt.parser_confidence == 0.95
        assert rebuilt.primary_hypothesis == {"statement": "Prop imbalance", "confidence": 0.7}
        assert rebuilt.quick_checks == ["Check prop balance"]

    def test_generator_derives_quick_checks_from_findings(self):
        report = generate_quick_analysis_summary(
            filename="f.ulg",
            file_size_bytes=100,
            findings=[
                {"severity": "critical", "title": "Vibration spike"},
                {"severity": "warning", "title": "GPS dropout"},
            ],
            hypotheses=[{"statement": "Prop issue", "confidence": 0.8}],
            parser_confidence=0.9,
            flight_duration_s=60.0,
        )
        assert report.primary_hypothesis["statement"] == "Prop issue"
        assert any("prop" in c.lower() for c in report.quick_checks)
        assert any("gps" in c.lower() for c in report.quick_checks)


# ---------------------------------------------------------------------------
# Extended Mission / Anomaly / Crash reports — backward compat
# ---------------------------------------------------------------------------


class TestExtendedReportFields:
    def test_mission_summary_to_dict_has_v11_fields(self):
        report = MissionSummaryReport(
            case_id="CASE-1",
            run_id="RUN-1",
            generated_at="2026-04-08T12:00:00",
            flight_duration_s=60.0,
            total_findings=1,
            critical_findings=0,
            warning_findings=1,
            top_hypothesis=None,
            top_hypothesis_confidence=None,
            parser_confidence=0.9,
        )
        d = report.to_dict()
        assert d["report_type"] == "mission_summary"
        assert d["report_version"] == "1.0"
        assert "mission_metadata" in d
        assert "platform_metadata" in d
        assert "limitations" in d

    def test_anomaly_report_has_extended_fields(self):
        report = AnomalyReport(
            case_id="CASE-1",
            run_id="RUN-1",
            generated_at="2026-04-08T12:00:00",
            findings=[{"severity": "warning", "title": "X"}],
            hypotheses=[],
        )
        d = report.to_dict()
        assert d["report_type"] == "anomaly_report"
        assert "chronology_snippet" in d
        assert "leading_hypotheses" in d

    def test_crash_report_has_extended_fields(self):
        report = CrashMishapReport(
            case_id="CASE-1",
            run_id="RUN-1",
            generated_at="2026-04-08T12:00:00",
            crash_detected=True,
        )
        d = report.to_dict()
        assert d["report_type"] == "crash_mishap_report"
        assert "chronology" in d
        assert "mission_context" in d
        assert "data_quality_limitations" in d


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


class TestReportRoutes:
    def test_forensic_case_report_route(self, client: TestClient, svc: CaseService):
        res = client.post("/api/cases", json={"created_by": "test"})
        assert res.status_code == 201
        case_id = res.json()["case"]["case_id"]

        r = client.get(f"/api/cases/{case_id}/exports/reports/forensic-case")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["report"]["report_type"] == "forensic_case_report"
        assert body["report"]["case_id"] == case_id

    def test_evidence_manifest_report_route(self, client: TestClient, svc: CaseService):
        res = client.post("/api/cases", json={"created_by": "test"})
        case_id = res.json()["case"]["case_id"]

        r = client.get(f"/api/cases/{case_id}/exports/reports/evidence-manifest")
        assert r.status_code == 200
        body = r.json()
        assert body["report"]["report_type"] == "evidence_manifest_report"

    def test_service_repair_report_route(self, client: TestClient, svc: CaseService):
        res = client.post("/api/cases", json={"created_by": "test"})
        case_id = res.json()["case"]["case_id"]

        r = client.get(f"/api/cases/{case_id}/exports/reports/service-repair")
        assert r.status_code == 200
        body = r.json()
        assert body["report"]["report_type"] == "service_repair_summary"

    def test_qa_validation_report_route(self, client: TestClient, svc: CaseService):
        res = client.post("/api/cases", json={"created_by": "test"})
        case_id = res.json()["case"]["case_id"]

        r = client.get(f"/api/cases/{case_id}/exports/reports/qa-validation")
        assert r.status_code == 200
        body = r.json()
        assert body["report"]["report_type"] == "qa_validation_report"
        # No findings file yet -> REQUIRES_REVIEW
        assert body["report"]["overall_disposition"] == "REQUIRES_REVIEW"

    def test_quick_summary_route(self, client: TestClient, svc: CaseService):
        res = client.post("/api/cases", json={"created_by": "test"})
        case_id = res.json()["case"]["case_id"]

        r = client.get(f"/api/cases/{case_id}/exports/reports/quick-summary")
        assert r.status_code == 200
        body = r.json()
        assert body["report"]["report_type"] == "quick_analysis_summary"

    def test_route_404_on_unknown_case(self, client: TestClient):
        r = client.get("/api/cases/CASE-DOESNOTEXIST/exports/reports/forensic-case")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Feature tier matrix
# ---------------------------------------------------------------------------


class TestFeatureTierMatrix:
    def test_matrix_is_populated(self):
        from goose.features import FEATURE_TIER_MATRIX, EntitlementLevel

        assert "quick_analysis" in FEATURE_TIER_MATRIX
        assert FEATURE_TIER_MATRIX["quick_analysis"] == EntitlementLevel.OSS_CORE
        assert FEATURE_TIER_MATRIX["advanced_reports"] == EntitlementLevel.LOCAL_PRO
        assert FEATURE_TIER_MATRIX["shared_cases"] == EntitlementLevel.HOSTED_TEAM
        assert FEATURE_TIER_MATRIX["enterprise_audit"] == EntitlementLevel.ENTERPRISE_GOV

    def test_is_feature_enabled_defaults_to_true_for_unknown(self):
        from goose.features import is_feature_enabled

        assert is_feature_enabled("something_not_in_matrix") is True

    def test_is_feature_enabled_gates_on_level(self):
        from goose.features import EntitlementLevel, FeatureGate, is_feature_enabled

        FeatureGate.set_level(EntitlementLevel.OSS_CORE)
        try:
            assert is_feature_enabled("quick_analysis") is True
            assert is_feature_enabled("advanced_reports") is False
            FeatureGate.set_level(EntitlementLevel.LOCAL_PRO)
            assert is_feature_enabled("advanced_reports") is True
            assert is_feature_enabled("shared_cases") is False
        finally:
            FeatureGate.set_level(EntitlementLevel.OSS_CORE)

    def test_features_api_includes_feature_matrix(self, client: TestClient):
        r = client.get("/api/features")
        assert r.status_code == 200
        data = r.json()
        assert "features" in data
        assert "feature_requirements" in data
        assert data["features"]["quick_analysis"] is True
        assert data["features"]["advanced_reports"] is False
        assert data["feature_requirements"]["advanced_reports"] == "local_pro"
