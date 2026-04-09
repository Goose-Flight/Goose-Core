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
    - Resolves stream_name from the plugin's manifest.primary_stream via
      PLUGIN_REGISTRY lookup.  Falls back to "" if the plugin is not registered.
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
    from goose.plugins import PLUGIN_REGISTRY
    _plugin = PLUGIN_REGISTRY.get(thin.plugin_name)
    stream = _plugin.manifest.primary_stream if _plugin is not None else ""

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

# Theme definitions.
#
# Fields (per entry):
#   theme              — short theme key used internally and for sorting
#   category           — human-readable category label (v11 spec)
#   statement_template — plain-language root-cause statement
#   plugin_ids         — plugin.name set that can support this hypothesis
#   severity_filter    — severities counted as supporting evidence
#   required_streams   — telemetry streams relied on (for missing-data penalty)
#   recommendations    — default analyst recommendations for this theme
def _build_impact_damage_plugin_ids() -> set[str]:
    """Build impact_damage plugin_ids, including payload_change_detection if registered."""
    from goose.plugins import PLUGIN_REGISTRY
    ids: set[str] = {"crash_detection", "vibration", "motor_saturation"}
    if "payload_change_detection" in PLUGIN_REGISTRY:
        ids.add("payload_change_detection")
    return ids


_HYPOTHESIS_THEMES: list[dict[str, Any]] = [
    {
        "theme": "crash",
        "category": "impact / damage class",
        "statement": "The vehicle experienced a crash or uncontrolled impact.",
        "plugin_ids": {"crash_detection"},
        "severity_filter": {"critical", "warning"},
        "required_streams": {"position", "attitude"},
        "recommendations": [
            "Inspect frame for structural damage",
            "Review motor telemetry for pre-impact anomalies",
            "Correlate impact time with pilot input and failsafe events",
        ],
    },
    {
        "theme": "power",
        "category": "battery / power issue",
        "statement": "Power system degradation contributed to the flight anomaly.",
        "plugin_ids": {"battery_sag"},
        "severity_filter": {"critical", "warning"},
        "required_streams": {"battery"},
        "recommendations": [
            "Inspect battery pack for cell imbalance, puffing, or damage",
            "Verify charger health and charge cycles on the pack",
            "Cross-check voltage telemetry against motor load",
        ],
    },
    {
        "theme": "navigation",
        "category": "navigation / GPS issue",
        "statement": "Navigation or position estimation failure affected the flight.",
        "plugin_ids": {"gps_health", "ekf_health", "ekf_status", "ekf_consistency"},
        "severity_filter": {"critical", "warning"},
        "required_streams": {"gps", "ekf"},
        "recommendations": [
            "Review GPS fix quality and sky visibility at the operating area",
            "Check EKF innovations and reset events",
            "Audit recent firmware or parameter changes affecting the estimator",
        ],
    },
    {
        "theme": "vibration",
        "category": "vibration-induced instability",
        "statement": "Excessive vibration degraded vehicle control or sensor quality.",
        "plugin_ids": {"vibration"},
        "severity_filter": {"critical", "warning"},
        "required_streams": {"vibration"},
        "recommendations": [
            "Balance propellers and inspect motor bearings",
            "Verify flight controller soft-mount integrity",
            "Check for loose frame hardware or damaged props",
        ],
    },
    {
        "theme": "propulsion",
        "category": "propulsion / motor issue",
        "statement": "Motor or propulsion system anomaly occurred during flight.",
        "plugin_ids": {"motor_saturation"},
        "severity_filter": {"critical", "warning"},
        "required_streams": {"motors"},
        "recommendations": [
            "Inspect each motor for bearing drag, heat damage, or winding issues",
            "Verify ESC calibration and firmware consistency across channels",
            "Check for mass imbalance or asymmetric thrust authority",
        ],
    },
    {
        "theme": "control",
        "category": "control / attitude tracking issue",
        "statement": "Attitude or flight control degradation was detected.",
        "plugin_ids": {"attitude_tracking"},
        "severity_filter": {"critical", "warning"},
        "required_streams": {"attitude"},
        "recommendations": [
            "Review rate controller tuning and PID gains",
            "Verify IMU orientation and calibration",
            "Correlate tracking errors with RC input and mode changes",
        ],
    },
    {
        "theme": "communications_link",
        "category": "communications / link issue",
        "statement": "Communications or link degradation contributed to the event.",
        "plugin_ids": {"rc_signal", "failsafe_events"},
        "severity_filter": {"critical", "warning"},
        "required_streams": set(),
        "recommendations": [
            "Review RC RSSI and dropout events in the telemetry log",
            "Check antenna placement and radio frequency interference sources",
            "Verify failsafe configuration and RTL trigger thresholds",
        ],
    },
    {
        "theme": "operator_action",
        "category": "operator-action contribution",
        "statement": "Operator action or control input sequence contributed to the event.",
        "plugin_ids": {"failsafe_events", "rc_signal"},
        "severity_filter": {"critical", "warning"},
        "required_streams": set(),
        "recommendations": [
            "Review RC input trace around the event window",
            "Interview the pilot about intended actions at the time of the anomaly",
            "Check for mode switch commands or arming/disarming sequences",
        ],
    },
    {
        "theme": "environmental",
        "category": "environmental contribution",
        "statement": "Environmental conditions (wind, GPS multipath, interference) contributed to degraded performance.",
        "plugin_ids": {"gps_health", "ekf_consistency"},
        "severity_filter": {"critical", "warning"},
        "required_streams": set(),
        "recommendations": [
            "Review wind speed and direction records for the flight location and time",
            "Inspect GPS satellite geometry and signal quality metrics",
            "Check for nearby RF interference sources (cellular, Wi-Fi, radar)",
        ],
    },
    {
        "theme": "impact_damage",
        "category": "impact / damage class",
        "statement": "Physical impact or damage occurred and may have caused or resulted from the event.",
        "plugin_ids": _build_impact_damage_plugin_ids,  # callable — evaluated lazily at runtime
        "severity_filter": {"critical", "warning"},
        "required_streams": set(),
        "recommendations": [
            "Inspect airframe and components for mechanical damage",
            "Check motor outputs for asymmetric failure signatures",
            "Correlate vibration spikes with crash detection timestamps",
        ],
    },
]


