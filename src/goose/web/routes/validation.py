"""Validation harness API routes for Goose-Core.

Advanced Forensic Validation Sprint — Corpus validation endpoints.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from goose import __version__
from goose.validation.harness import ValidationSummary, run_validation
from goose.validation.quality import compute_quality_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/validation", tags=["validation"])

# Results are persisted in-process for this session + to a JSON file
_LAST_RESULT_FILENAME = "last_validation_result.json"


def _corpus_dir() -> Path:
    """Resolve the corpus directory path."""
    # Prefer tests/corpus relative to repo root (cwd)
    candidates = [
        Path.cwd() / "tests" / "corpus",
        Path(__file__).parent.parent.parent.parent.parent / "tests" / "corpus",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _results_dir() -> Path:
    """Resolve the validation results storage directory."""
    d = Path.cwd() / "validation_results"
    d.mkdir(exist_ok=True)
    return d


@router.post("/run")
async def run_validation_endpoint() -> JSONResponse:
    """Run the corpus validation harness and return the summary."""
    corpus_dir = _corpus_dir()
    if not corpus_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Corpus directory not found: {corpus_dir}",
        )

    try:
        summary = run_validation(
            corpus_dir=corpus_dir,
            cases_dir=Path.cwd() / "cases",
            engine_version=__version__,
        )
    except Exception as exc:
        logger.exception("Validation run failed")
        raise HTTPException(status_code=500, detail=f"Validation failed: {exc}") from exc

    # Compute quality report
    quality_report = compute_quality_report(summary)

    # Persist result
    try:
        results_file = _results_dir() / _LAST_RESULT_FILENAME
        results_file.write_text(
            json.dumps({
                "summary": summary.to_dict(),
                "quality_report": quality_report.to_dict(),
            }, indent=2),
            encoding="utf-8",
        )
    except Exception:
        logger.warning("Failed to persist validation result")

    return JSONResponse({
        "ok": True,
        "summary": summary.to_dict(),
        "quality_report": quality_report.to_dict(),
    })


@router.get("/results")
async def get_validation_results() -> JSONResponse:
    """Return the most recent validation result, if any."""
    results_file = _results_dir() / _LAST_RESULT_FILENAME
    if not results_file.exists():
        return JSONResponse({
            "ok": True,
            "summary": None,
            "quality_report": None,
            "message": "No validation run yet.",
        })

    try:
        data = json.loads(results_file.read_text(encoding="utf-8"))
        return JSONResponse({
            "ok": True,
            "summary": data.get("summary"),
            "quality_report": data.get("quality_report"),
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read results: {exc}") from exc
