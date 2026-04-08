"""REST API endpoints for the Goose flight analysis dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel

from goose.core import Flight, Finding
from goose.core.crash_detector import analyze_crash
from goose.parsers.detect import parse_file
from goose.plugins.registry import load_plugins

router = APIRouter(prefix="/api", tags=["analysis"])


# ============================================================================
# Data Models
# ============================================================================

class PluginInfo(BaseModel):
    """Plugin metadata."""
    name: str
    description: str | None = None


class FindingResponse(BaseModel):
    """Finding response model."""
    plugin: str
    title: str
    severity: str
    score: int
    description: str
    evidence: dict[str, Any] | None = None
    phase: str | None = None
    timestamp_start: float | None = None
    timestamp_end: float | None = None


class AnalysisResponse(BaseModel):
    """Analysis response model."""
    findings: list[FindingResponse]
    plugins_run: list[str]
    file_name: str


class CrashAnalysisResponse(BaseModel):
    """Crash analysis response model."""
    crashed: bool
    confidence: float
    classification: str
    root_cause: str
    evidence_chain: list[str] = []
    contributing_factors: list[str] = []
    inspect_checklist: list[str] = []
    timeline: list[dict[str, Any]] = []


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str


# ============================================================================
# Utilities
# ============================================================================

def _parse_log_file(filepath: Path) -> Flight:
    """Parse a log file via the formal parser contract."""
    result = parse_file(filepath)
    if not result.success:
        errors = "; ".join(result.diagnostics.errors)
        raise ValueError(f"Failed to parse {filepath.name}: {errors}")
    assert result.flight is not None
    return result.flight


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Server health check endpoint."""
    from goose import __version__
    return HealthResponse(
        status="ok",
        version=__version__,
    )


@router.get("/plugins", response_model=list[PluginInfo])
def list_plugins() -> list[PluginInfo]:
    """List all loaded analysis plugins."""
    plugins = load_plugins()
    return [
        PluginInfo(
            name=plugin.name,
            description=getattr(plugin, "description", None),
        )
        for plugin in plugins
    ]


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_flight(file: UploadFile = File(...)) -> AnalysisResponse:
    """Analyze a flight log file and return all findings."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Save uploaded file temporarily
    with NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Parse the log file
        flight = _parse_log_file(tmp_path)

        # Load plugins and run analysis
        plugins = load_plugins()
        findings: list[Finding] = []
        plugins_run: list[str] = []

        for plugin in plugins:
            plugins_run.append(plugin.name)
            if not plugin.applicable(flight):
                continue
            try:
                findings.extend(plugin.analyze(flight, {}))
            except Exception as exc:
                findings.append(Finding(
                    plugin_name=plugin.name,
                    title=f"{plugin.name} plugin error",
                    severity="info",
                    score=50,
                    description=str(exc),
                ))

        # Convert findings to response format
        findings_response = [
            FindingResponse(
                plugin=f.plugin_name,
                title=f.title,
                severity=f.severity,
                score=f.score,
                description=f.description,
                evidence=f.evidence if f.evidence else None,
                phase=f.phase,
                timestamp_start=f.timestamp_start,
                timestamp_end=f.timestamp_end,
            )
            for f in findings
        ]

        return AnalysisResponse(
            findings=findings_response,
            plugins_run=plugins_run,
            file_name=file.filename,
        )

    finally:
        # Clean up temporary file
        tmp_path.unlink(missing_ok=True)


@router.post("/crash", response_model=CrashAnalysisResponse)
async def detect_crash(file: UploadFile = File(...)) -> CrashAnalysisResponse:
    """Analyze a flight log for crash detection and root cause."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Save uploaded file temporarily
    with NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Parse the log file
        flight = _parse_log_file(tmp_path)

        # Load plugins and run analysis to get all findings
        plugins = load_plugins()
        findings: list[Finding] = []

        for plugin in plugins:
            if not plugin.applicable(flight):
                continue
            try:
                findings.extend(plugin.analyze(flight, {}))
            except Exception:
                # Silently skip plugins that error during crash analysis
                pass

        # Analyze crash with all findings
        crash_analysis = analyze_crash(flight, findings)

        return CrashAnalysisResponse(
            crashed=crash_analysis.crashed,
            confidence=crash_analysis.confidence,
            classification=crash_analysis.classification,
            root_cause=crash_analysis.root_cause,
            evidence_chain=crash_analysis.evidence_chain,
            contributing_factors=crash_analysis.contributing_factors,
            inspect_checklist=crash_analysis.inspect_checklist,
            timeline=crash_analysis.timeline,
        )

    finally:
        # Clean up temporary file
        tmp_path.unlink(missing_ok=True)
