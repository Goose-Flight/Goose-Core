"""Dynamic flight narrative generator — builds a human-readable summary from findings.

No AI calls. Pure template logic. Adapts to whatever plugins ran and whatever
data was available. If a plugin didn't run or data was missing, it's simply
not mentioned.
"""

from __future__ import annotations

from typing import Any


_SKIP_KEYWORDS = frozenset([
    "skipped", "not available", "not found", "no data", "no battery",
    "no attitude", "no gps", "no motor", "no rc", "no ekf", "no position",
])


def _is_data_missing(finding: Any) -> bool:
    """True if this finding just reports missing data."""
    if finding.severity != "info":
        return False
    desc = (finding.description or "").lower()
    return any(kw in desc for kw in _SKIP_KEYWORDS)


def generate_narrative(
    findings: list[Any],
    metadata: dict[str, Any] | None = None,
    overall_score: int | None = None,
) -> str:
    """Generate a dynamic flight analysis narrative from findings.

    Args:
        findings: List of Finding objects from plugin analysis.
        metadata: Flight metadata dict (duration_str, vehicle_type, etc.).
        overall_score: The computed overall score (0-100).

    Returns:
        A multi-sentence human-readable flight summary.
    """
    meta = metadata or {}
    parts: list[str] = []

    # ── Flight overview ──────────────────────────────────
    overview_bits: list[str] = []
    if meta.get("duration_str"):
        overview_bits.append(f"{meta['duration_str']} flight")
    if meta.get("vehicle_type"):
        vt = meta["vehicle_type"].replace("_", " ").title()
        overview_bits.append(vt)
    if meta.get("primary_mode"):
        overview_bits.append(f"in {meta['primary_mode'].title()} mode")
    if meta.get("firmware_version") and meta["firmware_version"] != "unknown":
        overview_bits.append(f"(fw {meta['firmware_version']})")

    if overview_bits:
        parts.append(" ".join(overview_bits) + ".")

    # ── Overall score ────────────────────────────────────
    if overall_score is not None:
        if overall_score >= 80:
            grade = "Nominal"
        elif overall_score >= 50:
            grade = "Degraded"
        else:
            grade = "Critical"
        parts.append(f"Overall score: {overall_score}/100 ({grade}).")

    # ── Crash detection ──────────────────────────────────
    if meta.get("crashed"):
        parts.append("CRASH DETECTED during this flight.")

    # ── Separate findings by type ────────────────────────
    real_findings: list[Any] = [f for f in findings if not _is_data_missing(f)]
    criticals = [f for f in real_findings if f.severity == "critical"]
    warnings = [f for f in real_findings if f.severity == "warning"]
    passes = [f for f in real_findings if f.severity == "pass"]

    # ── Critical findings (always mentioned) ─────────────
    for f in criticals:
        evidence_str = _format_key_evidence(f.evidence)
        line = f"CRITICAL — {f.title}."
        if f.description:
            line += f" {_first_sentence(f.description)}"
        if evidence_str:
            line += f" ({evidence_str})"
        parts.append(line)

    # ── Warnings (summarized) ────────────────────────────
    if warnings:
        if len(warnings) <= 3:
            for f in warnings:
                evidence_str = _format_key_evidence(f.evidence)
                line = f"Warning — {f.title}."
                if evidence_str:
                    line += f" ({evidence_str})"
                parts.append(line)
        else:
            warning_names = ", ".join(f.title for f in warnings[:3])
            parts.append(
                f"{len(warnings)} warnings detected: {warning_names}"
                + (f", and {len(warnings) - 3} more." if len(warnings) > 3 else ".")
            )

    # ── Passes (brief summary) ───────────────────────────
    if passes:
        # Group passes by plugin
        pass_plugins = sorted(set(f.plugin_name for f in passes))
        if len(pass_plugins) <= 4:
            parts.append(f"All checks passed: {', '.join(pass_plugins)}.")
        else:
            parts.append(f"{len(pass_plugins)} plugins passed all checks.")

    # ── Missing data note ────────────────────────────────
    missing = [f for f in findings if _is_data_missing(f)]
    if missing:
        missing_plugins = sorted(set(f.plugin_name for f in missing))
        parts.append(
            f"Data not available for: {', '.join(missing_plugins)} "
            f"(excluded from scoring)."
        )

    # ── No findings at all ───────────────────────────────
    if not findings:
        parts.append("No analysis findings. Upload a flight log to run the analysis pipeline.")

    return " ".join(parts)


def _first_sentence(text: str) -> str:
    """Extract the first sentence from a description."""
    for end in (". ", ".\n", ".\t"):
        idx = text.find(end)
        if idx != -1:
            return text[:idx + 1]
    if text.endswith("."):
        return text
    return text.split("\n")[0].rstrip(".") + "."


def _format_key_evidence(evidence: dict[str, Any] | None) -> str:
    """Pick the most useful 1-2 evidence values for inline display."""
    if not evidence:
        return ""
    # Priority keys that are most useful in a summary
    priority = [
        "peak_value", "max_value", "min_value", "mean_value",
        "threshold", "drop_volts", "sag_percent", "rms",
        "duration_sec", "count", "max_error_deg",
    ]
    selected: list[str] = []
    for key in priority:
        if key in evidence:
            val = evidence[key]
            if isinstance(val, float):
                val = round(val, 2)
            selected.append(f"{key}={val}")
            if len(selected) >= 2:
                break

    if not selected:
        # Fall back to first 2 non-string evidence items
        for k, v in list(evidence.items())[:2]:
            if isinstance(v, (int, float)):
                if isinstance(v, float):
                    v = round(v, 2)
                selected.append(f"{k}={v}")

    return ", ".join(selected)
