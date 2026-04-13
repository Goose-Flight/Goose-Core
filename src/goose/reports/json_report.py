"""Goose JSON report generation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import goose
from goose.core.finding import Finding
from goose.core.flight import Flight
from goose.core.scoring import compute_overall_score


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    """Serialize a Finding to a JSON-safe dict."""
    evidence = finding.evidence or {}
    safe_evidence: dict[str, Any] = {}
    for k, v in evidence.items():
        try:
            json.dumps(v)
            safe_evidence[k] = v
        except (TypeError, ValueError):
            safe_evidence[k] = str(v)

    return {
        "plugin_name": finding.plugin_name,
        "title": finding.title,
        "severity": finding.severity,
        "score": int(finding.score),
        "description": finding.description,
        "evidence": safe_evidence,
        "phase": finding.phase,
        "timestamp_start": finding.timestamp_start,
        "timestamp_end": finding.timestamp_end,
    }


def generate(
    flight: Flight,
    findings: list[Finding],
) -> dict[str, Any]:
    """Generate a complete JSON report from flight analysis results."""
    meta = flight.metadata
    overall = compute_overall_score(findings)

    by_severity: dict[str, int] = {"critical": 0, "warning": 0, "info": 0, "pass": 0}
    for f in findings:
        sev = f.severity if f.severity in by_severity else "info"
        by_severity[sev] += 1

    start_time_str: str | None = None
    if meta.start_time_utc is not None:
        start_time_str = meta.start_time_utc.isoformat()

    return {
        "goose_version": goose.__version__,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "flight": {
            "source_file": meta.source_file,
            "autopilot": meta.autopilot,
            "firmware_version": meta.firmware_version,
            "vehicle_type": meta.vehicle_type,
            "duration_sec": round(meta.duration_sec, 1),
            "start_time_utc": start_time_str,
            "log_format": meta.log_format,
            "motor_count": meta.motor_count,
        },
        "overall_score": overall,
        "overall_status": "pass" if overall >= 90 else ("warning" if overall >= 60 else "critical"),
        "summary": {
            "total_findings": len(findings),
            "by_severity": by_severity,
        },
        "findings": [_finding_to_dict(f) for f in findings],
    }
