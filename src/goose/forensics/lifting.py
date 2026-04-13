"""Thin-finding bridge — promotes legacy plugin findings to forensic-grade artifacts.

Role of this module
-------------------
This is a **transitional bridge**.  Plugins in goose-flight currently emit
``goose.core.finding.Finding`` (thin) objects from their ``analyze()`` method.
This module converts them to ``ForensicFinding`` and auto-generates
``Hypothesis`` candidates from correlated findings.

The bridge exists so that all 17 built-in plugins continue to work without
rewriting them.  Plugins that have been ported to native ForensicFinding
emission (via ``Plugin.forensic_analyze_native()``) bypass this module entirely
— the base class dispatches to native emission first.

Planned retirement path
-----------------------
The thin-finding bridge (``lift_finding``, ``lift_findings``) will be retired
progressively as plugins are ported to emit ``ForensicFinding`` directly from
``forensic_analyze_native()``.  When all plugins are ported:

1. ``lift_finding`` and ``lift_findings`` can be removed.
2. ``Plugin.forensic_analyze()`` in ``base.py`` can remove the thin-finding
   fallback path.
3. ``goose.core.finding.Finding`` (the thin type) can be deprecated.

Do not add new callers to ``lift_finding`` / ``lift_findings``.  New plugins
should override ``forensic_analyze_native()`` and return ``ForensicFinding``
directly.

Design rules
------------
- Every ForensicFinding must have at least one EvidenceReference.
- Confidence is derived from the finding score (score / 100) — a proxy until
  plugins declare their own confidence via native emission.
- Hypothesis generation is rule-based and conservative; it flags correlations
  but does not invent claims the findings do not support.
- Parser confidence, finding confidence, and hypothesis confidence remain
  explicitly distinct throughout.

Sprint 4 — Canonical Model Completion
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from goose.core.finding import Finding
    from goose.forensics.models import EvidenceItem
    from goose.parsers.diagnostics import ParseDiagnostics

from goose.forensics.canonical import (
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

    # Resolve the best available time range from the thin finding.
    # Priority: timestamp_start/end (canonical Finding fields) →
    # start_time/end_time (alternate names some plugins may use) → None.
    time_start: float | None = getattr(thin, "timestamp_start", None)
    if time_start is None:
        time_start = getattr(thin, "start_time", None)
    time_end: float | None = getattr(thin, "timestamp_end", None)
    if time_end is None:
        time_end = getattr(thin, "end_time", None)

    ev_ref = EvidenceReference(
        evidence_id=evidence_item.evidence_id,
        stream_name=stream,
        time_range_start=time_start,
        time_range_end=time_end,
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

    # Also extract phase from alternate attribute names for forward-compat
    phase = getattr(thin, "phase", None)

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
        phase=phase,
        start_time=time_start,
        end_time=time_end,
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
        "plugin_ids": {"rc_signal", "failsafe_events", "operator_action_sequence"},
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
        "plugin_ids": {"failsafe_events", "rc_signal", "operator_action_sequence"},
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


# ---------------------------------------------------------------------------
# Design note: generate_hypotheses() is intentionally rule-based and
# conservative. It correlates plugin findings by theme using the static
# _HYPOTHESIS_THEMES registry — no machine learning, no probabilistic
# inference, no LLM calls. This is a deliberate forensic design choice:
#
#   1. Rules are auditable. An investigator can trace exactly which findings
#      triggered a hypothesis and why confidence was computed as it was.
#   2. Rules are deterministic. Replay always produces the same hypothesis set
#      for the same findings (no stochastic or external-API dependencies).
#   3. Hypotheses are CANDIDATE only. Promoting to SUPPORTED or REFUTED
#      requires human analyst judgment or future correlation logic — the
#      system never auto-closes a hypothesis.
#
# LLM-assisted hypothesis enrichment (narrative generation, unresolved question
# phrasing, root-cause explanation) is deferred to a future sprint and will be
# additive — it will not replace this rule-based layer.
# ---------------------------------------------------------------------------

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
        raw_confidence = round(len(supporting_ids) / total, 2) if total > 0 else 0.0
        confidence = raw_confidence

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
        penalty = 0.0
        if theme_missing:
            penalty = round(0.1 * len(theme_missing), 2)
            confidence = round(max(0.0, confidence - penalty), 2)
            unresolved.append(
                "Required telemetry streams missing for this hypothesis: "
                + ", ".join(sorted(theme_missing))
            )

        # --- C2b: stream-specific unresolved questions per plugin ----------
        for pid in plugin_ids:
            plugin_obj = PLUGIN_REGISTRY.get(pid)
            if plugin_obj is None:
                continue
            plugin_required = getattr(
                getattr(plugin_obj, "manifest", None), "required_streams", []
            ) or []
            for stream in plugin_required:
                if stream in missing_streams and stream not in theme_missing:
                    unresolved.append(
                        f"Stream '{stream}' required by plugin '{pid}' is absent — "
                        "findings from this plugin may be incomplete."
                    )

        # --- C2a: score_components transparency ---------------------------
        score_components: dict[str, Any] = {
            "supporting_findings_count": len(supporting_ids),
            "contradicting_findings_count": len(contradicting_ids),
            "missing_stream_penalty": -penalty,
            "raw_confidence": raw_confidence,
            "final_confidence": confidence,
        }

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
            supporting_metrics={"score_components": score_components},
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

        # C2c: populate with available evidence stream names for investigator context
        available_streams = sorted({
            ref.stream_name
            for f in forensic_findings
            for ref in f.evidence_references
            if getattr(ref, "stream_name", None)
        })
        stream_list = ", ".join(available_streams) if available_streams else "none identified"

        # C2c: contradicting_findings = PASS findings from all theme plugins (evidence
        # that each specific cause was NOT found)
        all_pass_findings = [
            f for f in forensic_findings
            if f.severity == FindingSeverity.PASS
        ]
        unknown_contradicting_structured = [
            {"finding_id": f.finding_id, "title": f.title, "severity": f.severity.value}
            for f in all_pass_findings
        ]

        hypotheses.append(Hypothesis(
            hypothesis_id=f"HYP-{uuid.uuid4().hex[:8].upper()}",
            statement="Root cause is unclear or involves multiple interacting factors.",
            supporting_finding_ids=[f.finding_id for f in forensic_findings],
            contradicting_finding_ids=[f.finding_id for f in all_pass_findings],
            contradicting_findings=unknown_contradicting_structured,
            confidence=unknown_confidence,
            status=HypothesisStatus.CANDIDATE,
            unresolved_questions=[
                "No single theme reached sufficient confidence — a multi-factor or "
                "undetermined root cause should be considered.",
                "Additional manual investigation or data collection is recommended.",
                f"No clear dominant cause identified — consider reviewing: {stream_list}",
            ],
            analyst_notes=(
                "This hypothesis fires when no other theme achieves sufficient confidence. "
                "It is not a cause — it is a forensic signal that more data or investigation is needed."
            ),
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
