"""Goose scoring engine — compute overall flight scores from plugin findings."""

from __future__ import annotations

from typing import Any


# Per-plugin importance weights
PLUGIN_WEIGHTS: dict[str, float] = {
    "crash_detection": 3.0,
    "vibration": 1.5,
    "battery_sag": 2.0,
    "gps_health": 1.5,
    "motor_saturation": 2.0,
    "ekf_consistency": 1.5,
    "rc_signal": 1.0,
    "attitude_tracking": 1.0,
    "position_tracking": 1.0,
    "failsafe_events": 1.5,
    "log_health": 0.5,
}


_SKIP_KEYWORDS = frozenset([
    "skipped", "not available", "not found", "no data", "no battery",
    "no attitude", "no gps", "no motor", "no rc", "no ekf", "no position",
])


def _is_data_missing_finding(finding: Any) -> bool:
    """Return True if this finding just reports missing data (not a real issue)."""
    if finding.severity != "info":
        return False
    desc = (finding.description or "").lower()
    return any(kw in desc for kw in _SKIP_KEYWORDS)


def compute_overall_score(findings: list[Any]) -> int:
    """Compute a weighted overall score (0-100) from all findings.

    Groups findings by plugin, takes the worst (minimum) score per plugin,
    then computes a weighted average using PLUGIN_WEIGHTS.

    Plugins that only report missing data (no sensor data available) are
    excluded from the average — missing data should not penalize the score.
    """
    if not findings:
        return 100

    # Worst score per plugin, tracking which plugins only have skip findings
    plugin_scores: dict[str, int] = {}
    plugin_has_real_finding: dict[str, bool] = {}
    for f in findings:
        name = f.plugin_name
        score = int(f.score)
        if name not in plugin_scores:
            plugin_scores[name] = score
            plugin_has_real_finding[name] = not _is_data_missing_finding(f)
        else:
            plugin_scores[name] = min(plugin_scores[name], score)
            if not _is_data_missing_finding(f):
                plugin_has_real_finding[name] = True

    total_weight = 0.0
    weighted_sum = 0.0
    for plugin_name, score in plugin_scores.items():
        # Skip plugins that only reported missing data
        if not plugin_has_real_finding.get(plugin_name, False):
            continue
        w = PLUGIN_WEIGHTS.get(plugin_name, 1.0)
        weighted_sum += score * w
        total_weight += w

    if total_weight == 0:
        return 100

    raw = weighted_sum / total_weight
    return max(0, min(100, round(raw)))
