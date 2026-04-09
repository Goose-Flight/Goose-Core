"""Analyzer quality tracking for Goose-Core.

Advanced Forensic Validation Sprint — Computes precision/recall metrics
from corpus validation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from goose.validation.harness import ValidationSummary


@dataclass
class AnalyzerQualitySnapshot:
    """Quality metrics for one analyzer across a corpus validation run."""

    plugin_id: str
    plugin_version: str
    validation_run_id: str
    total_corpus_cases: int = 0
    cases_ran: int = 0
    cases_skipped: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    avg_confidence: float | None = None
    confidence_range: tuple[float, float] | None = None

    @property
    def precision(self) -> float | None:
        denom = self.true_positives + self.false_positives
        if denom == 0:
            return None
        return self.true_positives / denom

    @property
    def recall(self) -> float | None:
        denom = self.true_positives + self.false_negatives
        if denom == 0:
            return None
        return self.true_positives / denom

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "validation_run_id": self.validation_run_id,
            "total_corpus_cases": self.total_corpus_cases,
            "cases_ran": self.cases_ran,
            "cases_skipped": self.cases_skipped,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "avg_confidence": self.avg_confidence,
            "confidence_range": list(self.confidence_range) if self.confidence_range else None,
            "precision": self.precision,
            "recall": self.recall,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnalyzerQualitySnapshot:
        d = dict(d)
        cr = d.pop("confidence_range", None)
        d.pop("precision", None)
        d.pop("recall", None)
        known = {
            "plugin_id", "plugin_version", "validation_run_id",
            "total_corpus_cases", "cases_ran", "cases_skipped",
            "true_positives", "false_positives", "false_negatives",
            "avg_confidence",
        }
        inst = cls(**{k: v for k, v in d.items() if k in known})
        if cr and isinstance(cr, (list, tuple)) and len(cr) == 2:
            inst.confidence_range = (cr[0], cr[1])
        return inst


@dataclass
class AnalyzerQualityReport:
    validation_run_id: str
    generated_at: str
    engine_version: str
    analyzers: list[AnalyzerQualitySnapshot] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_run_id": self.validation_run_id,
            "generated_at": self.generated_at,
            "engine_version": self.engine_version,
            "analyzers": [a.to_dict() for a in self.analyzers],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnalyzerQualityReport:
        d = dict(d)
        d["analyzers"] = [
            AnalyzerQualitySnapshot.from_dict(a) for a in d.get("analyzers", [])
        ]
        known = {"validation_run_id", "generated_at", "engine_version", "analyzers", "summary"}
        return cls(**{k: v for k, v in d.items() if k in known})


def compute_quality_report(validation_summary: ValidationSummary) -> AnalyzerQualityReport:
    """Compute per-analyzer quality metrics from a validation summary."""
    from goose import __version__
    from goose.plugins import PLUGIN_REGISTRY

    plugin_stats: dict[str, dict[str, Any]] = {}

    # Initialize stats for all known plugins
    for pid, plugin in PLUGIN_REGISTRY.items():
        plugin_stats[pid] = {
            "version": getattr(plugin, "version", "unknown"),
            "cases_ran": 0,
            "cases_skipped": 0,
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
        }

    # Walk each corpus case result
    for result in validation_summary.corpus_case_results:
        observed = result.observed
        expected = result.expected

        for pid in plugin_stats:
            if pid in observed.plugins_ran:
                plugin_stats[pid]["cases_ran"] += 1
            elif pid in observed.plugins_skipped:
                plugin_stats[pid]["cases_skipped"] += 1

        # For each expected finding, check if it was found (TP) or not (FN)
        for exp_finding in expected.expected_findings:
            found = any(
                exp_finding.lower() in t.lower() for t in observed.findings_found
            )
            # Attribute to the most likely plugin based on finding text
            # (simplified: attribute to first plugin that matches)
            attributed_pid = _attribute_finding_to_plugin(exp_finding)
            if attributed_pid and attributed_pid in plugin_stats:
                if found:
                    plugin_stats[attributed_pid]["true_positives"] += 1
                else:
                    plugin_stats[attributed_pid]["false_negatives"] += 1

        # For each not-expected finding that was found (FP)
        for bad_finding in expected.not_expected_findings:
            found = any(
                bad_finding.lower() in t.lower() for t in observed.findings_found
            )
            if found:
                attributed_pid = _attribute_finding_to_plugin(bad_finding)
                if attributed_pid and attributed_pid in plugin_stats:
                    plugin_stats[attributed_pid]["false_positives"] += 1

    # Build snapshots
    snapshots: list[AnalyzerQualitySnapshot] = []
    total_cases = validation_summary.total_cases

    for pid, stats in sorted(plugin_stats.items()):
        snapshots.append(AnalyzerQualitySnapshot(
            plugin_id=pid,
            plugin_version=stats["version"],
            validation_run_id=validation_summary.validation_id,
            total_corpus_cases=total_cases,
            cases_ran=stats["cases_ran"],
            cases_skipped=stats["cases_skipped"],
            true_positives=stats["true_positives"],
            false_positives=stats["false_positives"],
            false_negatives=stats["false_negatives"],
        ))

    # Summary
    total_tp = sum(s.true_positives for s in snapshots)
    total_fp = sum(s.false_positives for s in snapshots)
    total_fn = sum(s.false_negatives for s in snapshots)
    summary = (
        f"{len(snapshots)} analyzers evaluated across {total_cases} corpus cases. "
        f"Aggregate: {total_tp} TP, {total_fp} FP, {total_fn} FN."
    )

    return AnalyzerQualityReport(
        validation_run_id=validation_summary.validation_id,
        generated_at=datetime.now().isoformat(),
        engine_version=__version__,
        analyzers=snapshots,
        summary=summary,
    )


def _attribute_finding_to_plugin(finding_text: str) -> str | None:
    """Best-effort attribution of a finding description to a plugin_id."""
    text = finding_text.lower()
    mapping = {
        "crash": "crash_detection",
        "impact": "crash_detection",
        "altitude loss": "crash_detection",
        "vibration": "vibration",
        "clipping": "vibration",
        "battery": "battery_sag",
        "voltage": "battery_sag",
        "sag": "battery_sag",
        "gps": "gps_health",
        "satellite": "gps_health",
        "hdop": "gps_health",
        "motor": "motor_saturation",
        "saturation": "motor_saturation",
        "imbalance": "motor_saturation",
        "ekf": "ekf_consistency",
        "innovation": "ekf_consistency",
        "rc": "rc_signal",
        "rssi": "rc_signal",
        "attitude": "attitude_tracking",
        "tracking": "attitude_tracking",
        "position": "position_tracking",
        "hover": "position_tracking",
        "drift": "position_tracking",
        "failsafe": "failsafe_events",
        "rtl": "failsafe_events",
        "log": "log_health",
        "dropout": "log_health",
    }
    for keyword, pid in mapping.items():
        if keyword in text:
            return pid
    return None
