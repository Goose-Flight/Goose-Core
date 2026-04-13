"""Tests for goose.forensics.canonical — canonical forensic models.

Covers:
  - FindingSeverity, HypothesisStatus, ConfidenceBand enums
  - SignalQuality dataclass
  - EvidenceReference dataclass
  - ForensicFinding dataclass
  - Hypothesis dataclass
  - Confidence-scope distinction across all three confidence layers
"""

import json
from datetime import datetime

from goose.forensics.canonical import (
    ConfidenceBand,
    EvidenceReference,
    FindingSeverity,
    ForensicFinding,
    Hypothesis,
    HypothesisStatus,
    SignalQuality,
)
from goose.parsers.diagnostics import ParseDiagnostics

# ---------------------------------------------------------------------------
# Helper fixture
# ---------------------------------------------------------------------------

def make_finding(**kwargs) -> ForensicFinding:
    defaults = dict(
        finding_id="F-001",
        plugin_id="test_plugin",
        plugin_version="1.0.0",
        title="Test finding",
        description="A test finding",
        severity=FindingSeverity.WARNING,
        score=60,
        confidence=0.7,
    )
    defaults.update(kwargs)
    return ForensicFinding(**defaults)


# ---------------------------------------------------------------------------
# TestFindingSeverityEnum
# ---------------------------------------------------------------------------

class TestFindingSeverityEnum:
    def test_all_values_exist(self):
        assert FindingSeverity.CRITICAL
        assert FindingSeverity.WARNING
        assert FindingSeverity.INFO
        assert FindingSeverity.PASS

    def test_string_values_are_lowercase(self):
        assert FindingSeverity.CRITICAL.value == "critical"
        assert FindingSeverity.WARNING.value == "warning"
        assert FindingSeverity.INFO.value == "info"
        assert FindingSeverity.PASS.value == "pass"

    def test_construct_from_string(self):
        assert FindingSeverity("critical") is FindingSeverity.CRITICAL
        assert FindingSeverity("warning") is FindingSeverity.WARNING
        assert FindingSeverity("info") is FindingSeverity.INFO
        assert FindingSeverity("pass") is FindingSeverity.PASS


# ---------------------------------------------------------------------------
# TestHypothesisStatusEnum
# ---------------------------------------------------------------------------

class TestHypothesisStatusEnum:
    def test_all_values_exist(self):
        assert HypothesisStatus.CANDIDATE
        assert HypothesisStatus.SUPPORTED
        assert HypothesisStatus.REFUTED
        assert HypothesisStatus.INCONCLUSIVE

    def test_construct_from_string(self):
        assert HypothesisStatus("candidate") is HypothesisStatus.CANDIDATE
        assert HypothesisStatus("supported") is HypothesisStatus.SUPPORTED
        assert HypothesisStatus("refuted") is HypothesisStatus.REFUTED
        assert HypothesisStatus("inconclusive") is HypothesisStatus.INCONCLUSIVE


# ---------------------------------------------------------------------------
# TestConfidenceBand
# ---------------------------------------------------------------------------

class TestConfidenceBand:
    def test_high(self):
        assert ConfidenceBand.from_score(0.9) is ConfidenceBand.HIGH

    def test_medium(self):
        assert ConfidenceBand.from_score(0.65) is ConfidenceBand.MEDIUM

    def test_low(self):
        assert ConfidenceBand.from_score(0.3) is ConfidenceBand.LOW

    def test_unknown(self):
        assert ConfidenceBand.from_score(0.1) is ConfidenceBand.UNKNOWN

    def test_boundary_high(self):
        assert ConfidenceBand.from_score(0.80) is ConfidenceBand.HIGH

    def test_boundary_medium(self):
        assert ConfidenceBand.from_score(0.50) is ConfidenceBand.MEDIUM

    def test_boundary_low(self):
        assert ConfidenceBand.from_score(0.25) is ConfidenceBand.LOW


# ---------------------------------------------------------------------------
# TestSignalQuality
# ---------------------------------------------------------------------------