def _diag_missing_streams(diag: ParseDiagnostics | None) -> set[str]:
    """Return the set of required streams that were reported missing by the parser."""
    if diag is None:
        return set()
    missing: set[str] = set()
    for sc in getattr(diag, "stream_coverage", []) or []:
        if not getattr(sc, "present", True):
            missing.add(getattr(sc, "stream_name", ""))
    return missing


def generate_hypotheses(
    forensic_findings: list[ForensicFinding],
    run_id: str,
    parse_diag: ParseDiagnostics | None = None,
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
    from goose.plugins import PLUGIN_REGISTRY

    hypotheses: list[Hypothesis] = []
    missing_streams = _diag_missing_streams(parse_diag)
    max_confidence_seen: float = 0.0

    for theme_entry in _HYPOTHESIS_THEMES:
        theme = theme_entry["theme"]
        category = theme_entry["category"]
        statement = theme_entry["statement"]
        # plugin_ids may be a callable (for dynamic sets) or a plain set
        plugin_ids = (
            theme_entry["plugin_ids"]() if callable(theme_entry["plugin_ids"])
            else theme_entry["plugin_ids"]
        )
        sev_filter = theme_entry["severity_filter"]
        required_streams = theme_entry.get("required_streams", set())
        recommendations = list(theme_entry.get("recommendations", []))

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
        contradicting_findings_raw = [
            f for f in theme_findings
            if f.severity == FindingSeverity.PASS
        ]
        contradicting_ids = [f.finding_id for f in contradicting_findings_raw]
        # E1: structured contradicting_findings list
        contradicting_findings_structured = [
            {
                "finding_id": f.finding_id,
                "title": f.title,
                "severity": f.severity.value,
            }
            for f in contradicting_findings_raw
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

        # --- v11 missing-data penalty --------------------------------------
        # If any required stream is absent from the parse, the analytical
        # basis for this hypothesis is weaker. Reduce confidence by 0.1 per
        # required stream absence (floored at 0.0), and record an unresolved
        # question noting what is missing.
        theme_missing = required_streams & missing_streams
        if theme_missing:
            penalty = round(0.1 * len(theme_missing), 2)
            confidence = round(max(0.0, confidence - penalty), 2)
            unresolved.append(
                "Required telemetry streams missing for this hypothesis: "
                + ", ".join(sorted(theme_missing))
            )

        if confidence > max_confidence_seen:
            max_confidence_seen = confidence

        hypotheses.append(Hypothesis(
            hypothesis_id=f"HYP-{uuid.uuid4().hex[:8].upper()}",
            statement=statement,
            supporting_finding_ids=supporting_ids,
            contradicting_finding_ids=contradicting_ids,
            contradicting_findings=contradicting_findings_structured,
            confidence=confidence,
            # confidence_scope defaults to "hypothesis_root_cause" — not parser or finding confidence
            status=HypothesisStatus.CANDIDATE,
            unresolved_questions=unresolved,
            run_id=run_id,
            theme=theme,
            category=category,
            recommendations=recommendations,
            generated_by="system",
        ))

    # E3: Payload mass change — emit standalone hypothesis when payload findings
    # exist but no crash/impact findings are present.
    if "payload_change_detection" in PLUGIN_REGISTRY:
        payload_findings = [
            f for f in forensic_findings
            if f.plugin_id == "payload_change_detection"
            and f.severity.value in {"critical", "warning"}
        ]
        crash_findings = [
            f for f in forensic_findings
            if f.plugin_id in {"crash_detection"}
            and f.severity.value in {"critical", "warning"}
        ]
        if payload_findings and not crash_findings:
            payload_contradicting_raw = [
                f for f in forensic_findings
                if f.plugin_id == "payload_change_detection"
                and f.severity == FindingSeverity.PASS
            ]
            p_supporting_ids = [f.finding_id for f in payload_findings]
            p_contradicting_ids = [f.finding_id for f in payload_contradicting_raw]
            p_contradicting_structured = [
                {"finding_id": f.finding_id, "title": f.title, "severity": f.severity.value}
                for f in payload_contradicting_raw
            ]
            p_total = len(p_supporting_ids) + len(p_contradicting_ids)
            p_confidence = round(len(p_supporting_ids) / p_total, 2) if p_total > 0 else 0.0
            if p_confidence > max_confidence_seen:
                max_confidence_seen = p_confidence
            hypotheses.append(Hypothesis(
                hypothesis_id=f"HYP-{uuid.uuid4().hex[:8].upper()}",
                statement="A payload mass change event (drop, release, or addition) occurred during flight.",
                supporting_finding_ids=p_supporting_ids,
                contradicting_finding_ids=p_contradicting_ids,
                contradicting_findings=p_contradicting_structured,
                confidence=p_confidence,
                status=HypothesisStatus.CANDIDATE,
                unresolved_questions=[
                    "Payload change detection is a low-confidence Phase 1 signal — "
                    "corroborate with video evidence or operator testimony.",
                ],
                run_id=run_id,
                theme="payload_mass_change",
                category="propulsion / motor issue",
                recommendations=[
                    "Review current draw trace and motor output around the candidate event timestamp",
                    "Correlate with video or operator records of any payload release/attachment",
                ],
                generated_by="system",
            ))

    # E2 unknown_mixed: emit when no other hypothesis has confidence >= 0.3
    if max_confidence_seen < 0.3:
        unknown_confidence = max(0.1, round(0.3 - max_confidence_seen, 2)) if max_confidence_seen > 0 else 0.2
        hypotheses.append(Hypothesis(
            hypothesis_id=f"HYP-{uuid.uuid4().hex[:8].upper()}",
            statement="Root cause is unclear or involves multiple interacting factors.",
            supporting_finding_ids=[f.finding_id for f in forensic_findings],
            contradicting_finding_ids=[],
            contradicting_findings=[],
            confidence=unknown_confidence,
            status=HypothesisStatus.CANDIDATE,
            unresolved_questions=[
                "No single theme reached sufficient confidence — a multi-factor or "
                "undetermined root cause should be considered.",
                "Additional manual investigation or data collection is recommended.",
            ],
            run_id=run_id,
            theme="unknown_mixed",
            category="unknown / mixed-factor event",
            recommendations=[
                "Perform a detailed manual walkthrough of the full flight log",
                "Request additional sensor data or pilot account of events",
                "Consider whether multiple simultaneous failure modes may have interacted",
            ],
            generated_by="system",
        ))

    # Sort: highest confidence first
    hypotheses.sort(key=lambda h: h.confidence, reverse=True)
    return hypotheses
