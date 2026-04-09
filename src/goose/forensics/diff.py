"""Run diff engine for Goose-Core.

Advanced Forensic Validation Sprint — Structured comparison of analysis runs.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from goose.forensics.replay import FindingDifference, _diff_findings


@dataclass
class PluginExecutionDifference:
    plugin_id: str
    change: str  # "added", "removed", "status_changed", "version_changed", "trust_changed"
    original_status: str | None = None  # "ran", "skipped", "blocked"
    replay_status: str | None = None
    original_version: str | None = None
    replay_version: str | None = None
    findings_delta: int = 0  # replay_count - original_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "change": self.change,
            "original_status": self.original_status,
            "replay_status": self.replay_status,
            "original_version": self.original_version,
            "replay_version": self.replay_version,
            "findings_delta": self.findings_delta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PluginExecutionDifference:
        known = {
            "plugin_id", "change", "original_status", "replay_status",
            "original_version", "replay_version", "findings_delta",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class DiagnosticsDifference:
    parser_confidence_delta: float | None = None
    warnings_added: list[str] = field(default_factory=list)
    warnings_removed: list[str] = field(default_factory=list)
    missing_streams_delta: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parser_confidence_delta": self.parser_confidence_delta,
            "warnings_added": self.warnings_added,
            "warnings_removed": self.warnings_removed,
            "missing_streams_delta": self.missing_streams_delta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DiagnosticsDifference:
        known = {
            "parser_confidence_delta", "warnings_added",
            "warnings_removed", "missing_streams_delta",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class HypothesisDifference:
    theme: str
    change: str  # "added", "removed", "confidence_changed"
    original_confidence: float | None = None
    replay_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "change": self.change,
            "original_confidence": self.original_confidence,
            "replay_confidence": self.replay_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HypothesisDifference:
        known = {"theme", "change", "original_confidence", "replay_confidence"}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class RunComparison:
    comparison_id: str
    case_id: str
    run_a_id: str
    run_b_id: str
    compared_at: str
    finding_differences: list[FindingDifference] = field(default_factory=list)
    plugin_differences: list[PluginExecutionDifference] = field(default_factory=list)
    diagnostics_difference: DiagnosticsDifference | None = None
    hypothesis_differences: list[HypothesisDifference] = field(default_factory=list)
    tuning_profile_changed: bool = False
    parser_version_changed: bool = False
    plugin_versions_changed: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def has_differences(self) -> bool:
        return bool(
            self.finding_differences
            or self.plugin_differences
            or self.hypothesis_differences
            or self.tuning_profile_changed
            or self.parser_version_changed
            or self.plugin_versions_changed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "case_id": self.case_id,
            "run_a_id": self.run_a_id,
            "run_b_id": self.run_b_id,
            "compared_at": self.compared_at,
            "finding_differences": [f.to_dict() for f in self.finding_differences],
            "plugin_differences": [p.to_dict() for p in self.plugin_differences],
            "diagnostics_difference": self.diagnostics_difference.to_dict() if self.diagnostics_difference else None,
            "hypothesis_differences": [h.to_dict() for h in self.hypothesis_differences],
            "tuning_profile_changed": self.tuning_profile_changed,
            "parser_version_changed": self.parser_version_changed,
            "plugin_versions_changed": self.plugin_versions_changed,
            "summary": self.summary,
            "has_differences": self.has_differences,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunComparison:
        d = dict(d)
        d["finding_differences"] = [
            FindingDifference.from_dict(f) for f in d.get("finding_differences", [])
        ]
        d["plugin_differences"] = [
            PluginExecutionDifference.from_dict(p) for p in d.get("plugin_differences", [])
        ]
        dd = d.get("diagnostics_difference")
        d["diagnostics_difference"] = DiagnosticsDifference.from_dict(dd) if dd else None
        d["hypothesis_differences"] = [
            HypothesisDifference.from_dict(h) for h in d.get("hypothesis_differences", [])
        ]
        known = {
            "comparison_id", "case_id", "run_a_id", "run_b_id", "compared_at",
            "finding_differences", "plugin_differences", "diagnostics_difference",
            "hypothesis_differences", "tuning_profile_changed",
            "parser_version_changed", "plugin_versions_changed", "summary",
        }
        return cls(**{k: v for k, v in d.items() if k in known})


def compare_runs(case_dir: Path, run_a_id: str, run_b_id: str) -> RunComparison:
    """Load artifacts for two runs and produce a structured diff.

    For same-run comparison (run_a == run_b), returns empty differences.
    """
    comparison_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
    case_json_path = case_dir / "case.json"

    case_data: dict[str, Any] = {}
    if case_json_path.exists():
        case_data = json.loads(case_json_path.read_text(encoding="utf-8"))

    case_id = case_data.get("case_id", "")
    runs = case_data.get("analysis_runs", [])

    run_a = next((r for r in runs if r.get("run_id") == run_a_id), None)
    run_b = next((r for r in runs if r.get("run_id") == run_b_id), None)

    analysis_dir = case_dir / "analysis"

    # Load findings for each run
    # Note: Current system stores findings.json for the latest run only.
    # We compare based on what's available.
    findings_a = _load_run_findings(analysis_dir, run_a_id)
    findings_b = _load_run_findings(analysis_dir, run_b_id)

    hyps_a = _load_run_hypotheses(analysis_dir, run_a_id)
    hyps_b = _load_run_hypotheses(analysis_dir, run_b_id)

    # Same-run comparison: short-circuit
    if run_a_id == run_b_id:
        return RunComparison(
            comparison_id=comparison_id,
            case_id=case_id,
            run_a_id=run_a_id,
            run_b_id=run_b_id,
            compared_at=datetime.now().isoformat(),
            summary="Same run compared — no differences.",
        )

    # Finding differences
    added, removed, changed = _diff_findings(findings_a, findings_b)
    finding_diffs: list[FindingDifference] = list(changed)
    for fid in added:
        finding_diffs.append(FindingDifference(
            finding_id=fid, change_type="added",
            replay_value=next((f for f in findings_b if f.get("finding_id", f.get("title")) == fid), None),
        ))
    for fid in removed:
        finding_diffs.append(FindingDifference(
            finding_id=fid, change_type="removed",
            original_value=next((f for f in findings_a if f.get("finding_id", f.get("title")) == fid), None),
        ))

    # Plugin differences
    plugin_diffs: list[PluginExecutionDifference] = []
    vers_a = (run_a or {}).get("plugin_versions", {})
    vers_b = (run_b or {}).get("plugin_versions", {})
    all_plugin_ids = set(list(vers_a.keys()) + list(vers_b.keys()))
    versions_changed: list[str] = []

    for pid in sorted(all_plugin_ids):
        va = vers_a.get(pid)
        vb = vers_b.get(pid)
        if va and not vb:
            plugin_diffs.append(PluginExecutionDifference(
                plugin_id=pid, change="removed",
                original_version=va, original_status="ran",
            ))
        elif vb and not va:
            plugin_diffs.append(PluginExecutionDifference(
                plugin_id=pid, change="added",
                replay_version=vb, replay_status="ran",
            ))
        elif va != vb:
            plugin_diffs.append(PluginExecutionDifference(
                plugin_id=pid, change="version_changed",
                original_version=va, replay_version=vb,
            ))
            versions_changed.append(pid)

    # Hypothesis differences
    hyp_diffs: list[HypothesisDifference] = []
    hyp_a_themes = {h.get("theme", h.get("statement", "")): h for h in hyps_a}
    hyp_b_themes = {h.get("theme", h.get("statement", "")): h for h in hyps_b}

    for theme in sorted(set(hyp_b_themes) - set(hyp_a_themes)):
        hyp_diffs.append(HypothesisDifference(
            theme=theme, change="added",
            replay_confidence=hyp_b_themes[theme].get("confidence"),
        ))
    for theme in sorted(set(hyp_a_themes) - set(hyp_b_themes)):
        hyp_diffs.append(HypothesisDifference(
            theme=theme, change="removed",
            original_confidence=hyp_a_themes[theme].get("confidence"),
        ))
    for theme in sorted(set(hyp_a_themes) & set(hyp_b_themes)):
        ca = hyp_a_themes[theme].get("confidence")
        cb = hyp_b_themes[theme].get("confidence")
        if ca != cb:
            hyp_diffs.append(HypothesisDifference(
                theme=theme, change="confidence_changed",
                original_confidence=ca, replay_confidence=cb,
            ))

    # Tuning profile
    tp_a = (run_a or {}).get("tuning_profile") or "default"
    tp_b = (run_b or {}).get("tuning_profile") or "default"
    tuning_changed = tp_a != tp_b

    # Parser version
    engine_a = (run_a or {}).get("engine_version", "")
    engine_b = (run_b or {}).get("engine_version", "")
    parser_changed = engine_a != engine_b  # approximate; parser version tied to engine

    # Summary
    parts: list[str] = []
    if finding_diffs:
        parts.append(f"{len(finding_diffs)} finding difference(s)")
    if plugin_diffs:
        parts.append(f"{len(plugin_diffs)} plugin difference(s)")
    if hyp_diffs:
        parts.append(f"{len(hyp_diffs)} hypothesis difference(s)")
    if tuning_changed:
        parts.append("tuning profile changed")
    summary = "; ".join(parts) if parts else "No differences detected."

    return RunComparison(
        comparison_id=comparison_id,
        case_id=case_id,
        run_a_id=run_a_id,
        run_b_id=run_b_id,
        compared_at=datetime.now().isoformat(),
        finding_differences=finding_diffs,
        plugin_differences=plugin_diffs,
        hypothesis_differences=hyp_diffs,
        tuning_profile_changed=tuning_changed,
        parser_version_changed=parser_changed,
        plugin_versions_changed=versions_changed,
        summary=summary,
    )


def _load_run_findings(analysis_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """Load findings for a specific run.

    Prefers the run-specific archive ``findings_{run_id}.json`` written since
    Convergence Sprint 1.  Falls back to ``findings.json`` only when the
    run_id matches (covers pre-sprint cases that only have the latest pointer).
    """
    # Preferred: run-specific file (written for every run since CS-1)
    specific_path = analysis_dir / f"findings_{run_id}.json"
    if specific_path.exists():
        try:
            bundle = json.loads(specific_path.read_text(encoding="utf-8"))
            return bundle.get("findings", [])
        except Exception:
            pass

    # Fallback: shared pointer only when it matches the requested run_id
    fallback_path = analysis_dir / "findings.json"
    if fallback_path.exists():
        try:
            bundle = json.loads(fallback_path.read_text(encoding="utf-8"))
            if bundle.get("run_id") == run_id:
                return bundle.get("findings", [])
        except Exception:
            pass
    return []


def _load_run_hypotheses(analysis_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """Load hypotheses for a specific run.

    Prefers the run-specific archive ``hypotheses_{run_id}.json``.
    Falls back to ``hypotheses.json`` only when run_id matches.
    """
    specific_path = analysis_dir / f"hypotheses_{run_id}.json"
    if specific_path.exists():
        try:
            bundle = json.loads(specific_path.read_text(encoding="utf-8"))
            return bundle.get("hypotheses", [])
        except Exception:
            pass

    hyp_path = analysis_dir / "hypotheses.json"
    if hyp_path.exists():
        try:
            bundle = json.loads(hyp_path.read_text(encoding="utf-8"))
            if bundle.get("run_id") == run_id:
                return bundle.get("hypotheses", [])
        except Exception:
            pass
    return []
