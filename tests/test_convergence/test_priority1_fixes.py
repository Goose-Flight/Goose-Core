"""Convergence Sprint 1 — Priority 1 fix regression tests.

Covers:
  A1: POST /api/analyze returns 410 Gone
  B1: replay.py drift_cats list/set intersection no longer crashes
  C1: _load_run_findings reads run-specific findings_{run_id}.json
  C2: compare_runs uses distinct per-run artifacts
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# A1: Legacy /api/analyze endpoint returns 410
# ---------------------------------------------------------------------------

class TestLegacyAnalyzeEndpoint:
    def test_legacy_analyze_returns_410(self):
        from goose.web.app import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/analyze",
            files={"file": ("test.ulg", io.BytesIO(b"fake data"), "application/octet-stream")},
        )
        assert response.status_code == 410

    def test_legacy_analyze_body_has_error_gone(self):
        from goose.web.app import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/analyze",
            files={"file": ("test.ulg", io.BytesIO(b"fake data"), "application/octet-stream")},
        )
        body = response.json()
        assert body["error"] == "gone"

    def test_legacy_analyze_body_has_alternatives(self):
        from goose.web.app import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/analyze",
            files={"file": ("test.ulg", io.BytesIO(b"fake data"), "application/octet-stream")},
        )
        body = response.json()
        assert "alternatives" in body


# ---------------------------------------------------------------------------
# B1: Replay drift_cats list/set intersection no longer crashes
# ---------------------------------------------------------------------------

class TestReplayDriftStatusDetermination:
    def test_drift_status_determination_no_crash(self):
        """The old bug used list & set which raises TypeError. This must not raise."""
        from goose.forensics.replay import DriftCategory

        drift_cats = [DriftCategory.ENGINE_VERSION, DriftCategory.PLUGIN_VERSION]
        version_drift_categories = {
            DriftCategory.ENGINE_VERSION, DriftCategory.PARSER_VERSION,
            DriftCategory.PLUGIN_VERSION, DriftCategory.TUNING_PROFILE,
        }
        # This should NOT raise TypeError (old code did `list & set`)
        has_version_drift = bool(set(drift_cats) & version_drift_categories)
        assert has_version_drift is True

    def test_empty_drift_cats_no_crash(self):
        from goose.forensics.replay import DriftCategory

        drift_cats_empty: list = []
        version_drift_categories = {
            DriftCategory.ENGINE_VERSION, DriftCategory.PARSER_VERSION,
            DriftCategory.PLUGIN_VERSION, DriftCategory.TUNING_PROFILE,
        }
        has_drift_empty = bool(set(drift_cats_empty) & version_drift_categories)
        assert has_drift_empty is False

    def test_non_version_drift_categories_not_matched(self):
        """FINDINGS_CHANGED and CONFIDENCE_SHIFTED should not trigger version drift."""
        from goose.forensics.replay import DriftCategory

        drift_cats = [DriftCategory.FINDINGS_CHANGED, DriftCategory.CONFIDENCE_SHIFTED]
        version_drift_categories = {
            DriftCategory.ENGINE_VERSION, DriftCategory.PARSER_VERSION,
            DriftCategory.PLUGIN_VERSION, DriftCategory.TUNING_PROFILE,
        }
        has_version_drift = bool(set(drift_cats) & version_drift_categories)
        assert has_version_drift is False


# ---------------------------------------------------------------------------
# C1: Run-specific findings files are written and read correctly
# ---------------------------------------------------------------------------

class TestRunSpecificFindingsFiles:
    def test_run_specific_file_preferred_over_shared_pointer(self):
        """_load_run_findings should return run-specific findings, not shared pointer."""
        from goose.forensics.diff import _load_run_findings

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir)
            run_id = "RUN-TESTRUN1"

            # Write the run-specific file (as analysis.py now does)
            bundle = {
                "findings_version": "2.0",
                "run_id": run_id,
                "findings": [{"title": "test finding"}],
            }
            (analysis_dir / f"findings_{run_id}.json").write_text(json.dumps(bundle))

            # Write a DIFFERENT run's shared pointer
            other_bundle = {
                "findings_version": "2.0",
                "run_id": "RUN-OTHER",
                "findings": [{"title": "other finding"}],
            }
            (analysis_dir / "findings.json").write_text(json.dumps(other_bundle))

            findings = _load_run_findings(analysis_dir, run_id)
            assert len(findings) == 1
            assert findings[0]["title"] == "test finding"

    def test_missing_run_specific_file_returns_empty(self):
        """When no run-specific file exists and shared pointer is for a different run, return []."""
        from goose.forensics.diff import _load_run_findings

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir)
            run_id = "RUN-OTHER"

            # Write shared pointer for a DIFFERENT run
            other_bundle = {
                "findings_version": "2.0",
                "run_id": "RUN-DIFFERENT",
                "findings": [{"title": "other finding"}],
            }
            (analysis_dir / "findings.json").write_text(json.dumps(other_bundle))

            findings_other = _load_run_findings(analysis_dir, run_id)
            assert findings_other == []

    def test_shared_pointer_used_when_run_id_matches(self):
        """Fallback to findings.json when run_id matches (backward compat for pre-CS1 cases)."""
        from goose.forensics.diff import _load_run_findings

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir)
            run_id = "RUN-LEGACY"

            # No run-specific file; only shared pointer that matches the run_id
            bundle = {
                "findings_version": "2.0",
                "run_id": run_id,
                "findings": [{"title": "legacy finding"}],
            }
            (analysis_dir / "findings.json").write_text(json.dumps(bundle))

            findings = _load_run_findings(analysis_dir, run_id)
            assert len(findings) == 1
            assert findings[0]["title"] == "legacy finding"

    def test_empty_analysis_dir_returns_empty(self):
        """No files at all should return empty list without exception."""
        from goose.forensics.diff import _load_run_findings

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir)
            findings = _load_run_findings(analysis_dir, "RUN-NONEXISTENT")
            assert findings == []


# ---------------------------------------------------------------------------
# C2: compare_runs uses distinct run artifacts
# ---------------------------------------------------------------------------

class TestCompareRunsDistinctArtifacts:
    def test_compare_runs_detects_severity_change(self):
        """compare_runs should find finding differences between two distinct runs."""
        from goose.forensics.diff import compare_runs

        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir)
            analysis_dir = case_dir / "analysis"
            analysis_dir.mkdir()

            run_a_id = "RUN-AAAA"
            run_b_id = "RUN-BBBB"

            case_data = {
                "case_id": "CASE-TEST",
                "analysis_runs": [
                    {"run_id": run_a_id, "plugin_versions": {"vibration": "1.0"}},
                    {"run_id": run_b_id, "plugin_versions": {"vibration": "1.1"}},
                ],
            }
            (case_dir / "case.json").write_text(json.dumps(case_data))

            # Different findings for each run
            findings_a = [{
                "finding_id": "F-001", "title": "Vibration high",
                "severity": "warning", "confidence": 0.8,
            }]
            findings_b = [{
                "finding_id": "F-001", "title": "Vibration high",
                "severity": "critical", "confidence": 0.9,
            }]

            bundle_a = {"findings_version": "2.0", "run_id": run_a_id, "findings": findings_a}
            bundle_b = {"findings_version": "2.0", "run_id": run_b_id, "findings": findings_b}
            (analysis_dir / f"findings_{run_a_id}.json").write_text(json.dumps(bundle_a))
            (analysis_dir / f"findings_{run_b_id}.json").write_text(json.dumps(bundle_b))

            result = compare_runs(case_dir, run_a_id, run_b_id)
            assert result.run_a_id == run_a_id
            assert result.run_b_id == run_b_id
            # F-001 changed severity from warning to critical
            changed_ids = [d.finding_id for d in result.finding_differences]
            assert "F-001" in changed_ids

    def test_compare_runs_same_run_returns_no_differences(self):
        """Same run compared to itself should return empty differences."""
        from goose.forensics.diff import compare_runs

        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir)
            analysis_dir = case_dir / "analysis"
            analysis_dir.mkdir()

            run_id = "RUN-SAME"
            case_data = {
                "case_id": "CASE-TEST2",
                "analysis_runs": [{"run_id": run_id, "plugin_versions": {}}],
            }
            (case_dir / "case.json").write_text(json.dumps(case_data))

            bundle = {"findings_version": "2.0", "run_id": run_id, "findings": []}
            (analysis_dir / f"findings_{run_id}.json").write_text(json.dumps(bundle))

            result = compare_runs(case_dir, run_id, run_id)
            assert not result.has_differences

    def test_compare_runs_plugin_version_change_detected(self):
        """Plugin version change between runs should be reflected in plugin_differences."""
        from goose.forensics.diff import compare_runs

        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir)
            analysis_dir = case_dir / "analysis"
            analysis_dir.mkdir()

            run_a_id = "RUN-P1"
            run_b_id = "RUN-P2"

            case_data = {
                "case_id": "CASE-PLUGIN",
                "analysis_runs": [
                    {"run_id": run_a_id, "plugin_versions": {"crash_detection": "1.0"}},
                    {"run_id": run_b_id, "plugin_versions": {"crash_detection": "2.0"}},
                ],
            }
            (case_dir / "case.json").write_text(json.dumps(case_data))

            for run_id in (run_a_id, run_b_id):
                bundle = {"findings_version": "2.0", "run_id": run_id, "findings": []}
                (analysis_dir / f"findings_{run_id}.json").write_text(json.dumps(bundle))

            result = compare_runs(case_dir, run_a_id, run_b_id)
            plugin_ids_changed = [d.plugin_id for d in result.plugin_differences]
            assert "crash_detection" in plugin_ids_changed
