"""Tests for RunComparison persistence (save/load/list/find).

Option C — Sprint 3 Phase 5: comparison_id is now stable across calls.
Verifies that save_comparison, list_comparisons, load_comparison, and
find_comparison all work correctly and that compare_runs → save → load
round-trips cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

from goose.forensics.diff import (
    RunComparison,
    compare_runs,
    find_comparison,
    list_comparisons,
    load_comparison,
    save_comparison,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_comparison(
    case_id: str = "CASE-001",
    run_a: str = "RUN-AAAA",
    run_b: str = "RUN-BBBB",
    comparison_id: str = "CMP-TESTTEST",
) -> RunComparison:
    return RunComparison(
        comparison_id=comparison_id,
        case_id=case_id,
        run_a_id=run_a,
        run_b_id=run_b,
        compared_at="2026-04-09T12:00:00",
        summary="No differences detected.",
        risk_assessment="stable",
    )


def _make_case_dir(tmp_path: Path) -> Path:
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    return case_dir


# ---------------------------------------------------------------------------
# save_comparison
# ---------------------------------------------------------------------------

def test_save_comparison_creates_file(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison()

    saved_path = save_comparison(case_dir, comp)

    assert saved_path.exists()
    assert saved_path.name == f"{comp.comparison_id}.json"
    data = json.loads(saved_path.read_text(encoding="utf-8"))
    assert data["comparison_id"] == comp.comparison_id
    assert data["run_a_id"] == "RUN-AAAA"


def test_save_comparison_creates_comparisons_dir(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison()
    save_comparison(case_dir, comp)
    assert (case_dir / "comparisons").is_dir()


def test_save_comparison_creates_index(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison()
    save_comparison(case_dir, comp)

    index_path = case_dir / "comparisons" / "index.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text(encoding="utf-8"))
    entries = data["comparisons"]
    assert len(entries) == 1
    assert entries[0]["comparison_id"] == comp.comparison_id


def test_save_comparison_upserts_existing_id(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison(comparison_id="CMP-SAME")
    save_comparison(case_dir, comp)

    # Save again with same ID (e.g. enriched version)
    comp2 = _minimal_comparison(comparison_id="CMP-SAME", run_b="RUN-CCCC")
    save_comparison(case_dir, comp2)

    entries = list_comparisons(case_dir)
    # Should still be only 1 entry, not 2
    same_entries = [e for e in entries if e["comparison_id"] == "CMP-SAME"]
    assert len(same_entries) == 1


def test_save_multiple_comparisons_index_accumulates(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    for i in range(3):
        comp = _minimal_comparison(comparison_id=f"CMP-{i:04d}")
        save_comparison(case_dir, comp)

    entries = list_comparisons(case_dir)
    assert len(entries) == 3


# ---------------------------------------------------------------------------
# list_comparisons
# ---------------------------------------------------------------------------

def test_list_comparisons_empty_when_no_dir(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    entries = list_comparisons(case_dir)
    assert entries == []


def test_list_comparisons_sorted_newest_first(tmp_path):
    case_dir = _make_case_dir(tmp_path)

    # Older comparison
    comp_old = RunComparison(
        comparison_id="CMP-OLD",
        case_id="CASE-001",
        run_a_id="RUN-A",
        run_b_id="RUN-B",
        compared_at="2026-04-09T10:00:00",
        summary="old",
        risk_assessment="stable",
    )
    # Newer comparison
    comp_new = RunComparison(
        comparison_id="CMP-NEW",
        case_id="CASE-001",
        run_a_id="RUN-C",
        run_b_id="RUN-D",
        compared_at="2026-04-09T15:00:00",
        summary="new",
        risk_assessment="stable",
    )

    save_comparison(case_dir, comp_old)
    save_comparison(case_dir, comp_new)

    entries = list_comparisons(case_dir)
    assert len(entries) == 2
    assert entries[0]["comparison_id"] == "CMP-NEW"   # newest first
    assert entries[1]["comparison_id"] == "CMP-OLD"


def test_list_comparisons_includes_summary_fields(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison()
    save_comparison(case_dir, comp)

    entries = list_comparisons(case_dir)
    entry = entries[0]
    assert "comparison_id" in entry
    assert "run_a_id" in entry
    assert "run_b_id" in entry
    assert "compared_at" in entry
    assert "risk_assessment" in entry
    assert "summary" in entry
    assert "has_differences" in entry


# ---------------------------------------------------------------------------
# load_comparison
# ---------------------------------------------------------------------------

def test_load_comparison_returns_none_for_missing_id(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    result = load_comparison(case_dir, "CMP-DOESNOTEXIST")
    assert result is None


def test_load_comparison_round_trips(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison()
    save_comparison(case_dir, comp)

    loaded = load_comparison(case_dir, comp.comparison_id)
    assert loaded is not None
    assert loaded.comparison_id == comp.comparison_id
    assert loaded.run_a_id == comp.run_a_id
    assert loaded.run_b_id == comp.run_b_id
    assert loaded.case_id == comp.case_id
    assert loaded.risk_assessment == comp.risk_assessment
    assert loaded.summary == comp.summary


def test_load_comparison_handles_corrupted_file(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp_dir = case_dir / "comparisons"
    comp_dir.mkdir()
    bad_file = comp_dir / "CMP-BAD.json"
    bad_file.write_text("not valid json {{{", encoding="utf-8")

    result = load_comparison(case_dir, "CMP-BAD")
    assert result is None  # never raises


# ---------------------------------------------------------------------------
# find_comparison
# ---------------------------------------------------------------------------

def test_find_comparison_returns_none_when_no_match(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    result = find_comparison(case_dir, "RUN-A", "RUN-B")
    assert result is None


def test_find_comparison_finds_by_run_pair(tmp_path):
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison(run_a="RUN-A", run_b="RUN-B")
    save_comparison(case_dir, comp)

    result = find_comparison(case_dir, "RUN-A", "RUN-B")
    assert result is not None
    assert result.comparison_id == comp.comparison_id


def test_find_comparison_is_order_insensitive(tmp_path):
    """find_comparison should match (B, A) when (A, B) was saved."""
    case_dir = _make_case_dir(tmp_path)
    comp = _minimal_comparison(run_a="RUN-A", run_b="RUN-B")
    save_comparison(case_dir, comp)

    result = find_comparison(case_dir, "RUN-B", "RUN-A")
    assert result is not None
    assert result.comparison_id == comp.comparison_id


def test_find_comparison_returns_newest_when_multiple_matches(tmp_path):
    case_dir = _make_case_dir(tmp_path)

    comp_old = RunComparison(
        comparison_id="CMP-OLD",
        case_id="CASE-001",
        run_a_id="RUN-A",
        run_b_id="RUN-B",
        compared_at="2026-04-09T10:00:00",
        summary="",
        risk_assessment="stable",
    )
    comp_new = RunComparison(
        comparison_id="CMP-NEW",
        case_id="CASE-001",
        run_a_id="RUN-A",
        run_b_id="RUN-B",
        compared_at="2026-04-09T11:00:00",
        summary="",
        risk_assessment="improvement",
    )
    save_comparison(case_dir, comp_old)
    save_comparison(case_dir, comp_new)

    result = find_comparison(case_dir, "RUN-A", "RUN-B")
    assert result is not None
    assert result.comparison_id == "CMP-NEW"  # newest returned


# ---------------------------------------------------------------------------
# compare_runs + save round-trip (integration)
# ---------------------------------------------------------------------------

def test_compare_runs_produces_valid_comparison_that_round_trips(tmp_path):
    """compare_runs() → save_comparison() → load_comparison() round-trip."""
    case_dir = tmp_path / "CASE-INTEG"
    case_dir.mkdir()

    # No case.json or run artifacts — compare_runs handles missing gracefully
    comparison = compare_runs(case_dir, "RUN-X", "RUN-Y")
    assert comparison.run_a_id == "RUN-X"
    assert comparison.run_b_id == "RUN-Y"

    save_comparison(case_dir, comparison)
    loaded = load_comparison(case_dir, comparison.comparison_id)

    assert loaded is not None
    assert loaded.comparison_id == comparison.comparison_id
    assert loaded.run_a_id == "RUN-X"
    assert loaded.run_b_id == "RUN-Y"


def test_same_run_compare_is_persistable(tmp_path):
    """Same-run comparison (no diff) saves and loads correctly."""
    case_dir = tmp_path / "CASE-SAME"
    case_dir.mkdir()

    comparison = compare_runs(case_dir, "RUN-SAME", "RUN-SAME")
    assert not comparison.has_differences

    save_comparison(case_dir, comparison)
    loaded = load_comparison(case_dir, comparison.comparison_id)
    assert loaded is not None
    assert not loaded.has_differences


def test_list_comparisons_returns_index_fields_from_saved_compare_runs(tmp_path):
    """Full pipeline: compare_runs + save + list returns proper index entries."""
    case_dir = tmp_path / "CASE-PIPE"
    case_dir.mkdir()

    comp = compare_runs(case_dir, "RUN-1", "RUN-2")
    save_comparison(case_dir, comp)

    entries = list_comparisons(case_dir)
    assert len(entries) == 1
    e = entries[0]
    assert e["comparison_id"] == comp.comparison_id
    assert e["run_a_id"] == "RUN-1"
    assert e["run_b_id"] == "RUN-2"
    assert "risk_assessment" in e
    assert "has_differences" in e
