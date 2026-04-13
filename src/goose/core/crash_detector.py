"""Crash root cause engine — synthesizes plugin findings into a single diagnosis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from goose.core.finding import Finding
from goose.core.flight import Flight

# Classification constants
MOTOR_FAILURE = "motor_failure"
POWER_LOSS = "power_loss"
GPS_LOSS = "gps_loss"
PILOT_ERROR = "pilot_error"
MECHANICAL = "mechanical"
UNKNOWN = "unknown"

# Plugin name → classification mapping for correlation
_PLUGIN_CLASSIFICATION: dict[str, str] = {
    "motor_saturation": MOTOR_FAILURE,
    "battery_sag": POWER_LOSS,
    "gps_health": GPS_LOSS,
    "vibration": MECHANICAL,
}

# Classification → physical inspect checklist
_INSPECT_CHECKLISTS: dict[str, list[str]] = {
    MOTOR_FAILURE: [
        "Motor bearings",
        "ESC solder joints and connections",
        "Motor wiring harness",
        "Propeller for damage or imbalance",
    ],
    POWER_LOSS: [
        "Battery cell voltages individually",
        "Battery connector and leads",
        "Power distribution board",
        "ESC power connections",
    ],
    GPS_LOSS: [
        "GPS antenna placement and cable",
        "GPS module mounting and shielding",
        "Nearby RF interference sources",
        "Compass calibration",
    ],
    MECHANICAL: [
        "Frame integrity and arm tightness",
        "Motor mounts and vibration dampeners",
        "Propeller balance and condition",
        "Flight controller mounting and dampening",
    ],
    PILOT_ERROR: [
        "RC transmitter range and antenna",
        "Flight mode configuration",
        "Failsafe settings",
        "Control surface linkages (if applicable)",
    ],
    UNKNOWN: [
        "All motor and ESC connections",
        "Battery and power system",
        "Flight controller and sensor connections",
        "Frame and propellers",
    ],
}


@dataclass
class CrashAnalysis:
    """Result of crash root cause analysis."""

    crashed: bool
    confidence: float  # 0.0-1.0
    classification: str  # motor_failure | power_loss | gps_loss | pilot_error | mechanical | unknown
    root_cause: str  # Human-readable description
    evidence_chain: list[str] = field(default_factory=list)
    contributing_factors: list[str] = field(default_factory=list)
    inspect_checklist: list[str] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)


def _build_timeline(findings: list[Finding]) -> list[dict[str, Any]]:
    """Build a sorted timeline from all findings that have timestamps."""
    events: list[dict[str, Any]] = []
    for f in findings:
        if f.timestamp_start is not None:
            events.append(
                {
                    "timestamp": f.timestamp_start,
                    "event": f.title,
                    "severity": f.severity,
                }
            )
        if f.timestamp_end is not None and f.timestamp_end != f.timestamp_start:
            events.append(
                {
                    "timestamp": f.timestamp_end,
                    "event": f"{f.title} (end)",
                    "severity": f.severity,
                }
            )
    events.sort(key=lambda e: e["timestamp"])
    return events


def _find_crash_findings(findings: list[Finding]) -> list[Finding]:
    """Find findings from the crash_detection plugin."""
    return [f for f in findings if f.plugin_name == "crash_detection"]


def _find_critical_findings(findings: list[Finding]) -> list[Finding]:
    """Find all critical-severity findings (excluding crash_detection itself)."""
    return [f for f in findings if f.severity == "critical" and f.plugin_name != "crash_detection"]


def _classify_from_findings(findings: list[Finding]) -> tuple[str, str, float]:
    """Determine classification, root cause, and confidence from correlated findings.

    Returns (classification, root_cause, confidence_boost).
    """
    # Score each classification by matching plugin findings
    classification_scores: dict[str, float] = {}
    classification_evidence: dict[str, list[str]] = {}

    for f in findings:
        if f.plugin_name == "crash_detection":
            continue
        cls = _PLUGIN_CLASSIFICATION.get(f.plugin_name)
        if cls is None:
            continue

        # Weight by severity
        weight = {"critical": 3.0, "warning": 1.5, "info": 0.5, "pass": 0.0}.get(f.severity, 0.0)
        # Also factor in low score (lower score = more evidence of failure)
        score_weight = max(0.0, (100 - f.score) / 100.0)
        combined = weight * (1.0 + score_weight)

        classification_scores[cls] = classification_scores.get(cls, 0.0) + combined
        classification_evidence.setdefault(cls, []).append(f.title)

    if not classification_scores:
        return UNKNOWN, "Crash detected but root cause could not be determined from available data", 0.0

    best_cls = max(classification_scores, key=classification_scores.get)  # type: ignore[arg-type]
    evidence_titles = classification_evidence.get(best_cls, [])
    root_cause = "; ".join(evidence_titles) if evidence_titles else "Unknown"

    # Confidence boost based on strength of evidence
    best_score = classification_scores[best_cls]
    confidence_boost = min(0.3, best_score / 20.0)

    return best_cls, root_cause, confidence_boost


def _check_flight_impact(flight: Flight) -> tuple[bool, float, str]:
    """Check if the flight data itself shows crash signatures.

    Returns (crashed, base_confidence, impact_description).
    """
    if flight.crashed:
        # Compute a basic confidence from the altitude data
        base_confidence = 0.6
        impact_desc = "Rapid altitude loss detected near end of flight"

        # Boost confidence if we see motor output drop
        if not flight.motors.empty:
            motor_cols = [c for c in flight.motors.columns if c.startswith("output_")]
            if motor_cols:
                tail_start = int(len(flight.motors) * 0.9)
                tail = flight.motors.iloc[tail_start:]
                for col in motor_cols:
                    if tail[col].min() < 0.05:
                        base_confidence = min(1.0, base_confidence + 0.1)
                        impact_desc = f"{col} dropped to 0% near end of flight"
                        break

        return True, base_confidence, impact_desc

    return False, 0.0, ""


def analyze_crash(flight: Flight, findings: list[Finding]) -> CrashAnalysis:
    """Synthesize all plugin findings into a crash root cause analysis.

    Logic:
    1. Check crash_detection findings for impact signature
    2. If crash detected, correlate with other plugin findings
    3. Build timeline from all findings
    4. Compute confidence based on evidence strength
    5. Generate inspect checklist based on classification
    """
    # Step 1: Check for crash indicators
    crash_findings = _find_crash_findings(findings)
    has_crash_finding = any(f.severity == "critical" for f in crash_findings)

    flight_crashed, flight_confidence, flight_impact = _check_flight_impact(flight)

    crashed = has_crash_finding or flight_crashed

    if not crashed:
        return CrashAnalysis(
            crashed=False,
            confidence=0.0,
            classification="none",
            root_cause="No crash detected",
        )

    # Step 2: Determine base confidence
    if has_crash_finding:
        # Use the crash_detection plugin's score as inverse confidence
        crash_score = min(f.score for f in crash_findings if f.severity == "critical")
        base_confidence = max(0.5, 1.0 - crash_score / 100.0)
    else:
        base_confidence = flight_confidence

    # Step 3: Classify from correlated findings
    classification, root_cause, confidence_boost = _classify_from_findings(findings)
    confidence = min(1.0, base_confidence + confidence_boost)

    # If crash_detection gave us a more specific root cause, use it
    if crash_findings:
        best_crash_finding = min(crash_findings, key=lambda f: f.score)
        if best_crash_finding.description:
            root_cause = best_crash_finding.description
        # Check evidence for classification hint
        evidence = best_crash_finding.evidence
        if "classification" in evidence:
            classification = str(evidence["classification"])

    # Step 4: Build evidence chain
    evidence_chain: list[str] = []
    critical = _find_critical_findings(findings)
    for f in sorted(critical, key=lambda x: x.timestamp_start or 0.0):
        evidence_chain.append(f"{f.plugin_name}: {f.title} (score: {f.score})")
    if crash_findings:
        for f in crash_findings:
            evidence_chain.append(f"crash_detection: {f.title} (score: {f.score})")
    if flight_impact:
        evidence_chain.append(f"flight_data: {flight_impact}")

    # Step 5: Contributing factors (warning-level findings)
    contributing: list[str] = []
    for f in findings:
        if f.severity == "warning" and f.plugin_name != "crash_detection":
            contributing.append(f"{f.plugin_name}: {f.title}")

    # Step 6: Build timeline
    timeline = _build_timeline(findings)

    # Step 7: Inspect checklist
    checklist_items = _INSPECT_CHECKLISTS.get(classification, _INSPECT_CHECKLISTS[UNKNOWN])
    # Personalize checklist based on evidence
    inspect_checklist: list[str] = []
    for f in findings:
        if f.severity == "critical" and f.plugin_name == "motor_saturation":
            # Add specific motor references from evidence
            motor_id = f.evidence.get("motor_id")
            if motor_id is not None:
                inspect_checklist.append(f"Motor {motor_id} bearings")
                inspect_checklist.append(f"ESC {motor_id} solder joints and connections")
                inspect_checklist.append(f"Motor {motor_id} wiring harness")
                inspect_checklist.append(f"Propeller {motor_id} for damage or imbalance")

    if not inspect_checklist:
        inspect_checklist = list(checklist_items)

    return CrashAnalysis(
        crashed=True,
        confidence=round(confidence, 2),
        classification=classification,
        root_cause=root_cause,
        evidence_chain=evidence_chain,
        contributing_factors=contributing,
        inspect_checklist=inspect_checklist,
        timeline=timeline,
    )
