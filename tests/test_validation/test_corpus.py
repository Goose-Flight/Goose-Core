"""Tests for the validation corpus and harness.

Advanced Forensic Validation Sprint.
"""

from __future__ import annotations

from pathlib import Path

from goose.validation.corpus import (
    CorpusCase,
    ExpectedAnalyzerBehavior,
    ExpectedParserBehavior,
    load_corpus_manifest,
)
from goose.validation.harness import (
    CorpusCaseResult,
    ObservedOutcome,
    ValidationSummary,
    run_validation,
)
from goose.validation.quality import (
    AnalyzerQualityReport,
    AnalyzerQualitySnapshot,
    compute_quality_report,
)

CORPUS_DIR = Path(__file__).parent.parent / "corpus"


def test_corpus_dir_exists():
    assert CORPUS_DIR.exists()
    assert (CORPUS_DIR / "corpus_manifest.json").exists()


def test_load_corpus_manifest():
    cases = load_corpus_manifest(CORPUS_DIR)
    assert len(cases) >= 3
    ids = {c.corpus_id for c in cases}
    assert "CORPUS-normal-flight" in ids
    assert "CORPUS-crash" in ids
    assert "CORPUS-vibration-crash" in ids


def test_corpus_case_serialization_roundtrip():
    cc = CorpusCase(
        corpus_id="CORPUS-test",
        description="Test case",
        category="normal",
        evidence_filename="test.ulg",
        expected_parser=ExpectedParserBehavior(
            should_succeed=True,
            min_parser_confidence=0.5,
        ),
        expected_analyzers=[
            ExpectedAnalyzerBehavior(
                plugin_id="crash_detection",
                should_find=["crash"],
            )
        ],
    )
    d = cc.to_dict()
    restored = CorpusCase.from_dict(d)
    assert restored.corpus_id == "CORPUS-test"
    assert restored.expected_parser.min_parser_confidence == 0.5
    assert len(restored.expected_analyzers) == 1
    assert restored.expected_analyzers[0].plugin_id == "crash_detection"


def test_expected_parser_behavior_serialization():
    epb = ExpectedParserBehavior(
        should_succeed=True,
        expected_format="ulog",
        min_parser_confidence=0.75,
        expected_warnings=["gps missing"],
    )
    d = epb.to_dict()
    restored = ExpectedParserBehavior.from_dict(d)
    assert restored.min_parser_confidence == 0.75
    assert restored.expected_warnings == ["gps missing"]


def test_observed_outcome_serialization():
    oo = ObservedOutcome(
        corpus_id="CORPUS-test",
        parser_succeeded=True,
        parser_confidence=0.9,
        findings_found=["Crash detected: motor_failure"],
        plugins_ran=["crash_detection", "vibration"],
    )
    d = oo.to_dict()
    restored = ObservedOutcome.from_dict(d)
    assert restored.parser_confidence == 0.9
    assert len(restored.findings_found) == 1


def test_validation_summary_serialization():
    summary = ValidationSummary(
        validation_id="VAL-TEST",
        run_at="2026-01-01T00:00:00",
        engine_version="1.3.4",
        total_cases=3,
        passed=2,
        failed=1,
        warned=0,
    )
    d = summary.to_dict()
    restored = ValidationSummary.from_dict(d)
    assert restored.validation_id == "VAL-TEST"
    assert restored.total_cases == 3
    assert restored.passed == 2


def test_run_validation_against_real_corpus():
    """Smoke-test: run the harness against the seeded corpus."""
    cases_dir = Path.cwd() / "cases"
    summary = run_validation(CORPUS_DIR, cases_dir)
    assert summary.total_cases >= 1
    # At least the harness must produce a summary without crashing
    assert summary.validation_id.startswith("VAL-")
    assert summary.engine_version


def test_compute_quality_report_from_summary():
    summary = ValidationSummary(
        validation_id="VAL-QA",
        run_at="2026-01-01T00:00:00",
        engine_version="1.3.4",
        total_cases=1,
        passed=1,
        failed=0,
        warned=0,
        corpus_case_results=[
            CorpusCaseResult(
                corpus_id="CORPUS-normal",
                category="normal",
                passed=True,
                observed=ObservedOutcome(
                    corpus_id="CORPUS-normal",
                    parser_succeeded=True,
                    plugins_ran=["crash_detection"],
                ),
            )
        ],
    )
    report = compute_quality_report(summary)
    assert isinstance(report, AnalyzerQualityReport)
    assert report.validation_run_id == "VAL-QA"
    assert len(report.analyzers) >= 1


def test_analyzer_quality_snapshot_precision_recall():
    snap = AnalyzerQualitySnapshot(
        plugin_id="crash_detection",
        plugin_version="1.0.0",
        validation_run_id="VAL-1",
        true_positives=8,
        false_positives=2,
        false_negatives=2,
    )
    assert snap.precision == 0.8
    assert snap.recall == 0.8


def test_analyzer_quality_snapshot_precision_none_when_no_predictions():
    snap = AnalyzerQualitySnapshot(
        plugin_id="quiet_plugin",
        plugin_version="1.0.0",
        validation_run_id="VAL-1",
    )
    assert snap.precision is None
    assert snap.recall is None
