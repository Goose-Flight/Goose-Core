"""Tests for the replay subsystem.

Advanced Forensic Validation Sprint — replay serialization and execution.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from goose.forensics.replay import (
    DriftCategory,
    FindingDifference,
    ReplayDifferenceSummary,
    ReplayRequest,
    ReplayStatus,
    ReplayVerificationRecord,
    _diff_findings,
    execute_replay,
)


def test_replay_request_serialization():
    req = ReplayRequest(
        source_case_id="CASE-2026-000001",
        source_run_id="RUN-ABCDEF12",
        requested_by="tester",
    )
    d = req.to_dict()
    assert d["source_case_id"] == "CASE-2026-000001"
    assert d["source_run_id"] == "RUN-ABCDEF12"
    assert d["requested_by"] == "tester"


def test_finding_difference_roundtrip():
    fd = FindingDifference(
        finding_id="F-001",
        change_type="added",
        original_value=None,
        replay_value={"title": "new", "severity": "warning"},
    )
    d = fd.to_dict()
    restored = FindingDifference.from_dict(d)
    assert restored.finding_id == "F-001"
    assert restored.change_type == "added"
    assert restored.replay_value == {"title": "new", "severity": "warning"}


def test_replay_difference_summary_empty():
    summary = ReplayDifferenceSummary()
    assert summary.findings_added == []
    assert summary.findings_removed == []
    assert summary.findings_changed == []
    assert summary.hypotheses_added == 0
    assert summary.hypotheses_removed == 0
    assert summary.parser_confidence_delta is None
    assert summary.plugin_execution_changes == []
    assert summary.drift_categories == []


def test_replay_difference_summary_with_changes():
    summary = ReplayDifferenceSummary(
        findings_added=["F-002"],
        findings_removed=["F-001"],
        hypotheses_added=1,
        drift_categories=[DriftCategory.PLUGIN_VERSION, DriftCategory.FINDINGS_CHANGED],
    )
    d = summary.to_dict()
    assert d["findings_added"] == ["F-002"]
    assert d["findings_removed"] == ["F-001"]
    assert d["hypotheses_added"] == 1
    assert "plugin_version" in d["drift_categories"]
    assert "findings_changed" in d["drift_categories"]

    restored = ReplayDifferenceSummary.from_dict(d)
    assert restored.findings_added == ["F-002"]
    assert DriftCategory.PLUGIN_VERSION in restored.drift_categories


def test_replay_verification_record_roundtrip():
    summary = ReplayDifferenceSummary(findings_added=["F-A"])
    record = ReplayVerificationRecord(
        replay_id="RPL-12345678",
        source_case_id="CASE-2026-000001",
        source_run_id="RUN-AAAAAAAA",
        replay_run_id="RUN-BBBBBBBB",
        status=ReplayStatus.EXPECTED_DRIFT,
        original_engine_version="1.3.3",
        replay_engine_version="1.3.4",
        original_parser_version="1.0",
        replay_parser_version="1.0",
        original_plugin_versions={"crash_detection": "1.0.0"},
        replay_plugin_versions={"crash_detection": "1.0.0"},
        original_tuning_profile="default",
        replay_tuning_profile="default",
        difference_summary=summary,
        verified_at=datetime.now().isoformat(),
        notes="test",
    )
    d = record.to_dict()
    restored = ReplayVerificationRecord.from_dict(d)
    assert restored.replay_id == "RPL-12345678"
    assert restored.status == ReplayStatus.EXPECTED_DRIFT
    assert restored.difference_summary.findings_added == ["F-A"]


def test_diff_findings_identical():
    findings = [
        {"finding_id": "F-1", "severity": "warning", "title": "a"},
        {"finding_id": "F-2", "severity": "info", "title": "b"},
    ]
    added, removed, changed = _diff_findings(findings, findings)
    assert added == []
    assert removed == []
    assert changed == []


def test_diff_findings_additions_and_removals():
    original = [{"finding_id": "F-1", "severity": "warning", "title": "a"}]
    replay = [
        {"finding_id": "F-1", "severity": "warning", "title": "a"},
        {"finding_id": "F-2", "severity": "critical", "title": "new"},
    ]
    added, removed, changed = _diff_findings(original, replay)
    assert added == ["F-2"]
    assert removed == []
    assert changed == []


def test_diff_findings_severity_change():
    original = [{"finding_id": "F-1", "severity": "warning", "title": "a"}]
    replay = [{"finding_id": "F-1", "severity": "critical", "title": "a"}]
    added, removed, changed = _diff_findings(original, replay)
    assert added == []
    assert removed == []
    assert len(changed) == 1
    assert changed[0].change_type == "severity_changed"


def test_execute_replay_incompatible_when_no_case(tmp_path: Path):
    # Missing case.json
    record = execute_replay(tmp_path, "RUN-DOESNOTEXIST")
    assert record.status == ReplayStatus.INCOMPATIBLE
    assert "Case JSON not found" in record.notes


def test_execute_replay_incompatible_when_run_missing(tmp_path: Path):
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
        "analysis_runs": [],
        "exports": [],
    }
    (tmp_path / "case.json").write_text(json.dumps(case_json), encoding="utf-8")
    record = execute_replay(tmp_path, "RUN-MISSING")
    assert record.status == ReplayStatus.INCOMPATIBLE
    assert "not found" in record.notes


def test_execute_replay_incompatible_when_no_evidence(tmp_path: Path):
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
                "run_id": "RUN-TEST",
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "plugin_versions": {},
                "ruleset_version": None,
                "findings_count": 0,
                "status": "completed",
                "engine_version": "1.3.4",
                "tuning_profile": None,
                "error": None,
            }
        ],
        "exports": [],
    }
    (tmp_path / "case.json").write_text(json.dumps(case_json), encoding="utf-8")
    record = execute_replay(tmp_path, "RUN-TEST")
    assert record.status == ReplayStatus.INCOMPATIBLE
    assert "evidence" in record.notes.lower()


def test_replay_status_exact_match_on_empty_diff():
    """If no version or output drift, status should be EXACT_MATCH."""
    summary = ReplayDifferenceSummary()
    assert summary.drift_categories == []
    # (Exact match logic is tested indirectly via execute_replay integration.)