class TestSignalQuality:
    def test_default_fields(self):
        sq = SignalQuality(stream_name="battery_status")
        assert sq.stream_name == "battery_status"
        assert sq.completeness == 1.0
        assert sq.continuity == 1.0
        assert sq.corruption_detected is False
        assert sq.reliability_estimate == 1.0
        assert sq.row_count == 0
        assert sq.notes == ""

    def test_to_dict_from_dict_roundtrip(self):
        sq = SignalQuality(
            stream_name="gps_position",
            completeness=0.8,
            continuity=0.9,
            corruption_detected=True,
            reliability_estimate=0.75,
            row_count=1200,
            notes="Some corruption detected.",
        )
        restored = SignalQuality.from_dict(sq.to_dict())
        assert restored.stream_name == sq.stream_name
        assert restored.completeness == sq.completeness
        assert restored.continuity == sq.continuity
        assert restored.corruption_detected == sq.corruption_detected
        assert restored.reliability_estimate == sq.reliability_estimate
        assert restored.row_count == sq.row_count
        assert restored.notes == sq.notes

    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "stream_name": "attitude",
            "completeness": 1.0,
            "continuity": 1.0,
            "corruption_detected": False,
            "reliability_estimate": 1.0,
            "row_count": 500,
            "notes": "",
            "future_field_v2": "should be ignored",
        }
        sq = SignalQuality.from_dict(d)
        assert sq.stream_name == "attitude"

    def test_from_stream_coverage_present(self):
        from goose.parsers.diagnostics import StreamCoverage
        sc = StreamCoverage(stream_name="battery", present=True, row_count=300)
        sq = SignalQuality.from_stream_coverage(sc)
        assert sq.reliability_estimate == 1.0
        assert sq.completeness == 1.0
        assert sq.stream_name == "battery"
        assert sq.row_count == 300

    def test_from_stream_coverage_not_present(self):
        from goose.parsers.diagnostics import StreamCoverage
        sc = StreamCoverage(stream_name="rc_input", present=False, row_count=0)
        sq = SignalQuality.from_stream_coverage(sc)
        assert sq.reliability_estimate == 0.0
        assert sq.completeness == 0.0
        assert sq.stream_name == "rc_input"


# ---------------------------------------------------------------------------
# TestEvidenceReference
# ---------------------------------------------------------------------------

class TestEvidenceReference:
    def test_required_field_evidence_id(self):
        ref = EvidenceReference(evidence_id="EV-001")
        assert ref.evidence_id == "EV-001"

    def test_all_optional_fields_default_to_none(self):
        ref = EvidenceReference(evidence_id="EV-002")
        assert ref.stream_name is None
        assert ref.time_range_start is None
        assert ref.time_range_end is None
        assert ref.sample_index_start is None
        assert ref.sample_index_end is None
        assert ref.parameter_ref is None
        assert ref.support_summary == ""

    def test_to_dict_from_dict_roundtrip_all_fields(self):
        ref = EvidenceReference(
            evidence_id="EV-003",
            stream_name="battery_status",
            time_range_start=12.5,
            time_range_end=45.0,
            sample_index_start=100,
            sample_index_end=450,
            parameter_ref="BAT_V_CHARGED_THRESH",
            support_summary="Voltage drop detected in this window.",
        )
        restored = EvidenceReference.from_dict(ref.to_dict())
        assert restored.evidence_id == ref.evidence_id
        assert restored.stream_name == ref.stream_name
        assert restored.time_range_start == ref.time_range_start
        assert restored.time_range_end == ref.time_range_end
        assert restored.sample_index_start == ref.sample_index_start
        assert restored.sample_index_end == ref.sample_index_end
        assert restored.parameter_ref == ref.parameter_ref
        assert restored.support_summary == ref.support_summary

    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "evidence_id": "EV-004",
            "stream_name": None,
            "time_range_start": None,
            "time_range_end": None,
            "sample_index_start": None,
            "sample_index_end": None,
            "parameter_ref": None,
            "support_summary": "",
            "future_field_v2": "extra key",
        }
        ref = EvidenceReference.from_dict(d)
        assert ref.evidence_id == "EV-004"


# ---------------------------------------------------------------------------
# TestForensicFinding
# ---------------------------------------------------------------------------

class TestForensicFinding:
    def test_required_fields_present(self):
        f = make_finding()
        assert f.finding_id == "F-001"
        assert f.plugin_id == "test_plugin"
        assert f.plugin_version == "1.0.0"
        assert f.title == "Test finding"
        assert f.description == "A test finding"
        assert f.severity == FindingSeverity.WARNING
        assert f.score == 60
        assert f.confidence == 0.7

    def test_confidence_scope_default(self):
        f = make_finding()
        assert f.confidence_scope == "finding_analysis"

    def test_has_evidence_false_when_no_references(self):
        f = make_finding(evidence_references=[])
        assert f.has_evidence is False

    def test_has_evidence_true_with_one_reference(self):
        ref = EvidenceReference(evidence_id="EV-001", stream_name="battery")
        f = make_finding(evidence_references=[ref])
        assert f.has_evidence is True

    def test_confidence_band_property(self):
        f = make_finding(confidence=0.85)
        assert f.confidence_band is ConfidenceBand.from_score(0.85)
        assert f.confidence_band is ConfidenceBand.HIGH

    def test_to_dict_includes_expected_keys(self):
        ref = EvidenceReference(evidence_id="EV-010")
        f = make_finding(confidence=0.7, evidence_references=[ref])
        d = f.to_dict()
        assert "finding_id" in d
        assert "plugin_id" in d
        assert d["severity"] == "warning"
        assert isinstance(d["evidence_references"], list)
        assert len(d["evidence_references"]) == 1
        assert d["confidence_scope"] == "finding_analysis"
        assert "confidence_band" in d

    def test_from_dict_roundtrip_severity_becomes_enum(self):
        f = make_finding()
        d = f.to_dict()
        restored = ForensicFinding.from_dict(d)
        assert restored.severity is FindingSeverity.WARNING
        assert isinstance(restored.severity, FindingSeverity)

    def test_from_dict_roundtrip_evidence_references_deserialized(self):
        ref = EvidenceReference(
            evidence_id="EV-020",
            stream_name="gps",
            support_summary="GPS signal lost.",
        )
        f = make_finding(evidence_references=[ref])
        d = f.to_dict()
        restored = ForensicFinding.from_dict(d)
        assert len(restored.evidence_references) == 1
        assert isinstance(restored.evidence_references[0], EvidenceReference)
        assert restored.evidence_references[0].evidence_id == "EV-020"
        assert restored.evidence_references[0].stream_name == "gps"

    def test_from_dict_ignores_unknown_keys(self):
        f = make_finding()
        d = f.to_dict()
        d["future_field_v2"] = "should not raise"
        restored = ForensicFinding.from_dict(d)
        assert restored.finding_id == f.finding_id

    def test_to_json_produces_valid_json(self):
        f = make_finding()
        raw = f.to_json()
        parsed = json.loads(raw)
        assert parsed["finding_id"] == "F-001"

    def test_generated_at_is_datetime(self):
        f = make_finding()
        assert isinstance(f.generated_at, datetime)


