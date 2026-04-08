"""Lifting layer — promotes thin plugin findings to forensic-grade artifacts.

Plugins currently emit goose.core.finding.Finding (thin).  This module
converts them to ForensicFinding and auto-generates Hypothesis candidates
from correlated findings.

Sprint 5 will let plugins emit ForensicFinding directly.  Until then this
layer bridges the gap without breaking the existing plugin contract.

Design rules:
- Every ForensicFinding must have at least one EvidenceReference.
- Confidence is derived from the finding score (score / 100) — a reasonable
  proxy until Sprint 5 plugins declare their own confidence.
- Hypothesis generation is rule-based and conservative; it flags correlations
  but does not invent claims the findings don't support.
- Parser confidence, finding confidence, and hypothesis confidence remain
  explicitly distinct throughout.

Sprint 4 — Canonical Model Completion
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from goose.core.finding import Finding
    from goose.forensics.models import EvidenceItem
    from goose.parsers.diagnostics import ParseDiagnostics

from goose.forensics.canonical import (
    ConfidenceBand,
    EvidenceReference,
    FindingSeverity,
    ForensicFinding,
    Hypothesis,
    HypothesisStatus,
    SignalQuality,
    _PLUGIN_STREAM_MAP,
)


# ---------------------------------------------------------------------------
# SignalQuality building
# ---------------------------------------------------------------------------

def build_signal_quality(diag: ParseDiagnostics) -> list[SignalQuality]:
    """Build SignalQuality list from ParseDiagnostics stream coverage."""
    return [SignalQuality.from_stream_coverage(sc) for sc in diag.stream_coverage]


# ---------------------------------------------------------------------------
# Finding lifting
# ---------------------------------------------------------------------------

def lift_finding(
    thin: Finding,
    run_id: str,
    evidence_item: EvidenceItem,
    plugin_version: str,
    parse_diag: ParseDiagnostics | None = None,
) -> ForensicFinding:
    """Promote a thin plugin Finding to a ForensicFinding.

    Evidence reference construction:
    - Always attaches evidence_id from the case evidence item.
    - Maps plugin_id → stream_name via _PLUGIN_STREAM_MAP.
    - Copies timestamp_start/timestamp_end as time_range when present.
    - Uses the finding description as support_summary.

    Confidence derivation:
    - confidence = score / 100.0 (proxy until Sprint 5 plugins declare own confidence)
    - For PASS findings, confidence is high; for CRITICAL, it reflects the
      score the plugin assigned.
    - confidence_scope is always "finding_analysis" — never parser confidence.

    Supporting/contradicting metrics:
    - Copies thin finding's evidence dict as supporting_metrics.
    - contradicting_metrics is empty — Sprint 5 plugins will declare their own.
    """
    stream = _PLUGIN_STREAM_MAP.get(thin.plugin_name)

    ev_ref = EvidenceReference(
        evidence_id=evidence_item.evidence_id,
        stream_name=stream,
        time_range_start=thin.timestamp_start,
        time_range_end=thin.timestamp_end,
        support_summary=thin.description[:200] if thin.description else "",
    )

    # Sanitize supporting metrics (thin finding's evidence dict may contain
    # numpy scalars or other non-serializable types)
    supporting: dict[str, Any] = {}
    for k, v in (thin.evidence or {}).items():
        try:
            import json as _json
            _json.dumps(v)
            supporting[k] = v
        except (TypeError, ValueError):
            supporting[k] = str(v)

    severity = FindingSeverity(thin.severity) if thin.severity in FindingSeverity._value2member_map_ else FindingSeverity.INFO

    return ForensicFinding(
        finding_id=f"FND-{uuid.uuid4().hex[:8].upper()}",
        plugin_id=thin.plugin_name,
        plugin_version=plugin_version,
        title=thin.title,
        description=thin.description,
        severity=severity,
        score=int(thin.score),
        confidence=round(int(thin.score) / 100.0, 2),
        # confidence_scope defaults to "finding_analysis" — intentionally distinct
        # from ParseDiagnostics.confidence_scope ("parser_parse_quality")
        phase=thin.phase,
        start_time=thin.timestamp_start,
        end_time=thin.timestamp_end,
        evidence_references=[ev_ref],
        supporting_metrics=supporting,
        contradicting_metrics={},
        assumptions=[],
        run_id=run_id,
    )


def lift_findings(
    thin_findings: list[Finding],
    run_id: str,
    evidence_item: EvidenceItem,
    plugin_versions: dict[str, str],
    parse_diag: ParseDiagnostics | None = None,
) -> list[ForensicFinding]:
    """Lift all thin findings from an analysis run."""
    result: list[ForensicFinding] = []
    for f in thin_findings:
        version = plugin_versions.get(f.plugin_name, "unknown")
        result.append(lift_finding(f, run_id, evidence_item, version, parse_diag))
    return result


# ---------------------------------------------------------------------------
# Hypothesis generation
# ---------------------------------------------------------------------------

# Theme definitions: (theme_name, statement_template, matching_plugin_ids, severity_filter)
_HYPOTHESIS_THEMES: list[tuple[str, str, set[str], set[str]]] = [
    (
        "crash",
        "The vehicle experienced a crash or uncontrolled impact.",
        {"crash_detection"},
        {"critical", "warning"},
    ),
    (
        "power",
        "Power system degradation contributed to the flight anomaly.",
        {"battery_sag"},
        {"critical", "warning"},
    ),
    (
        "navigation",
        "Navigation or position estimation failure affected the flight.",
        {"gps_health", "ekf_health", "ekf_status"},
        {"critical", "warning"},
    ),
    (
        "vibration",
        "Excessive vibration degraded vehicle control or sensor quality.",
        {"vibration"},
        {"critical", "warning"},
    ),
    (
        "propulsion",
        "Motor or propulsion system anomaly occurred during flight.",
        {"motor_saturation"},
        {"critical", "warning"},
    ),
    (
        "control",
        "Attitude or flight control degradation was detected.",
        {"attitude_tracking"},
        {"critical", "warning"},
    ),
]


def generate_hypotheses(
    forensic_findings: list[ForensicFinding],
    run_id: str,
) -> list[Hypothesis]:
    """Auto-generate hypothesis candidates from correlated findings.

    Rules:
    - A hypothesis is created for each theme that has at least one supporting
      finding (severity: critical or warning) from a matching plugin.
    - Pass findings for a theme's plugins are counted as contradicting evidence
      for that theme's hypothesis.
    - Confidence = (supporting_count) / (supporting_count + contradicting_count)
      where both counts use findings from the theme's plugin set only.
    - Hypotheses are CANDIDATE by default; analysis does not auto-promote them
      to SUPPORTED/REFUTED — that requires human review or Sprint 7 correlation.
    - Unresolved questions are generated for findings without contradicting evidence.

    Facts, findings, and hypotheses remain distinct:
    - The hypothesis references finding_ids — it does not embed findings.
    - Parser confidence is not used here.
    """
    hypotheses: list[Hypothesis] = []

    for theme, statement, plugin_ids, sev_filter in _HYPOTHESIS_THEMES:
        theme_findings = [
            f for f in forensic_findings
            if f.plugin_id in plugin_ids
        ]
        if not theme_findings:
            continue

        supporting_ids = [
            f.finding_id for f in theme_findings
            if f.severity.value in sev_filter
        ]
        contradicting_ids = [
            f.finding_id for f in theme_findings
            if f.severity == FindingSeverity.PASS
        ]

        if not supporting_ids:
            continue  # No meaningful evidence for this theme

        total = len(supporting_ids) + len(contradicting_ids)
        confidence = round(len(supporting_ids) / total, 2) if total > 0 else 0.0

        unresolved: list[str] = []
        if not contradicting_ids:
            unresolved.append(
                f"No contradicting findings for '{theme}' theme — additional checks may be needed."
            )
        if confidence < 0.6:
            unresolved.append(
                "Confidence is moderate; corroboration from additional plugin analysis recommended."
            )

        hypotheses.append(Hypothesis(
            hypothesis_id=f"HYP-{uuid.uuid4().hex[:8].upper()}",
            statement=statement,
            supporting_finding_ids=supporting_ids,
            contradicting_finding_ids=contradicting_ids,
            confidence=confidence,
            # confidence_scope defaults to "hypothesis_root_cause" — not parser or finding confidence
            status=HypothesisStatus.CANDIDATE,
            unresolved_questions=unresolved,
            run_id=run_id,
            theme=theme,
        ))

    # Sort: highest confidence first
    hypotheses.sort(key=lambda h: h.confidence, reverse=True)
    return hypotheses
