"""Tests for the run diff engine.

Advanced Forensic Validation Sprint — RunComparison.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from goose.forensics.diff import (
    DiagnosticsDifference,
    HypothesisDifference,
    PluginExecutionDifference,
    RunComparison,
    compare_runs,
)


def test_plugin_execution_difference_serialization():
    ped = PluginExecutionDifference(
        plugin_id="crash_detection",
        change="version_changed",
        original_version="1.0.0",
        replay_version="1.1.0",
        findings_delta=2,
    )
    d = ped.to_dict()
    assert d["plugin_id"] == "crash_detection"
    assert d["change"] == "version_changed"
    restored = PluginExecutionDifference.from_dict(d)
    assert restored.original_version == "1.0.0"
    assert restored.replay_version == "1.1.0"
    assert restored.findings_delta == 2


def test_diagnostics_difference_serialization():
    dd = DiagnosticsDifference(
        parser_confidence_delta=-0.1,
        warnings_added=["new warn"],
        warnings_removed=["old warn"],
        missing_streams_delta=["gps"],
    )
    d = dd.to_dict()
    restored = DiagnosticsDifference.from_dict(d)
    assert restored.parser_confidence_delta == -0.1
    assert restored.warnings_added == ["new warn"]


def test_hypothesis_difference_serialization():
    hd = HypothesisDifference(
        theme="crash_cause",
        change="confidence_changed",
        original_confidence=0.5,
        replay_confidence=0.7,
    )
    d = hd.to_dict()
    restored = HypothesisDifference.from_dict(d)
    assert restored.theme == "crash_cause"
    assert restored.original_confidence == 0.5
    assert restored.replay_confidence == 0.7


def test_run_comparison_empty_is_not_different():
    rc = RunComparison(
        comparison_id="CMP-1",
        case_id="CASE-TEST",
        run_a_id="RUN-A",
        run_b_id="RUN-A",
        compared_at=datetime.now().isoformat(),
    )
    assert rc.has_differences is False


def test_run_comparison_with_findings_is_different():
    from goose.forensics.replay import FindingDifference
    rc = RunComparison(
        comparison_id="CMP-1",
        case_id="CASE-TEST",
        run_a_id="RUN-A",
        run_b_id="RUN-B",
        compared_at=datetime.now().isoformat(),
        finding_differences=[FindingDifference(finding_id="F-1", change_type="added")],
    )
    assert rc.has_differences is True


def test_run_comparison_serialization_roundtrip():
    from goose.forensics.replay import FindingDifference
    rc = RunComparison(
        comparison_id="CMP-2",
        case_id="CASE-TEST",
        run_a_id="RUN-A",
        run_b_id="RUN-B",
        compared_at=datetime.now().isoformat(),
        finding_differences=[FindingDifference(finding_id="F-1", change_type="added")],
        plugin_differences=[PluginExecutionDifference(plugin_id="p", change="version_changed")],
        tuning_profile_changed=True,
        plugin_versions_changed=["p"],
        summary="1 finding difference(s)",
    )
    d = rc.to_dict()
    restored = RunComparison.from_dict(d)
    assert restored.comparison_id == "CMP-2"
    assert len(restored.finding_differences) == 1
    assert len(restored.plugin_differences) == 1
    assert restored.tuning_profile_changed is True
    assert restored.plugin_versions_changed == ["p"]


def test_compare_runs_same_run_returns_no_diff(tmp_path: Path):
    """Comparing a run to itself must return has_differences=False."""
    case_json = {
        "case_id": "CASE-TEST",
        "created_at": datetime.now().isoformat(),
        "created_by": "test",
        "status": "open",
        "tags": [],
        "notes": "",
        "engine_version": "1.3.4",
        "ruleset_version": None,
        "plugin_policy_version": None,
        "evidence_items": [],
        "analysis_runs": [
            {
                "run_id": "RUN-A",
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "plugin_versions": {"crash_detection": "1.0.0"},
                "ruleset_version": None,
                "findings_count": 0,
                "status": "completed",
                "engine_version": "1.3.4",
                "tuning_profile": "default",
                "error": None,
            }
        ],
        "exports": [],
    }
    (tmp_path / "case.json").write_text(json.dumps(case_json), encoding="utf-8")
    comparison = compare_runs(tmp_path, "RUN-A", "RUN-A")
    assert comparison.has_differences is False


def test_compare_runs_detects_plugin_version_change(tmp_path: Path):
    case_json = {
        "case_id": "CASE-TEST",
        "created_at": datetime.now().isoformat(),
        "created_by": "test",
        "status": "open",
        "tags": [],
        "notes": "",
        "engine_version": "1.3.4",
        "ruleset_version": None,
        "plugin_policy_version": None,
        "evidence_items": [],
        "analysis_runs": [
            {
                "run_id": "RUN-A",
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "plugin_versions": {"crash_detection": "1.0.0"},
                "ruleset_version": None,
                "findings_count": 0,
                "status": "completed",
                "engine_version": "1.3.4",
                "tuning_profile": "default",
                "error": None,
            },
            {
                "run_id": "RUN-B",
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "plugin_versions": {"crash_detection": "1.1.0"},
                "ruleset_version": None,
                "findings_count": 0,
                "status": "completed",
                "engine_version": "1.3.4",
                "tuning_profile": "default",
                "error": None,
            },
        ],
        "exports": [],
    }
    (tmp_path / "case.json").write_text(json.dumps(case_json), encoding="utf-8")
    comparison = compare_runs(tmp_path, "RUN-A", "RUN-B")
    assert comparison.has_differences is True
    assert "crash_detection" in comparison.plugin_versions_changed
    assert any(p.change == "version_changed" for p in comparison.plugin_differences)


def test_compare_runs_detects_tuning_profile_change(tmp_path: Path):
    case_json = {
        "case_id": "CASE-TEST",
        "created_at": datetime.now().isoformat(),
        "created_by": "test",
        "status": "open",
        "tags": [],
        "notes": "",
        "engine_version": "1.3.4",
        "ruleset_version": None,
        "plugin_policy_version": None,
        "evidence_items": [],
        "analysis_runs": [
            {
                "run_id": "RUN-A",
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "plugin_versions": {},
                "ruleset_version": None,
                "findings_count": 0,
                "status": "completed",
                "engine_version": "1.3.4",
                "tuning_profile": "default",
                "error": None,
            },
            {
                "run_id": "RUN-B",
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "plugin_versions": {},
                "ruleset_version": None,
                "findings_count": 0,
                "status": "completed",
                "engine_version": "1.3.4",
                "tuning_profile": "aggressive",
                "error": None,
            },
        ],
        "exports": [],
    }
    (tmp_path / "case.json").write_text(json.dumps(case_json), encoding="utf-8")
    comparison = compare_runs(tmp_path, "RUN-A", "RUN-B")
    assert comparison.tuning_profile_changed is True
    assert comparison.has_differences is True
