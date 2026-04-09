"""Parser diagnostics and ParseResult contract for Goose forensic framework.

Every parser must return a ParseResult containing:
  - flight: the canonical Flight model (or None on failure)
  - diagnostics: structured ParseDiagnostics describing what the parser found
  - provenance: full lineage record linking parsed data back to source evidence

These types are the formal parser contract from Sprint 3 onward.
All parser-aware code must consume ParseResult rather than raw Flight objects.

Sprint 3 — Parser Framework and Diagnostics
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from goose.core.flight import Flight
    from goose.forensics.models import Provenance


# ---------------------------------------------------------------------------
# ParseDiagnostics
# ---------------------------------------------------------------------------

@dataclass
class StreamCoverage:
    """Coverage summary for a single telemetry stream/topic.

    Attached to ParseDiagnostics.stream_coverage after a parse.  Represents
    whether a particular Flight attribute stream was present in the log and,
    if so, how many rows it contained.

    The forensic engine uses this to:
    - Drive the plugin skip check (required_streams absent → plugin SKIPPED).
    - Compute the missing-data penalty for hypothesis confidence.
    - Build SignalQuality objects for the GUI's diagnostics tab.

    Fields
    ------
    stream_name  — name matching a Flight attribute (e.g. ``"battery"``)
    present      — True if the stream had at least one row
    row_count    — number of rows parsed (0 if not present)
    notes        — optional free-text note from the parser about this stream
    """

    stream_name: str
    present: bool
    row_count: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StreamCoverage:
        return cls(**d)


@dataclass
class ParseDiagnostics:
    """Structured diagnostics produced by a parser alongside the canonical Flight.

    Every parser must populate this regardless of whether parsing succeeded.
    Partial parses, corruptions, and unsupported formats must surface here —
    they must not be silently swallowed.

    Fields mirror the spec in 02_forensic_core_architecture_spec.md §4.5.

    Schema versioning
    -----------------
    ``diagnostics_version`` is a forward-compatibility field. Increment it
    when the shape of this dict changes in a way that would break a reader
    built against a prior version. Consumers must check this field before
    deserializing if they need strict compatibility.

    Confidence scope
    ----------------
    ``parser_confidence`` is **parse/data-quality confidence only**.
    It answers: "How completely and reliably did the parser extract data
    from this file?"  It does NOT reflect root-cause analysis confidence,
    plugin agreement, or investigative certainty — those live in Finding and
    Hypothesis models.  Conflating the two would corrupt forensic reasoning.

    Parser confidence scoring (ULogParser, v1):
      Start:  1.0
      Each critical missing stream (position, attitude, battery, gps): −0.15
      Each corruption indicator (capped at 3):                          −0.10
      Any timebase anomaly:                                             −0.05
      Floor:  0.0, rounded to 2 decimal places
    """

    # Schema version — increment on breaking serialization changes
    diagnostics_version: str = "1.0"

    # Parser identity
    parser_selected: str = ""           # parser class name, e.g. "ULogParser"
    parser_version: str = ""            # semver or hash

    # Format detection
    detected_format: str = ""           # "ulog" | "dataflash" | "tlog" | "csv" | "unknown"
    format_confidence: float = 0.0      # 0.0–1.0
    supported: bool = False             # False if format is not implemented

    # Parse quality — see "Confidence scope" in class docstring
    parser_confidence: float = 0.0      # 0.0–1.0, parse/data-quality confidence ONLY
    # Explicit label so consumers can never mistake the scope of this value:
    confidence_scope: str = "parser_parse_quality"  # always this value; not root-cause

    # Streams
    missing_streams: list[str] = field(default_factory=list)
    stream_coverage: list[StreamCoverage] = field(default_factory=list)

    # Diagnostics
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    corruption_indicators: list[str] = field(default_factory=list)
    timebase_anomalies: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    # Timestamps
    parse_started_at: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))
    parse_completed_at: datetime | None = None
    parse_duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostics_version": self.diagnostics_version,
            "parser_selected": self.parser_selected,
            "parser_version": self.parser_version,
            "detected_format": self.detected_format,
            "format_confidence": self.format_confidence,
            "supported": self.supported,
            "parser_confidence": self.parser_confidence,
            "confidence_scope": self.confidence_scope,
            "missing_streams": self.missing_streams,
            "stream_coverage": [s.to_dict() for s in self.stream_coverage],
            "warnings": self.warnings,
            "errors": self.errors,
            "corruption_indicators": self.corruption_indicators,
            "timebase_anomalies": self.timebase_anomalies,
            "assumptions": self.assumptions,
            "parse_started_at": self.parse_started_at.isoformat(),
            "parse_completed_at": self.parse_completed_at.isoformat() if self.parse_completed_at else None,
            "parse_duration_ms": self.parse_duration_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParseDiagnostics:
        d = dict(d)
        d["stream_coverage"] = [
            StreamCoverage.from_dict(s) for s in d.get("stream_coverage", [])
        ]
        d["parse_started_at"] = datetime.fromisoformat(d["parse_started_at"])
        if d.get("parse_completed_at"):
            d["parse_completed_at"] = datetime.fromisoformat(d["parse_completed_at"])
        # Forward-compat: ignore unknown keys from future versions
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)

    @classmethod
    def unsupported(cls, ext: str, parser_name: str = "") -> ParseDiagnostics:
        """Construct diagnostics for a format that is declared unsupported."""
        return cls(
            parser_selected=parser_name or "none",
            detected_format=ext.lstrip(".").lower() or "unknown",
            format_confidence=1.0 if ext else 0.0,
            supported=False,
            parser_confidence=0.0,
            errors=[
                f"Format '{ext}' is not supported. "
                "Only .ulg (PX4 ULog) files are currently implemented."
            ],
        )

    @classmethod
    def failed(
        cls,
        parser_name: str,
        parser_version: str,
        detected_format: str,
        error: str,
    ) -> ParseDiagnostics:
        """Construct diagnostics for a parse that failed with an exception."""
        return cls(
            parser_selected=parser_name,
            parser_version=parser_version,
            detected_format=detected_format,
            format_confidence=1.0,
            supported=True,
            parser_confidence=0.0,
            errors=[f"Parse failed: {error}"],
        )


# ---------------------------------------------------------------------------
# ParseResult
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    """The complete output of a parser invocation.

    A parser always returns this — even on failure.  On failure:
      - flight is None
      - diagnostics.errors is non-empty
      - diagnostics.parser_confidence is 0.0

    Consumers must check ``success`` before using ``flight``.
    """

    diagnostics: ParseDiagnostics
    flight: Flight | None = None
    provenance: Provenance | None = None
    # Raw artifacts produced by the parser that may be useful for debugging
    # (e.g. topic lists, parameter dumps). Not part of the canonical model.
    parse_artifacts: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True if the parse produced a usable Flight object."""
        return self.flight is not None and not self.diagnostics.errors

    @classmethod
    def failure(
        cls,
        diagnostics: ParseDiagnostics,
        provenance: Provenance | None = None,
    ) -> ParseResult:
        """Construct a failed ParseResult."""
        return cls(flight=None, diagnostics=diagnostics, provenance=provenance)