# ---------------------------------------------------------------------------
# TestHypothesis
# ---------------------------------------------------------------------------

class TestHypothesis:
    def _make_hypothesis(self, **kwargs) -> Hypothesis:
        defaults = dict(
            hypothesis_id="H-001",
            statement="Battery failure caused the crash.",
        )
        defaults.update(kwargs)
        return Hypothesis(**defaults)

    def test_required_fields_present(self):
        h = self._make_hypothesis()
        assert h.hypothesis_id == "H-001"
        assert h.statement == "Battery failure caused the crash."

    def test_confidence_scope_default_is_hypothesis_root_cause(self):
        h = self._make_hypothesis()
        assert h.confidence_scope == "hypothesis_root_cause"

    def test_status_defaults_to_candidate(self):
        h = self._make_hypothesis()
        assert h.status is HypothesisStatus.CANDIDATE

    def test_confidence_band_property(self):
        h = self._make_hypothesis(confidence=0.55)
        assert h.confidence_band is ConfidenceBand.MEDIUM
        assert h.confidence_band is ConfidenceBand.from_score(0.55)

    def test_to_dict_includes_expected_keys(self):
        h = self._make_hypothesis(
            supporting_finding_ids=["F-001", "F-002"],
            contradicting_finding_ids=["F-003"],
            confidence=0.6,
        )
        d = h.to_dict()
        assert d["hypothesis_id"] == "H-001"
        assert d["status"] == "candidate"
        assert d["confidence_scope"] == "hypothesis_root_cause"
        assert d["supporting_finding_ids"] == ["F-001", "F-002"]
        assert d["contradicting_finding_ids"] == ["F-003"]

    def test_from_dict_roundtrip_status_becomes_enum(self):
        h = self._make_hypothesis(status=HypothesisStatus.SUPPORTED)
        d = h.to_dict()
        restored = Hypothesis.from_dict(d)
        assert restored.status is HypothesisStatus.SUPPORTED
        assert isinstance(restored.status, HypothesisStatus)

    def test_from_dict_ignores_unknown_keys(self):
        h = self._make_hypothesis()
        d = h.to_dict()
        d["future_field_v2"] = "should not raise"
        restored = Hypothesis.from_dict(d)
        assert restored.hypothesis_id == "H-001"

    def test_to_json_produces_valid_json(self):
        h = self._make_hypothesis()
        raw = h.to_json()
        parsed = json.loads(raw)
        assert parsed["hypothesis_id"] == "H-001"


# ---------------------------------------------------------------------------
# TestConfidenceScopeDistinction
# ---------------------------------------------------------------------------

class TestConfidenceScopeDistinction:
    """Verify that the three confidence scopes in the system are explicit and distinct.

    This is a forensic integrity check — parser/finding/hypothesis confidence
    must never be conflated.
    """

    def test_parse_diagnostics_confidence_scope(self):
        diag = ParseDiagnostics()
        assert diag.confidence_scope == "parser_parse_quality"

    def test_forensic_finding_confidence_scope(self):
        f = make_finding()
        assert f.confidence_scope == "finding_analysis"

    def test_hypothesis_confidence_scope(self):
        h = Hypothesis(hypothesis_id="H-X", statement="Test hypothesis.")
        assert h.confidence_scope == "hypothesis_root_cause"

    def test_all_three_scopes_are_distinct(self):
        diag = ParseDiagnostics()
        f = make_finding()
        h = Hypothesis(hypothesis_id="H-X", statement="Test hypothesis.")
        scopes = {diag.confidence_scope, f.confidence_scope, h.confidence_scope}
        assert len(scopes) == 3, (
            f"Expected 3 distinct confidence scopes, got {len(scopes)}: {scopes}"
        )
