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
    """Construct a timeline from flight phases, mode changes, events, and findings."""
    from goose.web.cases_api import get_service
    try:
        svc = get_service()
        svc.get_case(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    events: list[dict[str, Any]] = []
    case_dir = svc.case_dir(case_id)

    # Load findings
    findings_path = case_dir / "analysis" / "findings.json"
    if findings_path.exists():
        try:
            bundle = json.loads(findings_path.read_text(encoding="utf-8"))
            for f in bundle.get("findings", []):
                t = f.get("start_time") or f.get("end_time")
                if t is not None:
                    events.append({
                        "time": t,
                        "type": "finding",
                        "label": f.get("title", ""),
                        "severity": f.get("severity"),
                        "finding_id": f.get("finding_id"),
                        "description": f.get("description", ""),
                    })
        except Exception:
            pass

    # Load parse diagnostics for mode changes
    diag_path = case_dir / "parsed" / "parse_diagnostics.json"
    if diag_path.exists():
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
            for mc in diag.get("mode_changes", []):
                events.append({
                    "time": mc.get("timestamp", 0),
                    "type": "mode",
                    "label": f"{mc.get('from_mode', '?')} -> {mc.get('to_mode', '?')}",
                    "severity": None,
                    "finding_id": None,
                    "description": "Flight mode change",
                })
        except Exception:
            pass

    # Load provenance for flight start/end
    prov_path = case_dir / "parsed" / "provenance.json"
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            duration = prov.get("flight_duration_sec")
            if duration:
                events.append({
                    "time": 0,
                    "type": "phase",
                    "label": "Flight start",
                    "severity": None,
                    "finding_id": None,
                    "description": f"Total duration: {duration}s",
                })
                events.append({
                    "time": duration,
                    "type": "phase",
                    "label": "Flight end",
                    "severity": None,
                    "finding_id": None,
                    "description": "",
                })
        except Exception:
            pass

    events.sort(key=lambda e: e["time"])
    return JSONResponse({
        "ok": True,
        "timeline_version": "1.0",
        "events": events,
        "count": len(events),
        "message": "Timeline constructed from available case artifacts." if events else "No parsed data available yet. Run analysis first.",
    })
