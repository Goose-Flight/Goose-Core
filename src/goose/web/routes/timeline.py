"""Timeline route.

Extracted from cases_api.py during API modularization sprint.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["timeline"])


@router.get("/{case_id}/timeline")
async def get_timeline(case_id: str) -> JSONResponse:
    """Return the structured case timeline.

    v11 Strategy Sprint: prefers the persisted ``analysis/timeline.json``
    built during the analyze route (formal ``TimelineEvent`` objects). Falls
    back to a legacy findings-derived view if the case has no analysis run yet.
    """
    from goose.web.cases_api import get_service

    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc

    case_dir = svc.case_dir(case_id)

    # --- Preferred path: load the v2.0 timeline produced by analyze --------
    timeline_path = case_dir / "analysis" / "timeline.json"
    if timeline_path.exists():
        try:
            bundle = json.loads(timeline_path.read_text(encoding="utf-8"))
            events = bundle.get("events", [])
            return JSONResponse(
                {
                    "ok": True,
                    "timeline_version": bundle.get("timeline_version", "2.0"),
                    "run_id": bundle.get("run_id"),
                    "events": events,
                    "count": len(events),
                    "message": "Structured timeline from latest analysis run.",
                }
            )
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass  # fall through to legacy reconstruction

    # --- Legacy fallback: reconstruct from findings + parse diagnostics ----
    events: list[dict[str, Any]] = []

    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle = json.loads(findings_path.read_text(encoding="utf-8"))
            for f in bundle.get("findings", []):
                t = f.get("start_time") or f.get("end_time")
                if t is not None:
                    events.append(
                        {
                            "event_id": f.get("finding_id"),
                            "event_type": "finding",
                            "event_category": "finding",
                            "label": f.get("title", ""),
                            "start_time": t,
                            "end_time": f.get("end_time"),
                            "source": "plugin",
                            "severity": f.get("severity"),
                            "related_finding_ids": [f.get("finding_id")] if f.get("finding_id") else [],
                            "notes": (f.get("description") or "")[:200],
                        }
                    )
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass

    diag_path = case_dir / "parsed" / "parse_diagnostics.json"
    if diag_path.exists():
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            for mc in diag.get("mode_changes", []):
                events.append(
                    {
                        "event_id": None,
                        "event_type": "mode_change",
                        "event_category": "system",
                        "label": f"Mode: {mc.get('from_mode', '?')} -> {mc.get('to_mode', '?')}",
                        "start_time": mc.get("timestamp", 0),
                        "end_time": None,
                        "source": "parser",
                        "severity": None,
                    }
                )
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass

    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            duration = prov.get("flight_duration_sec")
            if duration:
                events.append(
                    {
                        "event_id": None,
                        "event_type": "phase",
                        "event_category": "flight_phase",
                        "label": "Flight start",
                        "start_time": 0,
                        "end_time": None,
                        "source": "parser",
                        "severity": None,
                    }
                )
                events.append(
                    {
                        "event_id": None,
                        "event_type": "phase",
                        "event_category": "flight_phase",
                        "label": "Flight end",
                        "start_time": duration,
                        "end_time": None,
                        "source": "parser",
                        "severity": None,
                    }
                )
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            pass

    events.sort(key=lambda e: e.get("start_time") or 0)
    return JSONResponse(
        {
            "ok": True,
            "timeline_version": "2.0-legacy",
            "events": events,
            "count": len(events),
            "message": "Timeline reconstructed from case artifacts (no analysis/timeline.json present)."
            if events
            else "No parsed data available yet. Run analysis first.",
        }
    )
