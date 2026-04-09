"""Report format registry — extension seam for Pro report generators.

Role of this module
-------------------
This is the report/export extension seam.  Core registers its built-in report
generators here.  Pro packages can register additional premium report formats
without modifying Core.

How it works
------------
A report generator is a callable with the signature::

    def my_generator(case_dir: Path, run_id: str | None) -> dict:
        ...

It receives the case directory path and an optional run_id, and returns a dict
that can be serialized to JSON or passed to a rendering layer.

Core generators are registered at module import time below.
Pro packages register theirs at install time::

    from goose.forensics.report_registry import register_report_generator
    register_report_generator("my_premium_format", my_generator)

After registration, ``list_report_formats()`` includes the new format and
``get_report_generator()`` can retrieve it.

Design rules
------------
- Core must never import Pro.  Registered generators live outside Core.
- Registration is explicit — no magic scanning, no entry_points here.
- Core generators are always present; Pro generators are additive.
- If a Pro generator raises, it must not crash the Core report pipeline.
  Callers are responsible for try/except around Pro generators.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for report generator callables.
# Signature: (case_dir: Path, run_id: str | None) -> dict[str, Any]
ReportGenerator = Callable[[Path, "str | None"], "dict[str, Any]"]

# Internal registry: format_name -> (generator_callable, description, is_core)
_REGISTRY: dict[str, tuple[ReportGenerator, str, bool]] = {}


def register_report_generator(
    format_name: str,
    generator: ReportGenerator,
    description: str = "",
    *,
    _is_core: bool = False,
) -> None:
    """Register a report generator for a named format.

    Args:
        format_name:  Unique string key for this format (e.g. ``"json_findings"``).
                      Must be a non-empty string.  Existing registrations are
                      overwritten — Core generators should use stable names.
        generator:    Callable with signature ``(case_dir: Path, run_id: str | None)
                      -> dict[str, Any]``.
        description:  Short human-readable description shown in the GUI and CLI.
        _is_core:     Internal flag — set True only for Core built-in generators.
                      Pro packages must not set this.
    """
    if not format_name or not isinstance(format_name, str):
        raise ValueError("format_name must be a non-empty string")
    if not callable(generator):
        raise TypeError(f"generator must be callable, got {type(generator).__name__}")
    _REGISTRY[format_name] = (generator, description, _is_core)
    logger.debug("Registered report generator: %s (core=%s)", format_name, _is_core)


def get_report_generator(format_name: str) -> ReportGenerator | None:
    """Return the generator for ``format_name``, or None if not registered."""
    entry = _REGISTRY.get(format_name)
    return entry[0] if entry is not None else None


def list_report_formats() -> list[dict[str, Any]]:
    """Return all registered report formats as a list of metadata dicts.

    Suitable for the ``/api/reports/formats`` endpoint and the GUI report picker.
    """
    return [
        {
            "format_name": name,
            "description": desc,
            "is_core": is_core,
        }
        for name, (_, desc, is_core) in _REGISTRY.items()
    ]


def list_core_formats() -> list[str]:
    """Return format names for Core-only generators."""
    return [name for name, (_, _, is_core) in _REGISTRY.items() if is_core]


def list_extension_formats() -> list[str]:
    """Return format names registered by Pro/extension packages."""
    return [name for name, (_, _, is_core) in _REGISTRY.items() if not is_core]


# ---------------------------------------------------------------------------
# Core generator registrations
# ---------------------------------------------------------------------------
# Each Core generator is a thin wrapper around the existing report objects in
# forensics/reports.py.  The generators are registered here so the registry
# API is always populated, even before any Pro package is installed.
# ---------------------------------------------------------------------------

def _generate_json_findings(case_dir: Path, run_id: str | None) -> dict[str, Any]:
    """Generate a JSON findings report from the last analysis run."""
    findings_path = case_dir / "analysis" / "findings.json"
    if not findings_path.exists() and run_id:
        findings_path = case_dir / "analysis" / f"findings_{run_id}.json"
    if findings_path.exists():
        import json
        try:
            return json.loads(findings_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read findings JSON: %s", exc)
    return {"findings": [], "source": str(findings_path), "available": findings_path.exists()}


def _generate_json_hypotheses(case_dir: Path, run_id: str | None) -> dict[str, Any]:
    """Generate a JSON hypotheses report from the last analysis run."""
    hyp_path = case_dir / "analysis" / "hypotheses.json"
    if not hyp_path.exists() and run_id:
        hyp_path = case_dir / "analysis" / f"hypotheses_{run_id}.json"
    if hyp_path.exists():
        import json
        try:
            return json.loads(hyp_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read hypotheses JSON: %s", exc)
    return {"hypotheses": [], "source": str(hyp_path), "available": hyp_path.exists()}


def _generate_timeline(case_dir: Path, run_id: str | None) -> dict[str, Any]:
    """Generate a timeline report from the persisted timeline artifact."""
    tl_path = case_dir / "analysis" / "timeline.json"
    if tl_path.exists():
        import json
        try:
            return json.loads(tl_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read timeline JSON: %s", exc)
    return {"events": [], "source": str(tl_path), "available": tl_path.exists()}


# Register Core built-ins
register_report_generator(
    "json_findings",
    _generate_json_findings,
    description="JSON export of all findings from the last analysis run.",
    _is_core=True,
)
register_report_generator(
    "json_hypotheses",
    _generate_json_hypotheses,
    description="JSON export of all hypotheses from the last analysis run.",
    _is_core=True,
)
register_report_generator(
    "timeline",
    _generate_timeline,
    description="Structured timeline of events from the last analysis run.",
    _is_core=True,
)
