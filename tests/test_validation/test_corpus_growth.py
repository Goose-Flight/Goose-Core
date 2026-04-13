"""Corpus growth and profile-aware harness tests.

Part of the TuningProfile wiring + corpus growth sprint: verifies that the
validation corpus has grown beyond the initial 3 seeded cases, that every
corpus case loads cleanly, and that the harness threads tuning profile
identity through ``ValidationSummary``.
"""

from __future__ import annotations

from pathlib import Path

from goose.validation.corpus import load_corpus_manifest
from goose.validation.harness import (
    RegressionAlert,
    ValidationSummary,
    run_validation,
)

CORPUS_DIR = Path(__file__).parent.parent / "corpus"


# ---------------------------------------------------------------------------
# Corpus-growth guarantees
# ---------------------------------------------------------------------------


def test_corpus_has_at_least_ten_cases():
    """The corpus must have grown to at least 10 cases."""
    cases = load_corpus_manifest(CORPUS_DIR)
    assert len(cases) >= 10, f"Expected at least 10 corpus cases, found {len(cases)}"


def test_corpus_contains_required_new_cases():
    """Every new case from this sprint must be registered in the manifest."""
    cases = load_corpus_manifest(CORPUS_DIR)
    ids = {c.corpus_id for c in cases}
    required = {
        "CORPUS-battery-sag",
        "CORPUS-gps-degradation",
        "CORPUS-ekf-issue",
        "CORPUS-rc-signal-loss",
        "CORPUS-partial-log",
        "CORPUS-motor-saturation",
        "CORPUS-racer-profile",
    }
    missing = required - ids
    assert not missing, f"Missing required corpus cases: {sorted(missing)}"


def test_every_case_has_profile_field():
    """Every corpus case must expose a ``profile`` attribute, defaulting to 'default'."""
    cases = load_corpus_manifest(CORPUS_DIR)
    for c in cases:
        assert hasattr(c, "profile")
        assert isinstance(c.profile, str)
        assert c.profile  # non-empty


def test_racer_profile_case_uses_racer_profile():
    """CORPUS-racer-profile must opt into the racer profile."""
    cases = load_corpus_manifest(CORPUS_DIR)
    by_id = {c.corpus_id: c for c in cases}
    assert "CORPUS-racer-profile" in by_id
    assert by_id["CORPUS-racer-profile"].profile == "racer"


def test_every_case_evidence_file_exists():
    """Every manifest case must have its evidence file present on disk."""
    cases = load_corpus_manifest(CORPUS_DIR)
    for c in cases:
        evidence = CORPUS_DIR / "cases" / c.corpus_id / "evidence" / c.evidence_filename
        assert evidence.exists(), f"Evidence missing for {c.corpus_id}: {evidence}"


# ---------------------------------------------------------------------------
# Harness integration: profile-aware summary
# ---------------------------------------------------------------------------


def test_run_validation_records_tuning_profile_identity():
    """ValidationSummary must record tuning_profile_id and version."""
    cases_dir = Path.cwd() / "cases"
    summary = run_validation(CORPUS_DIR, cases_dir)
    assert isinstance(summary, ValidationSummary)
    assert summary.tuning_profile_id == "default"
    assert summary.tuning_profile_version
    # Must be a non-empty string
    assert isinstance(summary.tuning_profile_version, str)
    assert len(summary.tuning_profile_version) > 0


def test_run_validation_produces_results_for_all_active_cases():
    """Harness must produce one CorpusCaseResult per active case."""
    cases = load_corpus_manifest(CORPUS_DIR)
    active = [c for c in cases if c.active]
    cases_dir = Path.cwd() / "cases"
    summary = run_validation(CORPUS_DIR, cases_dir)
    assert summary.total_cases == len(active)
    assert len(summary.corpus_case_results) == len(active)


def test_run_validation_results_carry_profile_field():
    """Every CorpusCaseResult must carry the originating profile."""
    cases_dir = Path.cwd() / "cases"
    summary = run_validation(CORPUS_DIR, cases_dir)
    for r in summary.corpus_case_results:
        assert hasattr(r, "profile")
        assert isinstance(r.profile, str)
        assert r.profile


def test_regression_alerts_are_structured_objects():
    """Regression alerts must be RegressionAlert objects, not bare strings."""
    cases_dir = Path.cwd() / "cases"
    summary = run_validation(CORPUS_DIR, cases_dir)
    for alert in summary.regression_alerts:
        assert isinstance(alert, RegressionAlert)
        assert alert.corpus_id
        assert alert.severity in ("failure", "warning")


def test_validation_summary_roundtrip_preserves_tuning_profile():
    """ValidationSummary.to_dict() / from_dict() must round-trip profile info."""
    cases_dir = Path.cwd() / "cases"
    summary = run_validation(CORPUS_DIR, cases_dir)
    d = summary.to_dict()
    assert d["tuning_profile_id"] == summary.tuning_profile_id
    assert d["tuning_profile_version"] == summary.tuning_profile_version
    restored = ValidationSummary.from_dict(d)
    assert restored.tuning_profile_id == summary.tuning_profile_id
    assert restored.tuning_profile_version == summary.tuning_profile_version


def test_regression_alert_serialization_roundtrip():
    """RegressionAlert itself must round-trip through to_dict/from_dict."""
    alert = RegressionAlert(
        alert_id="REG-TEST",
        corpus_id="CORPUS-example",
        category="crash",
        severity="failure",
        message="Expected plugin did not run",
    )
    d = alert.to_dict()
    restored = RegressionAlert.from_dict(d)
    assert restored.alert_id == "REG-TEST"
    assert restored.severity == "failure"
    assert restored.message == "Expected plugin did not run"
